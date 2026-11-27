// 되돌려 보기 ① 실제 시트 자료로: 맞춰 보기(섀도)가 진짜 자료 모양에서 ① 같은 것을 다르다고 하지 않는지 ② 틀린 것을 다 잡는지
//  + GW Agent 의 지금 실적(기준선): 어제 자료가 다음 날 정오 전에 들어온 날이 며칠인가
//  사용: node aside/test/bt/real.mjs <kv.json(저장소 밖 · aside/tools/check.mjs snap 으로 받음)>
//  출력은 건수·비율·시각만. 매출·수량·품목 이름은 찍지 않음
import fs from "fs";
import path from "path";
import { createRequire } from "module";
import { fileURLToPath } from "url";
const require = createRequire(import.meta.url), HERE = path.dirname(fileURLToPath(import.meta.url)), REPO = path.resolve(HERE, "../../..");
require("../../verify-core.js"); require("../../desk-core.js");
const V = globalThis.AsideVerify, D = globalThis.AsideDesk;
const file = process.argv[2];
if (!file) { console.log("건너뜀: kv.json 을 알려 주세요 (node aside/tools/check.mjs snap <저장소 밖 파일>)"); process.exit(0); }
const raw = JSON.parse(fs.readFileSync(file, "utf8")), d = raw.data || raw, snapAt = raw.at || Date.now();
let seed = 7; const rnd = () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const pick = (a) => a[Math.floor(rnd() * a.length)], clone = (o) => JSON.parse(JSON.stringify(o));
let fails = 0; const ok = (c, m) => { console.log((c ? "통과 " : "실패 ") + m); if (!c) fails++; };

const FAM = ["misRecv", "misOrder", "misXfer", "menuDay", "setDay", "lineCheck"];
const keys = Object.keys(d).filter((k) => FAM.includes(k.split(".")[0]) && /\.\d{4}-\d\d-\d\d$/.test(k));
const withRows = keys.filter((k) => d[k] && Array.isArray(d[k].rows) && d[k].rows.length);
console.log(`자료: 키 ${Object.keys(d).length}개 · 날짜별 자료 ${keys.length}개(줄 있는 것 ${withRows.length}개) · 줄 ${withRows.reduce((a, k) => a + d[k].rows.length, 0)}개 · 받은 때 ${new Date(snapAt + 9 * 3600e3).toISOString().slice(0, 16).replace("T", " ")}`);

// ---- 1) 모양 검사: 진짜 자료를 틀렸다고 하지 않는지 ----
const shapeBad = keys.filter((k) => V.shapeCheck(k, d[k]).length);
ok(shapeBad.length === 0 && !V.shapeCheck("forecast", d.forecast).length, `모양 검사: 진짜 자료 ${keys.length}개 + forecast 에서 잘못 거른 것 ${shapeBad.length}개` + (shapeBad.length ? " · " + shapeBad.slice(0, 5).join(", ") : ""));

// ---- 2) 같은 것을 같다고: 쓴 시각을 바꾸고 줄 순서를 섞어도 "같음" ----
const shuffle = (a) => { const b = a.slice(); for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; };
const same = V.summarize(keys.map((k) => ({ action: "set", key: k, value: Array.isArray((d[k] || {}).rows) ? { ...clone(d[k]), at: 1, rows: shuffle(clone(d[k].rows)) } : { ...clone(d[k]), at: 1 } })), d);
ok(same.keys === keys.length && same.same === keys.length && !same.diff.length && !same.miss.length, `같은 자료 ${keys.length}개 → 같음 ${same.same} · 다름 ${same.diff.length} (잘못 울린 것 0 이어야 함)`);
// forecast 는 merge: 있는 값 그대로면 같음
const fcDays = Object.keys(d.forecast || {}).filter((x) => String((d.forecast[x] || {}).act ?? "").trim() !== "");
const fcSame = V.summarize([{ action: "merge", key: "forecast", patch: Object.fromEntries(fcDays.map((x) => [x, { act: Number(d.forecast[x].act) }])) }], d);
ok(fcSame.same === 1 && !fcSame.diff.length, `forecast 실제 칸 ${fcDays.length}일 → 같음 (글자·숫자 차이는 같은 것으로)`);

