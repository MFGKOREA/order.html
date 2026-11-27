// 되돌려 보기 ③ "AI가 화면 숫자를 직접 읽어 옮기면" 어떻게 되나 — 코드로 읽기(시작 코드 방식)와 견줄 근거
//  어사이드가 표를 보고 옮겨 적는다고 치고, 칸 하나를 틀릴 확률 p 를 바꿔 가며 여러 번 돌려 봄(지어낸 실수).
//  잡는 방법 세 가지를 견줌: ① 모양 검사만 ② 합계 줄 대조(수량 합) ③ 두 번 읽어 같을 때만 넣기
//  p 는 가정임(어사이드의 실제 값은 기능 시험 4번 '표 옮겨 넣기'로 잼). 표 크기는 진짜 시트 사본이 있으면 그 줄 수를 씀
//  사용: node aside/test/bt/readerr.mjs [kv.json(저장소 밖)] [--runs 4000]
import fs from "fs";
import { createRequire } from "module";
createRequire(import.meta.url)("../../verify-core.js");
const V = globalThis.AsideVerify;
const file = process.argv[2] && !process.argv[2].startsWith("--") ? process.argv[2] : null;
const RUNS = +(process.argv[process.argv.indexOf("--runs") + 1] || 0) || 4000;
let s = 11; const rnd = () => { s = (s + 0x6d2b79f5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };

// 표 만들기: 진짜 사본이 있으면 최근 31일 입고 줄(값은 찍지 않고 계산에만 씀), 없으면 지어낸 300줄
let rows;
if (file) {
  const raw = JSON.parse(fs.readFileSync(file, "utf8")), d = raw.data || raw;
  const days = Object.keys(d).filter((k) => /^misRecv\.\d{4}-\d\d-\d\d$/.test(k)).sort().slice(-31);
  rows = days.flatMap((k) => (d[k].rows || []).map((r) => ({ code: String(r.code), name: String(r.name || ""), qty: +r.qty, unit: String(r.unit || "") })));
}
if (!rows || rows.length < 50) rows = Array.from({ length: 300 }, (_, i) => ({ code: String(900001 + i * 7), name: "시험품목" + i, qty: Math.round(rnd() * 400) / (rnd() < 0.3 ? 10 : 1) + 1, unit: "EA" }));
const N = rows.length, band = N < 200 ? "200줄 아래" : N < 500 ? "200~500줄" : N < 1000 ? "500~1,000줄" : "1,000줄 넘음";
console.log(`표 크기: 입고현황 31일 치 ${file ? "(진짜 줄 수 · " + band + ")" : "(지어낸 300줄)"} · 칸 ${N * 4}개 · ${RUNS}번씩 돌림\n`);

const digit = () => String(Math.floor(rnd() * 10));
const garble = (v) => { const t = String(v); if (!t.length) return "x"; const i = Math.floor(rnd() * t.length), c = /\d/.test(t[i]) ? digit() : "x"; return t.slice(0, i) + (c === t[i] ? (c === "9" ? "0" : "9") : c) + t.slice(i + 1); };
// AI 가 한 번 읽음: 칸마다 p 로 한 글자 틀림, 줄마다 p/2 로 빠짐, p/4 로 두 번
function read(src, p) {
  const out = [];
  for (const r of src) {
    if (rnd() < p / 2) continue;
    const x = { code: rnd() < p ? garble(r.code) : r.code, name: rnd() < p ? garble(r.name) : r.name, qty: rnd() < p ? parseFloat(garble(r.qty)) || 0 : r.qty, unit: rnd() < p ? garble(r.unit) : r.unit };
    out.push(x); if (rnd() < p / 4) out.push({ ...x });
  }
  return out;
}
const key = (rs) => rs.map((r) => V.stable(r)).sort().join("\n");
const sum = (rs) => Math.round(rs.reduce((a, r) => a + (isFinite(r.qty) ? r.qty : 0), 0) * 1000) / 1000;
const TRUE = key(rows), SUM = sum(rows);
const shapeBad = (rs) => V.shapeCheck("misRecv.2026-11-01", { rows: rs.map((r) => ({ ...r, ...(r.qty < 0 ? { ret: 1 } : {}) })) }).length > 0;

console.log("칸 하나 틀릴 확률   한 번 읽어 틀린 표   모양 검사 뒤에도   합계 대조 뒤에도   두 번 읽어 같을 확률   두 번 같아서 넣었는데 틀림");
console.log("(가정)              (그대로 넣으면)      틀린 채 들어감      틀린 채 들어감      (못 맞추면 그날 못 넣음)");
for (const p of [0.0002, 0.001, 0.005, 0.01, 0.02]) {
  let wrong = 0, afterShape = 0, afterSum = 0, agree = 0, agreeWrong = 0;
  const runs = N > 600 ? Math.min(RUNS, 1500) : RUNS;
  for (let i = 0; i < runs; i++) {
    const a = read(rows, p), ka = key(a), bad = ka !== TRUE;
    if (bad) { wrong++; if (!shapeBad(a)) afterShape++; if (sum(a) === SUM) afterSum++; }
    const b = read(rows, p);
    if (key(b) === ka) { agree++; if (bad) agreeWrong++; }
  }
  const f = (x) => (x / runs * 100).toFixed(x / runs < 0.01 && x ? 2 : 1).padStart(5) + "%";
  console.log(`   ${(p * 100).toFixed(2).padStart(5)}%            ${f(wrong)}              ${f(afterShape)}             ${f(afterSum)}              ${f(agree)}                  ${f(agreeWrong)}`);
}

// 작은 값 하나(오늘 지금까지 Gross: 숫자 7~8자리 하나)는 사정이 다름
console.log("\n작은 값 하나(오늘 Gross 숫자 한 칸)일 때");
for (const p of [0.001, 0.01, 0.02]) {
  let wrong = 0, agree = 0, agreeWrong = 0;
  for (let i = 0; i < 200000; i++) { const a = rnd() < p ? garble(4567800) : "4567800", b = rnd() < p ? garble(4567800) : "4567800"; if (a !== "4567800") wrong++; if (a === b) { agree++; if (a !== "4567800") agreeWrong++; } }
  console.log(`   칸 틀릴 확률 ${(p * 100).toFixed(1)}% → 한 번 읽어 틀림 ${(wrong / 2000).toFixed(2)}% · 두 번 읽어 같을 확률 ${(agree / 2000).toFixed(1)}% · 같아서 넣었는데 틀림 ${(agreeWrong / 2000).toFixed(4)}%`);
}
console.log("\n읽는 법: '한 번 읽어 틀린 표'가 높으면 그대로 넣을 수 없고, '두 번 읽어 같을 확률'이 낮으면 두 번 읽기로도 그날 값을 못 넣음.");
console.log("코드로 읽기(시작 코드)는 화면의 줄 자료를 그대로 가져오므로 옮겨 적는 실수가 없음 — 섀도로 GW Agent 값과 같음을 확인함.");
