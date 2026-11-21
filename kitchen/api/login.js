import { login } from "../lib/api.js";
import { readRaw, send, fromNode } from "../lib/node-handler.js";

export const config = { api: { bodyParser: false } };

export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, { status: 405, headers: {}, body: { ok: false } });
  const body = await readRaw(req);
  send(res, await login(fromNode(req, body), process.env));
}