// ---- 3) 틀린 것을 다 잡는지: 진짜 줄에 실수 한 가지씩을 넣어 봄 ----
const numField = (r) => ["qty", "q", "n", "cnt"].find((f) => typeof r[f] === "number");
const MUT = {
  "수량 +1": (rows) => { const i = Math.floor(rnd() * rows.length), f = numField(rows[i]); if (!f) return null; rows[i][f] += 1; return rows; },
  "수량 자릿수 바뀜": (rows) => { const c = rows.map((r, i) => [i, numField(r)]).filter(([i, f]) => f && /\d\d/.test(String(Math.abs(rows[i][f]))) && new Set(String(Math.abs(rows[i][f])).replace(/\D/g, "")).size > 1); if (!c.length) return null; const [i, f] = pick(c), sgn = rows[i][f] < 0 ? -1 : 1, s = String(Math.abs(rows[i][f])).split(""); const p = s.findIndex((ch, x) => x < s.length - 1 && /\d/.test(ch) && /\d/.test(s[x + 1]) && ch !== s[x + 1]); if (p < 0) return null; [s[p], s[p + 1]] = [s[p + 1], s[p]]; rows[i][f] = sgn * parseFloat(s.join("")); return rows; },
  "수량 10배": (rows) => { const i = Math.floor(rnd() * rows.length), f = numField(rows[i]); if (!f || !rows[i][f]) return null; rows[i][f] *= 10; return rows; },
  "부호 바뀜": (rows) => { const i = Math.floor(rnd() * rows.length), f = numField(rows[i]); if (!f || !rows[i][f]) return null; rows[i][f] *= -1; return rows; },
  "한 줄 빠짐": (rows) => { rows.splice(Math.floor(rnd() * rows.length), 1); return rows; },
  "한 줄 두 번": (rows) => { rows.push(clone(pick(rows))); return rows; },
  "코드 한 글자": (rows) => { const c = rows.map((r, i) => i).filter((i) => typeof rows[i].code === "string" && rows[i].code.length > 1); if (!c.length) return null; const i = pick(c), s = rows[i].code.split(""), p = Math.floor(rnd() * s.length); s[p] = s[p] === "7" ? "1" : "7"; rows[i].code = s.join(""); return rows; },
  "두 줄 수량 맞바뀜": (rows) => { if (rows.length < 2) return null; const i = Math.floor(rnd() * rows.length); let j = Math.floor(rnd() * rows.length); if (j === i) j = (i + 1) % rows.length; const f = numField(rows[i]), g = numField(rows[j]); if (!f || !g || rows[i][f] === rows[j][g]) return null; [rows[i][f], rows[j][g]] = [rows[j][g], rows[i][f]]; return rows; },
  "이름 한 글자": (rows) => { const c = rows.map((r, i) => i).filter((i) => ["name", "m"].some((f) => typeof rows[i][f] === "string" && rows[i][f].length > 1)); if (!c.length) return null; const i = pick(c), f = typeof rows[i].name === "string" && rows[i].name.length > 1 ? "name" : "m"; rows[i][f] = rows[i][f].slice(0, -1) + (rows[i][f].slice(-1) === "x" ? "y" : "x"); return rows; },
};
console.log("\n실수 종류            넣은 수   잡은 수   모양 검사만으로 잡은 수");
let allIn = 0, allHit = 0;
for (const [name, fn] of Object.entries(MUT)) {
  let n = 0, hit = 0, shape = 0;
  for (const k of withRows) for (let rep = 0; rep < 3; rep++) {
    const rows = fn(clone(d[k].rows)); if (!rows) continue;
    if (V.stable(V.norm(rows).map(V.stable).sort()) === V.stable(V.norm(d[k].rows).map(V.stable).sort())) continue; // 바꿨는데 내용이 같으면(같은 줄이 둘 등) 실수가 아님
    n++; const v = { ...clone(d[k]), at: 2, rows };
    if (V.cmpSet(v, d[k]).r !== "same") hit++;
    if (V.shapeCheck(k, v).length) shape++;
  }
  allIn += n; allHit += hit;
  console.log(`${name.padEnd(14, "　")} ${String(n).padStart(7)} ${String(hit).padStart(8)} ${String(shape).padStart(10)}`);
}
ok(allIn > 500 && allHit === allIn, `넣은 실수 ${allIn}건 가운데 맞춰 보기가 잡은 것 ${allHit}건 (${(allHit / allIn * 100).toFixed(1)}%)`);

