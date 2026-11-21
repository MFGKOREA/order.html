import { cookieValue } from "./session.js";

export async function readRaw(req) {
  if (Buffer.isBuffer(req.body)) return req.body;
  if (typeof req.body === "string") return Buffer.from(req.body);
  const chunks = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks);
}

export function send(res, result) {
  res.statusCode = result.status;
  for (const [key, value] of Object.entries(result.headers || {})) res.setHeader(key, value);
  res.end(JSON.stringify(result.body));
}

export function fromNode(req, body, now = Date.now()) {
  return {
    now,
    body,
    signature: req.headers["x-hub-signature"] || "",
    timestamp: req.headers["x-hub-timestamp"] || "",
    headers: { cookie: req.headers.cookie || "" },
  };
}

export function sessionToken(req) {
  return cookieValue(req.headers.cookie || "");
}
