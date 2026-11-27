// 되돌려 보기 ② 가상 시계로 여러 날 돌려 보기: 책상 판단(desk-core.js)이 매장 하루를 어떻게 굴리는지
//  진짜 판단 코드(desk-core.js + label-list 의 autoPlan·periodDue)를 20초 간격으로 그대로 부르고, 나머지는 흉내:
//   · 어사이드: 책상을 H분마다 봄(routine). 볼 때 '읽기 시작'이 떠 있으면 GW·MIS 를 열고 시작 코드를 실행(40~120초). 가끔 못 함(pMiss)
//   · 읽기 코드: 종류마다 15~40초, 가끔 실패(pReadFail). 끝나면 시트에 결과를 적음
//   · 매장: 하루 한 번 폰 [GW 전송](13:00~14:30), 가끔 [Gross 불러오기], 가끔 인터넷·VPN 끊김, 가끔 발주 대기 탭이 죽음
//   · 섀도 단계에서는 GW Agent 확장도 같이 돎(같은 판단 코드 + 바로 움직이는 손)
//  지어낸 시트만 씀(진짜 시트·MIS 에 요청 없음). 같은 씨앗이면 같은 결과
//  사용: node aside/test/bt/schedule.mjs [--days 30] [--seed 1] [--quick]
import fs from "fs";
import path from "path";
import { createRequire } from "module";
import { fileURLToPath } from "url";
const require = createRequire(import.meta.url), HERE = path.dirname(fileURLToPath(import.meta.url)), REPO = path.resolve(HERE, "../../..");
require("../../desk-core.js");
const LL = [process.env.LABEL_LIST, path.resolve(REPO, "../mfgkorea/label-list"), path.resolve(REPO, "../label-list")].filter(Boolean).find((p) => fs.existsSync(path.join(p, "gw-agent/periodic.js")));
if (!LL) { console.log("건너뜀: label-list 사본이 없음 (LABEL_LIST=경로)"); process.exit(0); }
require(path.join(LL, "gw-agent/auto.js")); require(path.join(LL, "gw-agent/periodic.js"));
const PLAN = JSON.parse(fs.readFileSync(path.join(LL, "gw-plan.json"), "utf8"));
const D = globalThis.AsideDesk, MIN = 60e3, HOUR = 3600e3, DAY = 86400e3, STEP = 20e3;
const arg = (n, d) => { const i = process.argv.indexOf("--" + n); return i >= 0 ? process.argv[i + 1] : d; };
const DAYS = +arg("days", process.argv.includes("--quick") ? 6 : 30), SEED = +arg("seed", 1);
const ymd = (ms) => new Date(ms + 9 * HOUR).toISOString().slice(0, 10), hmOf = (ms) => { const t = new Date(ms + 9 * HOUR); return t.getUTCHours() * 60 + t.getUTCMinutes(); };
const addDay = (d, n) => new Date(Date.parse(d + "T00:00:00Z") + n * DAY).toISOString().slice(0, 10), atKst = (day, hm) => Date.parse(day + "T00:00:00+09:00") + hm * MIN;
const clone = (o) => JSON.parse(JSON.stringify(o));
const merge = (a, p) => { a = a && typeof a === "object" ? a : {}; Object.keys(p).forEach((k) => { if (p[k] === null) delete a[k]; else if (p[k] && typeof p[k] === "object" && !Array.isArray(p[k])) a[k] = merge(a[k], p[k]); else a[k] = p[k]; }); return a; };

