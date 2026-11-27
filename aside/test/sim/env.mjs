// 시험 환경: 가짜 MIS(label-list 의 시험용 화면) + 가짜 발주 시트(진짜 Code.gs 를 node 에서 돌림) + 진짜 읽기 코드(mis-sales.js)
//  진짜 시트·MIS·GW 에는 아무 요청도 나가지 않음(모든 주소를 브라우저 안에서 가로챔). 자료는 지어낸 것만 씀
//  label-list 사본이 있어야 함: LABEL_LIST=/path/to/label-list (기본 ../../../../mfgkorea/label-list 또는 /home/user/mfgkorea/label-list)
import fs from "fs";
import path from "path";
import { fileURLToPath, pathToFileURL } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO = path.resolve(HERE, "../../..");
export const LL = [process.env.LABEL_LIST, path.resolve(REPO, "../mfgkorea/label-list"), path.resolve(REPO, "../label-list"), "/home/user/mfgkorea/label-list"].filter(Boolean).find((p) => fs.existsSync(path.join(p, "mis-sales.js")));
if (!LL) { console.log("건너뜀: label-list 사본이 없음 (LABEL_LIST=경로 로 알려 주세요)"); process.exit(0); }
const req = (m) => import(m).catch(() => import("/opt/node22/lib/node_modules/" + m + "/index.mjs"));
const { chromium } = await req("playwright");
const { load } = await import(pathToFileURL(path.join(LL, "order-src/test/gas/sim.mjs")).href);

export const MOCK = path.join(LL, "order-src/test/gw/mock");
// 발주 시트 주소는 이 저장소에 적지 않음 → label-list 코드에 있는 것을 읽어 씀
export const ORDER_API = (/const API = "([^"]+)"/.exec(fs.readFileSync(path.join(LL, "mis-agent.js"), "utf8")) || [])[1] || "";
const ORDER_PATH = ORDER_API ? new URL(ORDER_API).pathname : "";
export const kday = (ms) => new Date(ms + 9 * 3600e3).toISOString().slice(0, 10);
export const addDay = (d, n) => new Date(Date.parse(d + "T00:00:00Z") + n * 864e5).toISOString().slice(0, 10);

