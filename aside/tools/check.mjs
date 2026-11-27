#!/usr/bin/env node
// 검증 도구 (클로드 코드가 씀): 시트 사본 받기 · 사본 두 개 비교 · 기준선 · 섀도 결과 보기
//  출력은 건수·시각·키 이름만. 매출·수량 같은 값은 찍지 않음 (허브가 공개 저장소)
//  시트 사본(kv.json)은 매장 자료 → 이 저장소 안에는 저장하지 못하게 막음
// 사용:
//   node aside/tools/check.mjs snap <저장할 파일(저장소 밖)>     시트 전체를 받아 둠 (읽기만)
//   node aside/tools/check.mjs status                              시트 상태만 (요청·소식 시각)
//   node aside/tools/check.mjs baseline <kv.json> [--days 21]      GW Agent 기준선: 어제 자료가 다음 날 몇 시에 들어왔나 + 모양 검사
//   node aside/tools/check.mjs compare <a.json> <b.json> [--from YYYY-MM-DD] [--to YYYY-MM-DD]
//   node aside/tools/check.mjs shadow <kv.json>                    섀도 결과(asideShadow)를 날짜별로
//  발주 시트 주소: 환경 변수 ASIDE_API, 없으면 label-list 사본(LABEL_LIST 또는 ../mfgkorea/label-list)의 코드에서 찾음. 잠겨 있으면 ASIDE_KEY
import fs from "fs";
import path from "path";
import { createRequire } from "module";
import { fileURLToPath } from "url";
const require = createRequire(import.meta.url), HERE = path.dirname(fileURLToPath(import.meta.url)), REPO = path.resolve(HERE, "../..");
require("../verify-core.js");
const V = globalThis.AsideVerify;
const [cmd, ...rest] = process.argv.slice(2);
const flag = (n, d) => { const i = rest.indexOf("--" + n); return i >= 0 ? rest[i + 1] : d; };
const args = rest.filter((a, i) => !a.startsWith("--") && !(i > 0 && rest[i - 1].startsWith("--")));
const die = (m) => { console.error(m); process.exit(2); };
const kst = (ms) => (ms ? new Date(ms + 9 * 3600e3).toISOString().slice(0, 16).replace("T", " ") : "-");

function api() {
  if (process.env.ASIDE_API) return process.env.ASIDE_API;
  const LL = [process.env.LABEL_LIST, path.resolve(REPO, "../mfgkorea/label-list"), path.resolve(REPO, "../label-list")].filter(Boolean).find((p) => fs.existsSync(path.join(p, "mis-agent.js")));
  const m = LL && /const API = "([^"]+)"/.exec(fs.readFileSync(path.join(LL, "mis-agent.js"), "utf8"));
  if (!m) die("발주 시트 주소를 못 찾음: ASIDE_API 또는 LABEL_LIST 를 알려 주세요");
  return m[1];
}
const withKey = (u) => u + (process.env.ASIDE_KEY ? "&k=" + encodeURIComponent(process.env.ASIDE_KEY) : "");
const load = (f) => { const j = JSON.parse(fs.readFileSync(f, "utf8")); return j.data || j; };