function simulate(P) {
  let s = P.seed >>> 0; const rnd = () => { s = (s + 0x6d2b79f5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const U = (a, b) => a + rnd() * (b - a);
  const D0 = "2026-11-02", T0 = atKst(D0, 0), END = T0 + P.days * DAY;
  // ---- 지어낸 시트: 품목 60 · Forecast·메뉴 판매는 시작 전날까지 차 있음 ----
  const sheet = { "master.order": { rows: Array.from({ length: 60 }, (_, i) => ({ name: "x" + i, code: String(900001 + i) })) }, forecast: {}, asideCfg: P.cfg };
  for (let i = 1; i <= 60; i++) { const x = addDay(D0, -i); sheet.forecast[x] = { fc: "100", act: "90" }; sheet["menuDay." + x] = { at: 1, rows: [] }; }
  for (let i = 0; i < 30; i++) sheet["pad" + i] = 1;
  for (const k of ["hourShare", "misOrderScan", "misRecvScan", "misXferScan", "misSetScan"]) sheet[k] = { at: T0 - DAY, to: addDay(D0, -1) };
  sheet.gwScout = { at: 1 };
  const M = { posts: {}, badPost: [], reqInSkip: 0, concurrent: 0, stuck: [], fullReads: 0, lightReads: 0, agentActs: 0, instr: {}, stops: 0, orders: [], perSlots: {}, firstIn: {}, shadow: { runs: 0, ok: 0, slots: 0 }, reads: { n: 0, ok: 0, timeout: 0 }, press: [] };
  const light = () => ({ misPush: clone(sheet.misPush || {}), salesPush: clone(sheet.salesPush || {}), misAgent: clone(sheet.misAgent || {}) });
  // 인터넷·VPN 끊김(날마다 미리 정함)
  const outs = [];
  for (let i = 0; i < P.days; i++) { const day = addDay(D0, i); if (rnd() < P.pNetOut) { const a = atKst(day, U(8 * 60, 21 * 60)); outs.push({ a, b: a + U(5, 40) * MIN, kind: "net" }); } if (rnd() < P.pVpnOut) { const a = atKst(day, U(7 * 60, 20 * 60)); outs.push({ a, b: a + U(60, 300) * MIN, kind: "vpn" }); } }
  const out = (now, kind) => outs.some((o) => o.kind === kind && now >= o.a && now < o.b);
  // 매장 일: 폰 [GW 전송] 하루 한 번 · [Gross 불러오기] 가끔
  const events = [];
  for (let i = 0; i < P.days; i++) { const day = addDay(D0, i); events.push({ t: atKst(day, U(13 * 60, 14 * 60 + 30)), type: "order", day }); if (rnd() < P.pPress) events.push({ t: atKst(day, U(9 * 60, 21 * 60)), type: "press", day }); if (P.cfg.orders === "live" && rnd() < P.pTabDie) events.push({ t: atKst(day, U(6 * 60, 22 * 60)), type: "tabdie" }); }
  events.sort((a, b) => a.t - b.t);

  // ---- 읽기 코드 흉내 ----
  const DAILY = { orders: "misOrderScan", recv: "misRecvScan", xfer: "misXferScan", sets: "misSetScan", hour: "hourShare", scout: "gwScout" };
  let reader = null; // { ch, id, startAt, endAt, ok, kinds, shadow }
  const startReader = (ch, now) => {
    const rq = sheet[ch]; if (!rq || rq.status !== "pending") return false;
    const kinds = [rq.kind || "gross"].concat(Object.keys(rq.also || {}));
    rq.status = "running"; rq.startAt = now;
    reader = { ch, id: rq.id, startAt: now, endAt: now + kinds.reduce((a) => a + U(15, 40) * 1000, 0), ok: rnd() >= P.pReadFail, kinds, today: !!rq.today, shadow: ch === "asidePush" };
    return true;
  };
  const stepReader = (now) => {
    if (!reader || now < reader.endAt) return;
    const R = reader, rq = sheet[R.ch]; reader = null;
    if (!rq || rq.id !== R.id) return; // 그새 다른 요청으로 바뀜 → 조용히 끝
    rq.status = R.ok ? "done" : "error"; rq.doneAt = now; rq.parts = Object.fromEntries(R.kinds.map((k) => [k, { status: rq.status, doneAt: now }]));
    M.reads.n++; if (R.ok) M.reads.ok++;
    if (R.shadow) { sheet.asideShadow = sheet.asideShadow || { runs: {} }; sheet.asideShadow.runs[R.id] = { id: R.id, at: now, ok: R.ok, same: R.ok ? R.kinds.length * 10 : 0, nDiff: 0, nMiss: 0, kind: R.kinds[0] }; return; }
    if (!R.ok) return;
    const T = ymd(now), Y = addDay(T, -1);
    R.kinds.forEach((k) => {
      if (k === "gross") for (let x = rq.from || Y; x <= (rq.to || Y); x = addDay(x, 1)) { if (x < T) { sheet.forecast[x] = Object.assign({}, sheet.forecast[x], { act: "90" }); if (!M.firstIn["g" + x]) M.firstIn["g" + x] = now; } }
      else if (k === "menu" && !R.today) { const mf = (rq.kind === "menu" ? rq : (rq.also || {}).menu) || {}; for (let x = mf.from || Y; x <= (mf.to || Y); x = addDay(x, 1)) if (x < T && !sheet["menuDay." + x]) { sheet["menuDay." + x] = { at: now, rows: [] }; M.firstIn["m" + x] = now; } }
      else if (k === "now") { sheet.nowSales = { at: now, day: T }; const slot = T + " " + String(Math.floor(hmOf(R.startAt) / 60)).padStart(2, "0"); M.perSlots[slot] = now; }
      else if (DAILY[k]) { sheet[DAILY[k]] = { at: now, to: k === "xfer" ? T : Y }; if (!M.firstIn[k + Y]) M.firstIn[k + Y] = now; }
    });
  };

  // ---- 책상 하나 = 판단 + (상태 기억). who: "aside"(시험 대상) | "ext"(GW Agent 확장 흉내) ----
  const mk = (who, cfgOf) => ({ who, st: {}, full: null, fullAt: 0, fullFailAt: 0, cfgOf, instr: null });
  const stepDesk = (K, now) => {
    if (out(now, "net")) return; // 인터넷이 끊기면 책상은 아무것도 못 함
    const cfg = K.cfgOf();
    M.lightReads += K.who === "aside" ? 1 : 0;
    let r;
    for (let k = 0; k < 2; k++) {
      const lt = light(); if (K.who === "ext") delete lt.misAgent; // 확장 흉내는 제 소식을 '확장이 켜져 있음'으로 보지 않게
      r = D.decide({ now, cfg, light: lt, full: K.full, fullAt: K.fullAt, fullFailAt: K.fullFailAt, plan: PLAN, st: K.st });
      K.st = r.st;
      for (const a of r.acts) {
        if (a.type !== "post") continue;
        const b = a.body;
        if (K.who === "ext" && /^aside/.test(b.key)) continue; // 확장 흉내가 적는 책상 소식은 버림
        if (K.who === "aside") {
          M.posts[b.key] = (M.posts[b.key] || 0) + 1;
          const allowed = cfg.reads === "live" || cfg.orders === "live" ? /^(asidePush|asideDesk|asideDiag|salesPush|misAgent|misPush)$/ : /^(asidePush|asideDesk|asideDiag)$/;
          if (!allowed.test(b.key)) M.badPost.push(b.key);
          if ((b.key === "salesPush" || b.key === "asidePush") && b.action === "set") { const hm = hmOf(now); if (hm >= 750 && hm <= 885) M.reqInSkip++; if (reader) M.concurrent++; }
        }
        if (b.action === "set") { if (b.value === null) delete sheet[b.key]; else sheet[b.key] = clone(b.value); } else if (b.action === "merge") sheet[b.key] = merge(sheet[b.key], clone(b.patch));
      }
      if (!r.wantFull) break;
      K.full = clone(sheet); K.fullAt = now; if (K.who === "aside") M.fullReads++;
    }
    K.instr = r.instr;
    if (K.who === "aside") { M.instr[r.instr.code] = (M.instr[r.instr.code] || 0) + 1; if (r.instr.code === "STOP" && !K.wasStop) M.stops++; K.wasStop = r.instr.code === "STOP"; }
  };
  const aside = mk("aside", () => sheet.asideCfg), ext = P.ext ? mk("ext", () => ({ reads: "live" })) : null;

  // ---- 손 흉내: 책상을 볼 때 할 일이 있으면 시작. busyUntil 까지는 다른 일을 안 함 ----
  const hand = (K, o) => ({ K, o, nextLook: T0 + U(0, o.H), act: null });
  const stepHand = (Hd, now) => {
    const K = Hd.K;
    if (Hd.act) { // 하던 일(시작 코드 실행까지)이 끝날 때
      if (now < Hd.act.t) return;
      const a = Hd.act; Hd.act = null;
      if (out(now, "vpn") || out(now, "net")) {
        if (K.who === "aside") { const r = D.stuck(K.st, now, "GW 가 안 열림 (인터넷·VPN)", K.cfgOf()); K.st = r.st; if (!out(now, "net")) r.posts.forEach((b) => { if (b.action === "merge") sheet[b.key] = merge(sheet[b.key], clone(b.patch)); else sheet[b.key] = clone(b.value); }); }
        else if (K.st.run) { const rq = sheet[K.st.run.ch]; if (rq && rq.id === K.st.run.id && !out(now, "net")) { rq.status = "error"; rq.doneAt = now; } } // 확장: 못 열면 바로 오류를 적음
        return;
      }
      if (a.code === "READ") { if (!reader) startReader(a.ch, now); }
      if (a.code === "ARM") { warm.alive = true; warm.beatAt = 0; }
      return;
    }
    if (now < Hd.nextLook) return;
    Hd.nextLook = now + Hd.o.H * U(0.9, 1.1);
    const i = K.instr; if (!i || (i.code !== "READ" && i.code !== "ARM")) return;
    if (rnd() < Hd.o.pMiss) return; // 이번엔 못 봄·못 함
    if (K.who === "aside") M.agentActs++;
    Hd.act = { code: i.code, ch: K.st.run ? K.st.run.ch : "salesPush", t: now + U(Hd.o.actMin, Hd.o.actMax) * 1000 };
  };
  const asideHand = hand(aside, { H: P.H, pMiss: P.pMiss, actMin: 40, actMax: 120 }), extHand = ext ? hand(ext, { H: 3e3, pMiss: 0, actMin: 30, actMax: 70 }) : null;

  // ---- 발주: 대기 탭(어사이드, orders live) 또는 확장이 처리 ----
  const warm = { alive: false, beatAt: 0, job: null };
  const stepOrders = (now) => {
    const mp = sheet.misPush;
    if (P.cfg.orders === "live") {
      if (warm.alive && !out(now, "net") && now - warm.beatAt >= 110e3) { warm.beatAt = now; sheet.misAgent = { at: now, grid: true, ver: "5" }; }
      if (warm.alive && mp && mp.status === "pending" && !warm.job && !out(now, "net") && !out(now, "vpn")) { mp.status = "running"; warm.job = { id: mp.id, t: now + U(20, 60) * 1000 }; }
      if (warm.job && now >= warm.job.t) { if (sheet.misPush.id === warm.job.id) { sheet.misPush.status = rnd() < 0.97 ? "done" : "error"; sheet.misPush.doneAt = now; } warm.job = null; }
    } else if (ext && mp && mp.status === "pending" && !mp._ext) { mp._ext = now + U(60, 120) * 1000; }
    if (ext && mp && mp._ext && now >= mp._ext && /pending|running/.test(mp.status)) { mp.status = "done"; mp.doneAt = now; delete mp._ext; }
    // 풀린 전송을 셈
    const o = M.orders[M.orders.length - 1];
    if (o && !o.end && mp && mp.id === o.id && /done|error/.test(mp.status)) { o.end = mp.doneAt || now; o.status = mp.status; o.by = mp.text ? "desk" : "tab"; }
  };

  // ---- 시계 돌리기 ----
  let ei = 0, netBackAt = 0;
  for (let now = T0; now < END; now += STEP) {
    while (ei < events.length && events[ei].t <= now) {
      const e = events[ei++];
      if (e.type === "order") { sheet.misPush = { date: e.day, id: Math.floor(e.t), at: Math.floor(e.t), status: "pending" }; M.orders.push({ id: Math.floor(e.t), at: e.t }); }
      if (e.type === "press") { sheet.salesPush = { id: Math.floor(e.t), at: Math.floor(e.t), status: "pending", from: addDay(e.day, -1), to: addDay(e.day, -1), src: "phone" }; M.press.push({ id: Math.floor(e.t), at: e.t }); if (reader && reader.ch === "salesPush") reader.id = -1; }
      if (e.type === "tabdie") warm.alive = false;
    }
    stepReader(now); stepOrders(now);
    if (ext) { stepDesk(ext, now); stepHand(extHand, now); }
    stepDesk(aside, now); stepHand(asideHand, now);
    // 갇힌 요청 찾기: 25분 넘게 pending/running
    //  인터넷이 끊긴 동안은 책상도 못 쓰므로 세지 않음(돌아온 뒤 10분 안에 풀려야 함)
    if (out(now, "net")) netBackAt = now + STEP;
    for (const ch of ["salesPush", "asidePush"]) { const rq = sheet[ch]; if (rq && /pending|running/.test(rq.status) && now - rq.at > 25 * MIN && now - netBackAt > 10 * MIN && !rq._stuck && (ch === "asidePush" || P.cfg.reads === "live")) { rq._stuck = 1; M.stuck.push(`${ch} ${rq.src || "ext"} ${rq.status} @${ymd(now).slice(5)} ${String(Math.floor(hmOf(now) / 60)).padStart(2, "0")}:${String(hmOf(now) % 60).padStart(2, "0")} 책상=${(aside.instr || {}).code}${out(now, "vpn") ? " vpn끊김" : ""}`); } }
    // 폰에서 누른 요청이 풀린 때
    M.press.forEach((p) => { if (!p.end && sheet.salesPush && sheet.salesPush.id === p.id && /done|error/.test(sheet.salesPush.status)) { p.end = now; p.status = sheet.salesPush.status; } });
    if (aside.st.sh && aside.st.sh.done) M.shadow.slots = Math.max(M.shadow.slots, 0);
  }
  // ---- 셈 ----
  const lag = (prefix) => { const hs = []; let miss = 0; for (let i = 0; i < P.days - 1; i++) { const day = addDay(D0, i), t = M.firstIn[prefix + day]; if (!t) { miss++; continue; } hs.push((t - (atKst(day, 0) + DAY)) / HOUR); } hs.sort((a, b) => a - b); return { n: hs.length, miss, onTime: hs.filter((h) => h <= 12).length, med: hs.length ? hs[Math.floor(hs.length / 2)] : null, p90: hs.length ? hs[Math.floor(hs.length * 0.9)] : null }; };
  const slots = []; for (let i = 0; i < P.days; i++) for (const h of ["12", "16", "20"]) slots.push(addDay(D0, i) + " " + h);
  const runs = Object.values((sheet.asideShadow || {}).runs || {});
  const ordDone = M.orders.filter((o) => o.end), ordFast = ordDone.filter((o) => o.status === "done" && o.end - o.at <= 2 * MIN), ordErrMsg = M.orders.filter((o) => o.status === "error");
  const pressDone = M.press.filter((p) => p.end);
  return { M, days: P.days, gross: lag("g"), menu: lag("m"), recv: lag("recv"), slotHit: slots.filter((x) => M.perSlots[x]).length, slotN: slots.length, shadowRuns: runs.length, shadowOk: runs.filter((r) => r.ok).length,
    orders: { n: M.orders.length, done: ordDone.filter((o) => o.status === "done").length, fast: ordFast.length, err: ordErrMsg.length, open: M.orders.length - ordDone.length, medS: ordDone.length ? Math.round(ordDone.map((o) => (o.end - o.at) / 1000).sort((a, b) => a - b)[Math.floor(ordDone.length / 2)]) : null },
    press: { n: M.press.length, done: pressDone.filter((p) => p.status === "done").length, medMin: pressDone.length ? Math.round(pressDone.map((p) => (p.end - p.at) / MIN).sort((a, b) => a - b)[Math.floor(pressDone.length / 2)] * 10) / 10 : null } };
}

// ================= 돌려 보기 =================
const BASE = { days: DAYS, seed: SEED, pMiss: 0.05, pReadFail: 0.07, pNetOut: 0.15, pVpnOut: 0.1, pPress: 0.5, pTabDie: 0.5 };
let fails = 0; const ok = (c, m) => { console.log((c ? "통과 " : "실패 ") + m); if (!c) fails++; };
const pct = (a, b) => (b ? Math.round((a / b) * 100) + "%" : "-");
console.log(`가상 ${DAYS}일 · 씨앗 ${SEED} · 가정: 어사이드가 못 함 5% · 읽기 실패 7% · 인터넷 끊김 15%/일 · VPN 끊김 10%/일 · 대기 탭 죽음 50%/일\n`);

// ---- A) 섀도 단계: 확장이 일하는 옆에서 하루 두 번 맞춰 보기 ----
console.log("A) 섀도 단계 (GW Agent 확장이 같이 돎 · 섀도 10:40·15:40 · 책상 보는 간격 5분)");
const A = simulate({ ...BASE, H: 5 * MIN, ext: true, cfg: { reads: "shadow", shadow: { kinds: ["recv", "orders", "xfer", "sets", "menu", "gross"], times: ["10:40", "15:40"] } } });
console.log(`   섀도 ${A.shadowRuns}번 끝남 (${DAYS * 2}번 가운데) · 맞춰 보기 통과 ${A.shadowOk}번 · 멈춤 ${A.M.stops}번 · 책상이 시트에 쓴 것: ${JSON.stringify(A.M.posts)}`);
ok(A.M.badPost.length === 0, "섀도: 책상은 aside 로 시작하는 칸에만 씀 (진짜 요청·자료 칸 0건)" + (A.M.badPost.length ? " · " + [...new Set(A.M.badPost)].join(",") : ""));
ok(A.M.reqInSkip === 0, "섀도: 발주 시간대(12:30~14:45)에 낸 요청 0건");
ok(A.M.stuck.filter((x) => x.startsWith("asidePush")).length === 0, "섀도: 25분 넘게 갇힌 섀도 요청 0건" + (A.M.stuck.length ? "\n     " + A.M.stuck.join("\n     ") : ""));
ok(A.shadowRuns >= DAYS * 2 * 0.7, `섀도: 정한 차례의 70% 넘게 끝까지 돎 (${pct(A.shadowRuns, DAYS * 2)})`);
ok(A.orders.done === A.orders.n, `섀도: 폰 전송 ${A.orders.n}건은 확장이 그대로 처리 (${A.orders.done}건)`);

// ---- B) 실제 단계: 확장을 끄고 어사이드가 다 맡음 — 책상 보는 간격을 바꿔 가며 ----
console.log("\nB) 실제 단계 (확장 없음 · 읽기·발주 모두 어사이드)");
console.log("   간격    Gross 정오 전   메뉴 정오 전   12·16·20시   폰 전송(2분 안)   폰 불러오기(가운데)   어사이드가 움직인 횟수/일   시트 전체 읽기/일   멈춤");
const rows = [];
for (const H of [1, 3, 5, 10, 15]) {
  const r = simulate({ ...BASE, H: H * MIN, ext: false, cfg: { reads: "live", orders: "live" } }); rows.push([H, r]);
  console.log(`   ${String(H).padStart(2)}분    ${pct(r.gross.onTime, DAYS - 1).padStart(6)}        ${pct(r.menu.onTime, DAYS - 1).padStart(6)}       ${pct(r.slotHit, r.slotN).padStart(6)}       ${(r.orders.fast + "/" + r.orders.n).padStart(7)}          ${String(r.press.medMin == null ? "-" : r.press.medMin + "분").padStart(8)}             ${String(Math.round(r.M.agentActs / DAYS * 10) / 10).padStart(6)}               ${String(Math.round(r.M.fullReads / DAYS)).padStart(5)}        ${r.M.stops}`);
}
const B5 = rows.find(([h]) => h === 5)[1];
ok(rows.every(([, r]) => r.M.reqInSkip === 0), "실제: 발주 시간대에 책상이 낸 읽기 요청 0건 (모든 간격)");
ok(rows.every(([, r]) => r.M.concurrent === 0), "실제: 읽는 중에 새 요청을 겹쳐 낸 일 0건");
ok(rows.every(([, r]) => r.M.stuck.length === 0), "실제: 25분 넘게 갇힌 요청 0건 (못 하면 오류를 적어 폰이 풀림)" + (rows.some(([, r]) => r.M.stuck.length) ? "\n     " + rows.flatMap(([h, r]) => r.M.stuck.map((x) => h + "분 | " + x)).slice(0, 12).join("\n     ") : ""));
ok(rows.every(([, r]) => r.orders.open === 0), "실제: 폰 전송이 답 없이 남은 일 0건 (저장 완료 또는 '직접 넣어 주세요')");
ok(rows.every(([, r]) => Math.max(...Object.values(r.M.posts)) / DAYS < 200), "실제: 책상이 시트에 쓰는 횟수가 하루 200번 아래");
ok(B5.gross.onTime >= (DAYS - 1) * 0.8, `실제(5분): Gross 가 다음 날 정오 전에 들어온 날 ${pct(B5.gross.onTime, DAYS - 1)} (지금 GW Agent 실적은 36%)`);

// ---- C) 같은 매장 사정에서 확장만 돌 때 (견줄 기준) ----
const C = simulate({ ...BASE, H: 5 * MIN, ext: true, cfg: { reads: "off", orders: "off" } });
console.log(`\nC) 견줄 기준 — 같은 사정에서 확장만: Gross 정오 전 ${pct(C.gross.onTime, DAYS - 1)} · 메뉴 ${pct(C.menu.onTime, DAYS - 1)} · 12·16·20시 ${pct(C.slotHit, C.slotN)} · 폰 전송 ${C.orders.done}/${C.orders.n}`);
ok(Object.keys(C.M.posts).length === 0, "꺼짐: 책상은 여러 날 동안 시트에 한 번도 안 씀");

// ---- D) 나쁜 날: 어사이드가 자주 못 함(30%) · 읽기 실패 30% ----
const Dd = simulate({ ...BASE, H: 5 * MIN, pMiss: 0.3, pReadFail: 0.3, ext: false, cfg: { reads: "live", orders: "live" } });
console.log(`\nD) 나쁜 날(어사이드 못 함 30% · 읽기 실패 30%): Gross 정오 전 ${pct(Dd.gross.onTime, DAYS - 1)} · 12·16·20시 ${pct(Dd.slotHit, Dd.slotN)} · 멈춤 ${Dd.M.stops}번 · 갇힌 요청 ${Dd.M.stuck.length}건 · 답 없는 폰 전송 ${Dd.orders.open}건`);
ok(Dd.M.stuck.length === 0 && Dd.orders.open === 0 && Dd.M.concurrent === 0 && Dd.M.reqInSkip === 0, "나쁜 날에도 갇힘·겹침·발주 시간대 요청이 없음" + (Dd.M.stuck.length ? "\n     " + Dd.M.stuck.slice(0, 8).join("\n     ") : ""));

console.log(fails ? `\n일정 되돌려 보기: 실패 ${fails}건` : "\n일정 되돌려 보기: 모두 통과");
process.exit(fails ? 1 : 0);
