import { confirm } from "../lib/api.js";
import { fromNode, readRaw, send } from "../lib/node-handler.js";
import { openStore } from "../lib/store.js";

export const config = { api: { bodyParser: false } };

export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, { status: 405, headers: {}, body: { ok: false } });
  const body = await readRaw(req);
  try {
    send(res, await confirm(fromNode(req, body), process.env, openStore()));
  } catch (error) {
    const status = error.code === "unconfigured" ? 503 : 502;
    send(res, { status, headers: {}, body: { ok: false, error: status === 503 ? "unconfigured" : "store" } });
  }
}