if (cmd === "snap") {
  const out = path.resolve(args[0] || die("저장할 파일을 알려 주세요 (저장소 밖)"));
  if (out.startsWith(REPO + path.sep)) die("시트 사본은 이 저장소 안에 두지 않습니다 (공개 저장소). 다른 폴더를 써 주세요");
  const j = await (await fetch(withKey(api() + "?api=1&t=" + Date.now()))).json();
  if (!j || !j.ok || !j.data) die("시트를 못 읽음" + (j && j.auth ? " (가게 키 필요: ASIDE_KEY)" : ""));
  fs.writeFileSync(out, JSON.stringify({ at: Date.now(), data: j.data }));
  console.log(`받음: 키 ${Object.keys(j.data).length}개 · ${kst(Date.now())} → ${out}`);
} else if (cmd === "status") {
  const j = await (await fetch(withKey(api() + "?api=1&status=1&t=" + Date.now()))).json(), s = (j && j.status) || {}, now = Date.now();
  const ago = (t) => (t ? Math.round((now - t) / 60e3) + "분 전" : "-");
  console.log(`잠김: ${j.locked ? "예" : "아니오"} · 배포본 ${j.build || "-"}`);
  console.log(`매출 요청(salesPush): ${(s.salesPush || {}).status || "없음"} · 요청 ${ago((s.salesPush || {}).at)}`);
  console.log(`발주 전송(misPush): ${(s.misPush || {}).status || "없음"} · ${(s.misPush || {}).date || "-"}`);
  console.log(`매장 PC 소식(misAgent): ${ago((s.misAgent || {}).at)} · ${(s.misAgent || {}).ver || "-"} · ${(s.misAgent || {}).mode || ""}`);
  console.log(`진단(gwDiag): ${(s.gwDiag || {}).code || "없음"} · ${ago((s.gwDiag || {}).at)}`);
} else if (cmd === "baseline") {
  const d = load(args[0] || die("kv.json 을 알려 주세요")), days = +flag("days", 21);
  console.log(`시트 키 ${Object.keys(d).length}개`);
  // 1) 묶음별 날 수와 모양 검사
  const fams = {};
  Object.keys(d).forEach((k) => { const m = /^(misRecv|misOrder|misXfer|menuDay|setDay|lineCheck)\.\d{4}-\d\d-\d\d$/.exec(k); if (!m) return; const f = fams[m[1]] || (fams[m[1]] = { n: 0, bad: 0, first: k.slice(-10), last: k.slice(-10), why: {} }); f.n++; if (k.slice(-10) < f.first) f.first = k.slice(-10); if (k.slice(-10) > f.last) f.last = k.slice(-10); const e = V.shapeCheck(k, d[k]); if (e.length) { f.bad++; const w = e[0].replace(/\d+번째 줄 /, ""); f.why[w] = (f.why[w] || 0) + 1; } });
  console.log("\n묶음        날 수   모양 틀림   기간");
  Object.keys(fams).sort().forEach((f) => console.log(`${f.padEnd(10)} ${String(fams[f].n).padStart(5)} ${String(fams[f].bad).padStart(9)}   ${fams[f].first} ~ ${fams[f].last}${fams[f].bad ? "   까닭: " + JSON.stringify(fams[f].why) : ""}`));
  const fe = V.shapeCheck("forecast", d.forecast); console.log(`forecast   ${String(Object.keys(d.forecast || {}).length).padStart(5)} ${String(fe.length).padStart(9)}`);
  // 2) 도착 지연: 그날이 끝난 뒤 몇 시간 만에 처음 들어왔나 (menuDay·setDay 는 처음 받을 때만 씀)
  console.log(`\n도착 지연 (최근 ${days}일 · 그날 자정부터 처음 들어올 때까지, 시간)`);
  for (const fam of ["menuDay", "setDay"]) {
    const r = V.lagReport(d, { family: fam, days });
    console.log(`${fam.padEnd(8)} 받은 날 ${r.n}/${r.span} · 빈 날 ${r.missing} · 가운데 ${r.medianH}h · 90% ${r.p90H}h · 가장 늦음 ${r.maxH}h · 다음 날 정오 넘김 ${r.late}일`);
    if (rest.includes("--list")) console.log("   " + r.days.map((x) => `${x.d.slice(5)}:${x.h}h`).join(" "));
  }
  // 3) 하루 한 번 읽기의 마지막 기록
  console.log("\n읽은 기록 (마지막으로 읽은 때 · 어디까지)");
  for (const k of ["misRecvScan", "misOrderScan", "misXferScan", "misSetScan", "hourShare", "gwScout", "nowSales", "setNow", "menuNow"]) { const v = d[k]; if (v) console.log(`${k.padEnd(13)} ${kst(v.at)} ${v.to ? "· ~" + v.to : v.day ? "· " + v.day : ""}`); else console.log(`${k.padEnd(13)} 없음`); }
  const snaps = Object.keys(d).filter((k) => /^daySnap\./.test(k)).sort(); console.log(`마감 기록(daySnap) ${snaps.length}일${snaps.length ? " · " + snaps[0].slice(-10) + " ~ " + snaps[snaps.length - 1].slice(-10) : ""}`);
} else if (cmd === "compare") {
  const a = load(args[0] || die("사본 두 개를 알려 주세요")), b = load(args[1] || die("사본 두 개를 알려 주세요"));
  const r = V.compareSnap(a, b, { from: flag("from"), to: flag("to") });
  console.log("묶음        같음   다름   A에만   B에만");
  let bad = 0;
  Object.keys(r).sort().forEach((f) => { const t = r[f]; bad += t.diff; console.log(`${f.padEnd(10)} ${String(t.same).padStart(5)} ${String(t.diff).padStart(6)} ${String(t.onlyA).padStart(7)} ${String(t.onlyB).padStart(7)}${t.diffKeys.length ? "   다른 키: " + t.diffKeys.join(", ") : ""}`); });
  process.exit(bad ? 1 : 0);
} else if (cmd === "shadow") {
  const d = load(args[0] || die("kv.json 을 알려 주세요")), runs = ((d.asideShadow || {}).runs) || {};
  const ids = Object.keys(runs).sort();
  if (!ids.length) console.log("섀도 기록 없음");
  ids.forEach((id) => { const r = runs[id]; console.log(`${kst(r.at)} ${String(r.kind || "").padEnd(7)} ${r.ok ? "통과" : "확인"} · 같음 ${r.same} · 다름 ${r.nDiff} · 없음 ${r.nMiss}${r.today && r.today.n ? ` · 오늘 값 ${r.today.ok}/${r.today.n}` : ""} · ${Math.round(r.ms / 1000)}초${r.why ? " · " + r.why : ""}${r.nDiff ? "\n   다른 키: " + r.diff.join(", ") : ""}`); });
  const ok = ids.filter((id) => runs[id].ok).length; console.log(`\n합계: ${ids.length}번 중 통과 ${ok}번`);
} else {
  console.log(fs.readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n").filter((l) => l.startsWith("//")).slice(0, 12).join("\n"));
}
