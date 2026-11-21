/** Snapshot and confirm queue. Production uses the Vercel KV / Upstash REST API. Tests pass a memory store. */

export function memoryStore() {
  let snapshot = null;
  const queue = [];
  const acked = new Set();
  return {
    async putSnapshot(value) {
      snapshot = value;
    },
    async getSnapshot() {
      return snapshot;
    },
    async enqueue(cmd) {
      const existing = queue.find((item) => item.idempotency_key === cmd.idempotency_key);
      if (existing) return { ...existing, duplicate: true };
      if (acked.has(cmd.idempotency_key)) return { ...cmd, duplicate: true };
      queue.push(cmd);
      return cmd;
    },
    async listCommands() {
      return queue.slice();
    },
    async ack(keys) {
      for (const key of keys) {
        acked.add(key);
        const index = queue.findIndex((item) => item.idempotency_key === key);
        if (index >= 0) queue.splice(index, 1);
      }
    },
  };
}

async function redis(args) {
  const url = process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_TOKEN;
  if (!url || !token) {
    const error = new Error("unconfigured");
    error.code = "unconfigured";
    throw error;
  }
  const response = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(args),
  });
  if (!response.ok) {
    const error = new Error("store");
    error.code = "store";
    throw error;
  }
  const data = await response.json();
  if (data.error) {
    const error = new Error("store");
    error.code = "store";
    throw error;
  }
  return data.result;
}

export function kvStore() {
  return {
    async putSnapshot(value) {
      await redis(["SET", "hub:snapshot", JSON.stringify(value)]);
    },
    async getSnapshot() {
      const raw = await redis(["GET", "hub:snapshot"]);
      return raw ? JSON.parse(raw) : null;
    },
    async enqueue(cmd) {
      const seen = await redis(["SISMEMBER", "hub:acked", cmd.idempotency_key]);
      if (seen === 1) return { ...cmd, duplicate: true };
      const current = await redis(["HGET", "hub:queue", cmd.idempotency_key]);
      if (current) return { ...JSON.parse(current), duplicate: true };
      await redis(["HSET", "hub:queue", cmd.idempotency_key, JSON.stringify(cmd)]);
      return cmd;
    },
    async listCommands() {
      const flat = (await redis(["HGETALL", "hub:queue"])) || [];
      const out = [];
      for (let i = 1; i < flat.length; i += 2) out.push(JSON.parse(flat[i]));
      return out;
    },
    async ack(keys) {
      if (!keys.length) return;
      await redis(["SADD", "hub:acked", ...keys]);
      await redis(["HDEL", "hub:queue", ...keys]);
    },
  };
}

export function openStore() {
  if (process.env.KV_REST_API_URL && process.env.KV_REST_API_TOKEN) return kvStore();
  const error = new Error("unconfigured");
  error.code = "unconfigured";
  throw error;
}
