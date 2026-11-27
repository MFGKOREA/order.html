// 시작 코드(starter.js) 시험: 확장 없이 "시작 코드 한 줄"만으로 읽기가 되는지, 섀도가 시트를 건드리지 않고 맞춰 보는지
//  사용: node aside/test/sim/e2e-starter.mjs
import { start, checker, kday } from "./env.mjs";
const { ok, done } = checker();
const E = await start();
const D = () => E.data();
const famKeys = (fam) => Object.keys(D()).filter((k) => k.startsWith(fam + ".")).sort();
const snap = (fam) => JSON.stringify(famKeys(fam).map((k) => [k, D()[k]]));
const shadowReq = (job) => E.set("asidePush", { id: Date.now(), at: Date.now(), status: "pending", src: "aside-shadow", ...job });

// ---- 1) 섀도 · 입고현황: GW Agent 가 읽어 둔 값과 같으면 "같음", 시트는 그대로 ----
let d = await E.gwRead({ kind: "recv", from: "2026-11-01", to: "2026-11-12" }, "recv-main.html");
ok(d.salesPush.status === "done" && famKeys("misRecv").length > 0, `준비: GW Agent 흉내로 입고현황 ${famKeys("misRecv").length}일 읽어 둠`);
const before = snap("misRecv"), spBefore = JSON.stringify(D().salesPush), scanBefore = JSON.stringify(D().misRecvScan);
shadowReq({ kind: "recv", from: "2026-11-01", to: "2026-11-12" });
let r = await E.asideRun("recv-main.html", "shadow");
ok(r.done && r.ok === true && /같음 \d+ · 다름 0 · 없음 0/.test(r.text), "섀도 입고현황 끝 · " + r.text);
ok(r.summary && r.summary.same === famKeys("misRecv").length && r.summary.keys === r.summary.same, `같음 ${r.summary && r.summary.same}건 = 시트의 입고 날 수 ${famKeys("misRecv").length}`);
ok(snap("misRecv") === before && JSON.stringify(D().misRecvScan) === scanBefore, "섀도는 misRecv·misRecvScan 을 한 글자도 안 바꿈");
ok(JSON.stringify(D().salesPush) === spBefore, "섀도는 진짜 요청 칸(salesPush)을 안 건드림");
ok(D().asidePush.status === "done" && /입고현황/.test(D().asidePush.text || ""), "섀도 요청 칸(asidePush)에 결과가 적힘 · " + D().asidePush.text);
const run1 = (D().asideShadow || {}).runs || {}, one = run1[Object.keys(run1)[0]] || {};
ok(Object.keys(run1).length === 1 && one.ok === true && one.kind === "recv" && one.nDiff === 0, "asideShadow 에 요약 한 줄 (건수·키 이름만)");
ok(!/"qty"|"rows"/.test(JSON.stringify(D().asideShadow)), "요약에 수량·줄 내용이 없음");
ok(/\[어사이드 끝\]/.test(r.title) && /섀도/.test(r.badge), "화면 배지·탭 제목으로 끝남을 알림 · " + r.badge);
ok(!r.errs.length, "화면 오류 없음" + (r.errs.length ? " · " + r.errs[0] : ""));

// ---- 2) 섀도가 다름을 잡는지: 시트 값 하루를 일부러 바꿔 둠 ----
const k0 = famKeys("misRecv").find((k) => D()[k].rows.length), orig = D()[k0];
E.set(k0, { at: orig.at, rows: orig.rows.map((x, i) => (i === 0 ? { ...x, qty: x.qty + 1 } : x)) });
shadowReq({ kind: "recv", from: "2026-11-01", to: "2026-11-12" });
r = await E.asideRun("recv-main.html", "shadow");
ok(r.ok === false && r.summary.nDiff === 1 && r.summary.diff[0].startsWith(k0), `수량 1 다른 하루를 잡음 · ${r.text} · ${r.summary.diff[0]}`);
// 하루치가 통째로 없을 때
E.gas.post({ action: "set", key: k0, value: null });
const gone = D()[k0] == null;
shadowReq({ kind: "recv", from: "2026-11-01", to: "2026-11-12" });
r = await E.asideRun("recv-main.html", "shadow");
ok(gone && r.ok === true && r.summary.nMiss === 1 && r.summary.miss[0] === k0, `시트에 없는 날은 "없음"으로 따로 셈 · ${r.text}`);
E.set(k0, orig);