const TYPES = { ".js": "text/javascript; charset=utf-8", ".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".css": "text/css" };
const serve = (root) => (r) => {
  const u = new URL(r.request().url()), rel = decodeURIComponent(u.pathname).replace(/^\/(label-list|order\.html)\//, "/");
  const f = path.join(root, rel);
  if (!f.startsWith(root) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) return r.fulfill({ status: 404, body: "not found" });
  r.fulfill({ status: 200, contentType: TYPES[path.extname(f)] || "application/octet-stream", body: fs.readFileSync(f), headers: { "Access-Control-Allow-Origin": "*" } });
};

// 시트가 "정상"으로 보이게 채워 둠(품목 60개 · Forecast 60일 · 메뉴 40일) — 자동 판단(autoPlan)이 빈 시트로 보고 멈추지 않게. 모두 지어낸 값
export function seed(gas, today) {
  const set = (key, value) => gas.post({ action: "set", key, value });
  set("master.order", { rows: Array.from({ length: 60 }, (_, i) => ({ name: "시험품목" + (i + 1), code: String(900001 + i), vendor: i % 5 === 4 ? "새싹농산" : "온세물류", unit: "EA", group: "" })) });
  const fc = {}; for (let i = 1; i < 60; i++) fc[addDay(today, -i)] = { fc: "100", act: "90" };
  set("forecast", fc);
  for (let i = 1; i <= 40; i++) set("menuDay." + addDay(today, -i), { at: 1, rows: [{ c: "x", m: "a", q: 1 }] });
  for (let i = 0; i < 30; i++) set("pad" + i, 1);
}

export async function start(o = {}) {
  const gas = load(path.join(LL, "apps-script/order/Code.gs"));
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const ctx = await browser.newContext({ timezoneId: "Asia/Seoul" });
  const pushes = [], hits = { sheetGet: 0, sheetPost: 0 }, swap = {};
  let net = true; // false 면 시트 요청이 실패(인터넷 끊김 흉내)
  await ctx.route("https://script.google.com/**", async (r) => {
    const q = r.request(), u = new URL(q.url());
    if (!net) return r.abort();
    if (u.pathname !== ORDER_PATH) { pushes.push(JSON.parse(q.postData() || "{}")); return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ sent: 1 }) }); }
    let body;
    if (q.method() === "GET") { hits.sheetGet++; body = gas.get(Object.fromEntries(u.searchParams)); } else { hits.sheetPost++; body = gas.post(JSON.parse(q.postData())); }
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body), headers: { "Access-Control-Allow-Origin": "*" } });
  });
  await ctx.route("https://mis.test/**", (r) => { const n = new URL(r.request().url()).pathname.slice(1); r.fulfill({ path: path.join(MOCK, swap[n] || n) }); });
  await ctx.route("https://mfgkorea.github.io/label-list/**", serve(LL));
  await ctx.route("https://mfgkorea.github.io/order.html/**", serve(REPO));
  // 읽기 코드의 기다림을 시험용으로 줄임 (label-list 시험과 같은 값)
  await ctx.addInitScript((t) => { window.__salesTest = t; }, o.salesTest || { q: 8000, emptyWait: 1200, retry: [300, 600], progEvery: 1500 });
  const data = () => gas.get({ api: "1" }).data;
  const set = (key, value) => gas.post({ action: "set", key, value });
  // 가짜 MIS 첫 화면을 열고 스크립트 한 줄을 넣음 = 어사이드가 "시작 코드"를 실행한 것과 같음
  const inject = async (page, src, opt) => {
    const p = await ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(e.message)); p.on("dialog", (d) => d.accept());
    await p.goto("https://mis.test/" + page); await p.waitForTimeout(250);
    if (opt) await p.evaluate((x) => { window.__asideOpt = x; }, opt);
    await p.evaluate((s) => { const e = document.createElement("script"); e.charset = "utf-8"; e.src = s + (s.includes("?") ? "&" : "?") + "t=" + Date.now(); document.body.appendChild(e); }, src);
    p.__errs = errs; return p;
  };
  // "GW Agent 가 읽었다" 흉내: 진짜 읽기 코드를 salesPush 요청으로 그대로 돌림
  const gwRead = async (job, page) => {
    set("salesPush", { id: Date.now(), at: Date.now(), status: "pending", ...job });
    const p = await inject(page, "https://mfgkorea.github.io/label-list/mis-sales.js?quiet=1");
    for (let i = 0; i < 160 && /pending|running/.test(data().salesPush.status); i++) await p.waitForTimeout(250);
    await p.close(); return data();
  };
  // 어사이드 흉내: 시작 코드를 넣고 끝날 때까지 기다림 → 시작 코드의 상태
  const asideRun = async (page, mode, extra = {}) => {
    const p = await inject(page, `https://mfgkorea.github.io/order.html/aside/starter.js?mode=${mode}${extra.job ? "&job=" + extra.job : ""}`, extra.opt);
    for (let i = 0; i < 240; i++) { if (await p.evaluate(() => !!(window.__asideStarter && window.__asideStarter.done)).catch(() => false)) break; await p.waitForTimeout(250); }
    const st = await p.evaluate(() => { const s = window.__asideStarter || {}; return { phase: s.phase, text: s.text, ok: s.ok, done: s.done, summary: s.summary, suppressed: s.suppressed, captures: (s.captures || []).map((c) => c.key), badge: (document.getElementById("asideBadge") || {}).textContent || "", title: document.title }; });
    st.errs = p.__errs;
    if (extra.keep) st.page = p; else await p.close();
    return st;
  };
  return { gas, browser, ctx, data, set, inject, gwRead, asideRun, pushes, hits, swap, net: (v) => { net = v; }, stop: () => browser.close() };
}

export function checker() {
  let fails = 0, oks = 0;
  const ok = (c, m) => { console.log((c ? "통과 " : "실패 ") + m); if (c) oks++; else fails++; };
  const done = (name) => { console.log(`\n${name}: ${fails ? `실패 ${fails}건` : "모두 통과"} (${oks + fails}개)`); return fails; };
  return { ok, done };
}
