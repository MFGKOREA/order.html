import { createHmac, timingSafeEqual } from "node:crypto";

/** Shared with tools/screen_sync.py. Sign the exact bytes, never a re-serialized object. */

export function signBytes(secret, bytes) {
  return createHmac("sha256", secret).update(bytes).digest("hex");
}

export function verifyBytes(secret, bytes, header) {
  const got = String(header || "").replace(/^sha256=/, "");
  const expected = signBytes(secret, bytes);
  if (got.length !== expected.length) return false;
  return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
}

export function commandCanonical(cmd) {
  return `confirm\n${Number(cmd.task_id)}\n${cmd.idempotency_key}\n${cmd.at}`;
}

export function signCommand(secret, cmd) {
  return signBytes(secret, Buffer.from(commandCanonical(cmd)));
}

export const KEY_RE = /^[A-Za-z0-9:_-]{8,80}$/;
export const SKEW_MS = 120_000;