// ---- 3) 요청이 없으면 아무것도 안 함 ----
E.set("asidePush", { id: 1, at: 1, status: "done" });
r = await E.asideRun("recv-main.html", "shadow");
ok(r.ok === true && /할 일 없음/.test(r.text) && !r.captures.length, "대기 요청이 없으면 '할 일 없음' · 화면을 안 건드림");

// ---- 4) 실제(live) · 입고현황: 시작 코드 한 줄로 읽기 코드가 그대로 돎 ----
const eBefore = famKeys("misRecv").length;
for (const k of famKeys("misRecv")) E.gas.post({ action: "set", key: k, value: null });
E.set("salesPush", { id: Date.now(), at: Date.now(), status: "pending", kind: "recv", from: "2026-11-01", to: "2026-11-12", src: "aside" });
r = await E.asideRun("recv-main.html", "live");
ok(r.ok === true && r.text === "성공" && D().salesPush.status === "done", "실제 입고현황 끝 · " + D().salesPush.text);
ok(famKeys("misRecv").length === eBefore && snap("misRecv").replace(/"at":\d+/g, "") === before.replace(/"at":\d+/g, ""), "실제로 쓴 값이 GW Agent 흉내와 같음 (쓴 시각만 다름)");
ok(!r.captures.length && r.summary === null, "실제 방식은 아무것도 가로채지 않음");

// ---- 5) 섀도 · 다른 종류들: 주문현황 · 매장간재고이동 · Set판매현황(force) · 메뉴 판매(force) · Gross ----
const kinds = [
  ["orders", { kind: "orders", from: "2026-11-01", to: "2026-11-12" }, "order-main.html", "misOrder"],
  ["xfer", { kind: "xfer", from: "2026-11-01", to: "2026-11-16" }, "xfer-main.html", "misXfer"],
  ["sets", { kind: "sets", from: "2026-11-11", to: "2026-11-14", force: 1 }, "sets-main.html", "setDay"],
  ["menu", { kind: "menu", from: "2026-10-19", to: "2026-10-25", force: 1 }, "sales-main.html", "menuDay"],
];
for (const [name, job, page, fam] of kinds) {
  d = await E.gwRead(job, page);
  const n = Object.keys(d).filter((k) => k.startsWith(fam + ".") && k.slice(-10) >= job.from && k.slice(-10) <= job.to).length, b4 = snap(fam);
  shadowReq(job);
  r = await E.asideRun(page, "shadow");
  ok(d.salesPush.status === "done" && r.ok === true && r.summary.nDiff === 0 && r.summary.same >= 1 && snap(fam) === b4, `섀도 ${name}: ${r.text} (GW Agent 흉내 ${n}일) · 시트 그대로`);
}
// 시간대별 매출(hourShare 한 칸) · MIS 메뉴 살펴보기(기록만 남김)
d = await E.gwRead({ kind: "hour", from: "2026-11-12", to: "2026-11-12" }, "hour-main.html");
const hsB = JSON.stringify(D().hourShare);
shadowReq({ kind: "hour", from: "2026-11-12", to: "2026-11-12" });
r = await E.asideRun("hour-main.html", "shadow");
ok(d.salesPush.status === "done" && hsB && r.ok === true && r.summary.nDiff === 0 && r.summary.same === 1 && JSON.stringify(D().hourShare) === hsB, `섀도 hour: ${r.text} · hourShare 그대로`);
d = await E.gwRead({ kind: "scout" }, "scout-main.html");
const scB = JSON.stringify(D().gwScout);
shadowReq({ kind: "scout" });
r = await E.asideRun("scout-main.html", "shadow");
ok(d.salesPush.status === "done" && r.ok === true && r.captures.includes("gwScout") && JSON.stringify(D().gwScout) === scB, `섀도 scout: 끝까지 돎 · gwScout 그대로 (기록 칸은 같음/다름으로 세지 않음)`);
// Gross: 읽기 코드가 스스로 견줘서 같은 날은 안 씀 → 쓸 게 없으면 다름 0
d = await E.gwRead({ from: "2026-10-20", to: "2026-10-24" }, "sales-main.html");
const fcB = JSON.stringify(D().forecast);
shadowReq({ from: "2026-10-20", to: "2026-10-24" });
r = await E.asideRun("sales-main.html", "shadow");
ok(d.salesPush.status === "done" && r.ok === true && r.summary.nDiff === 0 && JSON.stringify(D().forecast) === fcB, `섀도 Gross: ${r.text} · forecast 그대로`);
// Gross 가 다르면: 시트의 하루 값을 바꿔 두면 읽기 코드가 고치려 함 → 섀도는 쓰지 않고 "다름"
const fc = D().forecast, day = "2026-10-22";
E.set("forecast", { ...fc, [day]: { ...fc[day], act: String(Math.round(parseFloat(fc[day].act) * 1.5)) } });
const fcC = JSON.stringify(D().forecast);
shadowReq({ from: "2026-10-20", to: "2026-10-24" });
r = await E.asideRun("sales-main.html", "shadow");
ok(r.ok === false && r.summary.nDiff === 1 && JSON.stringify(D().forecast) === fcC, `섀도 Gross: 시트 값이 다른 하루를 "다름"으로 · 시트는 안 고침 · ${r.text}`);
E.set("forecast", fc);