// ---- 4) GW Agent 의 지금 실적(기준선) ----
console.log("\n기준선: 어제 자료가 처음 들어온 때 (그날 자정부터, 시간) — 최근 14일");
for (const fam of ["menuDay", "setDay"]) {
  const r = V.lagReport(d, { family: fam, days: 14, now: snapAt });
  const onTime = r.days.filter((x) => x.h <= 12).length;
  console.log(`${fam.padEnd(8)} 다음 날 정오 전 ${onTime}/${r.span}일 (${Math.round(onTime / r.span * 100)}%) · 늦음 ${r.late}일 · 아직 없음 ${r.missing}일 · 가운데 ${r.medianH}h · 가장 늦음 ${r.maxH}h`);
}
const T = D.ymd(snapAt), back = (n) => new Date(Date.parse(T + "T00:00:00Z") - n * 864e5).toISOString().slice(0, 10);
const missAct = []; for (let i = 1; i <= 14; i++) { const a = (d.forecast[back(i)] || {}).act; if (a == null || ["", "0"].includes(String(a).trim())) missAct.push(back(i).slice(5)); }
console.log(`Gross 실제 칸이 빈 날(최근 14일): ${missAct.length}일${missAct.length ? " · " + missAct.join(" ") : ""}`);
const ageH = (k) => (d[k] && d[k].at ? Math.round((snapAt - d[k].at) / 3600e3) : null);
console.log("마지막으로 읽은 지: " + ["misRecvScan", "misOrderScan", "misXferScan", "misSetScan", "nowSales", "setNow", "menuNow"].map((k) => `${k} ${ageH(k) == null ? "없음" : ageH(k) + "h"}`).join(" · "));
console.log(`마감 기록(daySnap): ${Object.keys(d).filter((k) => /^daySnap\./.test(k)).length}일치 (11/17부터 매일이어야 함)`);

// ---- 5) 지금 시트에서 책상이 무엇을 시킬지 (쓰지 않고 판단만) ----
const LL = [process.env.LABEL_LIST, path.resolve(REPO, "../mfgkorea/label-list"), path.resolve(REPO, "../label-list")].filter(Boolean).find((p) => fs.existsSync(path.join(p, "gw-agent/periodic.js")));
if (LL) {
  require(path.join(LL, "gw-agent/auto.js")); require(path.join(LL, "gw-agent/periodic.js"));
  const plan = JSON.parse(fs.readFileSync(path.join(LL, "gw-plan.json"), "utf8"));
  const light = { salesPush: { ...(d.salesPush || {}), status: "done" }, misPush: d.misPush, misAgent: { at: 0 } };
  console.log("\n지금 시트로 판단만 해 봄 (아침 10:40 이라 치고, 시트에는 안 씀)");
  const now = Date.parse(T + "T10:40:00+09:00");
  for (const [name, cfg] of [["꺼짐", undefined], ["섀도(입고·주문·이동·세트·메뉴·Gross)", { reads: "shadow", shadow: { kinds: ["recv", "orders", "xfer", "sets", "menu", "gross"], times: ["10:40"] } }], ["실제", { reads: "live", orders: "live" }]]) {
    let r = D.decide({ now, cfg, st: {}, light, full: d, fullAt: now, plan });
    if (r.wantFull) r = D.decide({ now, cfg, st: r.st, light, full: d, fullAt: now, plan });
    const posts = r.acts.filter((a) => a.type === "post").map((a) => a.body.key + (a.body.value && a.body.value.kind ? `(${a.body.value.kind}${a.body.value.also ? "+" + Object.keys(a.body.value.also).join("+") : ""})` : ""));
    console.log(`  ${name}: ${r.instr.code} · ${r.instr.why} · 시트에 쓸 것: ${posts.join(", ") || "없음"}`);
    if (name === "꺼짐") ok(r.instr.code === "IDLE" && !posts.length, "꺼져 있으면 진짜 시트에서도 쓸 것이 없음");
    if (name.startsWith("섀도")) ok(r.instr.code === "READ" && posts.every((p) => /^aside/.test(p)), "섀도는 aside 로 시작하는 칸에만 씀");
  }
}
console.log(fails ? `\n실제 자료 되돌려 보기: 실패 ${fails}건` : "\n실제 자료 되돌려 보기: 모두 통과");
process.exit(fails ? 1 : 0);
