import { createHash, createHmac, timingSafeEqual } from "node:crypto";

const COOKIE = "hub_session";
const MAX_AGE = 60 * 60 * 12;

export function passwordMatches(given, expected) {
  if (!expected) return false;
  const a = createHash("sha256").update(String(given)).digest();
  const b = createHash("sha256").update(String(expected)).digest();
  return timingSafeEqual(a, b);
}

export function issueSession(secret, now = Date.now()) {
  const payload = Buffer.from(JSON.stringify({ exp: now + MAX_AGE * 1000 })).toString("base64url");
  const sig = createHmac("sha256", secret).update(`session\n${payload}`).digest("base64url");
  return `${payload}.${sig}`;
}

export function readSession(token, secret, now = Date.now()) {
  if (!token || !secret || !token.includes(".")) return null;
  const [payload, sig] = token.split(".");
  const expected = createHmac("sha256", secret).update(`session\n${payload}`).digest("base64url");
  const left = Buffer.from(sig);
  const right = Buffer.from(expected);
  if (left.length !== right.length || !timingSafeEqual(left, right)) return null;
  try {
    const body = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (!body.exp || body.exp < now) return null;
    return body;
  } catch {
    return null;
  }
}

export function sessionCookie(token) {
  return `${COOKIE}=${token}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${MAX_AGE}`;
}

export function clearCookie() {
  return `${COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`;
}

export function cookieValue(header) {
  for (const part of String(header || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === COOKIE) return part.slice(i + 1).trim();
  }
  return "";
}
