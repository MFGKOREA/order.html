import { pullCommands } from "../../lib/api.js";
import { fromNode, send } from "../../lib/node-handler.js";
import { openStore } from "../../lib/store.js";

export default async function handler(req, res) {
  if (req.method !== "GET") return send(res, { status: 405, headers: {}, body: { ok: false } });
  try {
    send(res, await pullCommands(fromNode(req, Buffer.alloc(0)), process.env, openStore()));
  } catch (error) {
    const status = error.code === "unconfigured" ? 503 : 502;
    send(res, { status, headers: {}, body: { ok: false, error: status === 503 ? "unconfigured" : "store" } });
  }
}
