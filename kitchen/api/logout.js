import { logout } from "../lib/api.js";
import { send } from "../lib/node-handler.js";

export default function handler(req, res) {
  if (req.method !== "POST") return send(res, { status: 405, headers: {}, body: { ok: false } });
  send(res, logout());
}