// ---- 6) 섀도 · 라인체크: 직원 폰 알림을 보내지 않음 ----
const T = kday(Date.now());
E.set("lineCheckCfg", { time: "00:00", secs: { FOH: 1, BOH2: 1, BOH: 0 } });
// 6-1) GW Agent 가 아직 안 읽은 때: 읽기 코드는 알림을 보내려 함 → 섀도는 막음
const push0 = E.pushes.length;
shadowReq({ kind: "linecheck", to: T });
r = await E.asideRun("lc-main.html", "shadow");
ok(r.done && E.pushes.length === push0 && r.suppressed >= 1, `섀도에서는 알림을 한 건도 안 보냄 (막은 요청 ${r.suppressed}건) · ${r.text}`);
ok(!(("lineCheck." + T) in D()) && r.summary.nMiss === 1, "섀도는 라인체크 기록도 시트에 안 씀 (시트에 없으니 '없음' 1)");
// 6-2) GW Agent 가 읽은 뒤: 같은 값
d = await E.gwRead({ kind: "linecheck", to: T }, "lc-main.html");
const pushB = E.pushes.length, lcB = JSON.stringify(D()["lineCheck." + T]);
ok(d.salesPush.status === "done" && pushB > push0 && lcB, `준비: GW Agent 흉내가 라인체크를 읽고 알림 ${pushB - push0}건을 보냄`);
shadowReq({ kind: "linecheck", to: T });
r = await E.asideRun("lc-main.html", "shadow");
ok(r.done && E.pushes.length === pushB && JSON.stringify(D()["lineCheck." + T]) === lcB, `섀도 라인체크(읽은 뒤): ${r.text} · 알림·기록 그대로` + (r.summary.nDiff ? " · 다름: " + r.summary.diff.join(",") : ""));
// 6-3) 오늘 중간값(지금까지 Gross): 값은 시각마다 달라 같음/다름으로 세지 않고 모양만 봄
E.set("lineCheckCfg", { time: "23:59", secs: { FOH: 1, BOH2: 1, BOH: 0 } });
d = await E.gwRead({ kind: "now", from: "2026-10-24", to: "2026-10-24", today: 1 }, "sales-main.html");
const nowB = JSON.stringify(D().nowSales);
shadowReq({ kind: "now", from: "2026-10-24", to: "2026-10-24", today: 1 });
r = await E.asideRun("sales-main.html", "shadow");
ok(d.salesPush.status === "done" && r.ok === true && r.summary.today.n >= 1 && r.summary.today.ok === r.summary.today.n && JSON.stringify(D().nowSales) === nowB, `섀도 오늘 값: ${r.text} · nowSales 그대로`);

// ---- 7) 발주는 섀도로 하지 않음 ----
r = await E.asideRun("main.html", "shadow", { job: "order" });
ok(r.ok === false && /섀도로 하지 않/.test(r.text), "발주(order)는 섀도에서 거절");

await E.stop();
process.exit(done("시작 코드 시험") ? 1 : 0);
