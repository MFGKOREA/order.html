import assert from "node:assert/strict";
import test from "node:test";
import { confirm, login, pullCommands, pushSnapshot, readSnapshot } from "../lib/api.js";
import { commandCanonical, signBytes, signCommand, verifyBytes } from "../lib/hmac.js";
import { issueSession, readSession } from "../lib/session.js";
import { memoryStore } from "../lib/store.js";

const SECRET = "test-secret";
const ENV = { HUB_SCREEN_PASSWORD: "correct horse", HUB_SYNC_SECRET: SECRET };

test("snapshot signature matches the hub vector", () => {
  const body = Buffer.from('{"ok":true}');
  assert.equal(signBytes(SECRET, body), "97b4f11584439784b801821ece72af4e29c19573aacf94bcc0533c09086b3643");
  assert.equal(verifyBytes(SECRET, body, "sha256=97b4f11584439784b801821ece72af4e29c19573aacf94bcc0533c09086b3643"), true);
  assert.equal(verifyBytes(SECRET, body, "sha256=00"), false);
});

test("confirm command signature matches the hub vector", () => {
  const cmd = { task_id: 3, idempotency_key: "confirm-3-abc", at: "2026-11-21T16:00:00Z" };
  assert.equal(commandCanonical(cmd), "confirm\n3\nconfirm-3-abc\n2026-11-21T16:00:00Z");
  assert.equal(signCommand(SECRET, cmd), "869c1b056ad0fe4a5d72e94fe4dc17c6ede4d1a8925cc3bd2c41ca9b4732cdd2");
});

test("login sets an HttpOnly cookie and the snapshot stays behind it", async () => {
  const store = memoryStore();
  const now = Date.parse("2026-11-21T16:00:00Z");
  const bad = await login({ body: Buffer.from(JSON.stringify({ password: "nope" })), now }, ENV);
  assert.equal(bad.status, 401);
  assert.equal(bad.headers["set-cookie"], undefined);
  const good = await login({ body: Buffer.from(JSON.stringify({ password: "correct horse" })), now }, ENV);
  assert.equal(good.status, 200);
  assert.match(good.headers["set-cookie"], /HttpOnly/);
  assert.match(good.headers["set-cookie"], /Secure/);
  const token = good.headers["set-cookie"].split(";")[0].split("=")[1];
  assert.ok(readSession(token, SECRET, now));
  const denied = await readSnapshot({ headers: { cookie: "" }, now }, ENV, store);
  assert.equal(denied.status, 401);
  const allowed = await readSnapshot({ headers: { cookie: `hub_session=${token}` }, now }, ENV, store);
  assert.equal(allowed.status, 200);
  assert.equal(allowed.body.snapshot, null);
});

test("a signed snapshot is stored and a confirm is queued once", async () => {
  const store = memoryStore();
  const now = Date.parse("2026-11-21T16:00:00Z");
  const body = Buffer.from(JSON.stringify({ badges: [], confirms: [], timeline: [], spend: "" }));
  const pushed = await pushSnapshot({
    body,
    signature: `sha256=${signBytes(SECRET, body)}`,
    now,
  }, ENV, store);
  assert.equal(pushed.status, 200);
  const token = issueSession(SECRET, now);
  const key = "confirm-3-abc000";
  const first = await confirm({
    headers: { cookie: `hub_session=${token}` },
    body: Buffer.from(JSON.stringify({ task_id: 3, idempotency_key: key })),
    now,
  }, ENV, store);
  const second = await confirm({
    headers: { cookie: `hub_session=${token}` },
    body: Buffer.from(JSON.stringify({ task_id: 3, idempotency_key: key })),
    now,
  }, ENV, store);
  assert.equal(first.status, 200);
  assert.equal(second.body.duplicate, true);
  const commands = await store.listCommands();
  assert.equal(commands.length, 1);
  assert.equal(commands[0].sig, signCommand(SECRET, commands[0]));
  const ts = "1700000000";
  const canon = Buffer.from(`GET\n/api/hub/commands\n${ts}`);
  const listed = await pullCommands({
    timestamp: ts,
    signature: `sha256=${signBytes(SECRET, canon)}`,
    now: 1700000000 * 1000,
  }, ENV, store);
  assert.equal(listed.status, 200);
  assert.equal(listed.body.commands.length, 1);
});

test("unsigned hub calls are refused and the password is not in the response", async () => {
  const store = memoryStore();
  const refused = await pushSnapshot({ body: Buffer.from("{}"), signature: "", now: Date.now() }, ENV, store);
  assert.equal(refused.status, 401);
  assert.equal(JSON.stringify(refused), JSON.stringify(refused).includes("correct horse") ? "leaked" : JSON.stringify(refused));
  assert.equal(JSON.stringify(refused).includes(SECRET), false);
});
