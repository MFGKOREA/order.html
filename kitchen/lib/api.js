import { KEY_RE, SKEW_MS, commandCanonical, signCommand, verifyBytes } from "./hmac.js";
import { clearCookie, cookieValue, issueSession, passwordMatches, readSession, sessionCookie } from "./session.js";

function json(status, body, headers = {}) {
  return { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers }, body };
}

function unconfigured() {
  return json(503, { ok: false, error: "unconfigured" });
}

function authed(request, secret) {
  return readSession(cookieValue(request.headers.cookie || ""), secret, request.now);
}

export async function login(request, env) {
  const password = env.HUB_SCREEN_PASSWORD;
  const secret = env.HUB_SYNC_SECRET;
  if (!password || !secret) return unconfigured();
  let given = "";
  try {
    given = JSON.parse(request.body.toString("utf8")).password || "";
  } catch {
    given = "";
  }
  if (!passwordMatches(given, password)) return json(401, { ok: false, error: "login" });
  return json(200, { ok: true }, { "set-cookie": sessionCookie(issueSession(secret, request.now)) });
}

export function logout() {
  return json(200, { ok: true }, { "set-cookie": clearCookie() });
}

export async function readSnapshot(request, env, store) {
  if (!env.HUB_SYNC_SECRET) return unconfigured();
  if (!authed(request, env.HUB_SYNC_SECRET)) return json(401, { ok: false, error: "login" });
  try {
    const snapshot = await store.getSnapshot();
    return json(200, { ok: true, snapshot });
  } catch (error) {
    return error.code === "unconfigured" ? unconfigured() : json(502, { ok: false, error: "store" });
  }
}

export async function confirm(request, env, store) {
  const secret = env.HUB_SYNC_SECRET;
  if (!secret) return unconfigured();
  if (!authed(request, secret)) return json(401, { ok: false, error: "login" });
  let input = {};
  try {
    input = JSON.parse(request.body.toString("utf8"));
  } catch {
    return json(400, { ok: false, error: "body" });
  }
  const taskId = Number(input.task_id);
  const key = String(input.idempotency_key || "");
  if (!Number.isInteger(taskId) || taskId < 1 || taskId > 999999 || !KEY_RE.test(key)) {
    return json(400, { ok: false, error: "body" });
  }
  const cmd = {
    task_id: taskId,
    idempotency_key: key,
    at: new Date(request.now).toISOString().replace(/\.\d{3}Z$/, "Z"),
  };
  cmd.sig = signCommand(secret, cmd);
  try {
    const saved = await store.enqueue(cmd);
    return json(200, { ok: true, idempotency_key: key, duplicate: Boolean(saved.duplicate) });
  } catch (error) {
    return error.code === "unconfigured" ? unconfigured() : json(502, { ok: false, error: "store" });
  }
}

export async function pushSnapshot(request, env, store) {
  const secret = env.HUB_SYNC_SECRET;
  if (!secret) return unconfigured();
  if (!verifyBytes(secret, request.body, request.signature)) return json(401, { ok: false, error: "signature" });
  let snapshot;
  try {
    snapshot = JSON.parse(request.body.toString("utf8"));
  } catch {
    return json(400, { ok: false, error: "body" });
  }
  if (!snapshot || !Array.isArray(snapshot.badges) || !Array.isArray(snapshot.confirms) || !Array.isArray(snapshot.timeline)) {
    return json(400, { ok: false, error: "body" });
  }
  if (request.body.length > 100_000) return json(413, { ok: false, error: "body" });
  try {
    await store.putSnapshot(snapshot);
    return json(200, { ok: true });
  } catch (error) {
    return error.code === "unconfigured" ? unconfigured() : json(502, { ok: false, error: "store" });
  }
}

function freshTimestamp(request, now) {
  const stamp = Number(request.timestamp);
  return Number.isFinite(stamp) && Math.abs(now - stamp * 1000) <= SKEW_MS;
}

export async function pullCommands(request, env, store) {
  const secret = env.HUB_SYNC_SECRET;
  if (!secret) return unconfigured();
  const canon = Buffer.from(`GET\n/api/hub/commands\n${request.timestamp}`);
  if (!freshTimestamp(request, request.now) || !verifyBytes(secret, canon, request.signature)) {
    return json(401, { ok: false, error: "signature" });
  }
  try {
    const commands = await store.listCommands();
    return json(200, { commands });
  } catch (error) {
    return error.code === "unconfigured" ? unconfigured() : json(502, { ok: false, error: "store" });
  }
}

export async function ackCommands(request, env, store) {
  const secret = env.HUB_SYNC_SECRET;
  if (!secret) return unconfigured();
  if (!verifyBytes(secret, request.body, request.signature)) return json(401, { ok: false, error: "signature" });
  let keys = [];
  try {
    keys = JSON.parse(request.body.toString("utf8")).keys;
  } catch {
    return json(400, { ok: false, error: "body" });
  }
  if (!Array.isArray(keys) || keys.length > 100 || keys.some((key) => !KEY_RE.test(String(key)))) {
    return json(400, { ok: false, error: "body" });
  }
  try {
    await store.ack(keys.map(String));
    return json(200, { ok: true });
  } catch (error) {
    return error.code === "unconfigured" ? unconfigured() : json(502, { ok: false, error: "store" });
  }
}

export { commandCanonical };
