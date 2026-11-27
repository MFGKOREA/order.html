// 책상 화면 + 시작 코드 + 읽기 코드를 한꺼번에 돌려 보는 시험. "어사이드"는 책상 화면의 글만 보고 움직이는 가짜 손으로 흉내 냄:
//   READ → MIS 첫 화면을 열고 책상의 '시작 코드'를 실행 · ARM → 주문등록 화면에서 실행 · CLOSE → 읽기 탭 닫기 · 그 밖에는 아무것도 안 함
//  화면 시계는 한국 시각 10:39(발주 시간대 밖)로 맞춰 돌림. 진짜 시트·MIS 에는 아무 요청도 안 나감
//  사용: node aside/test/sim/e2e-desk.mjs
import { start, checker, seed, kday } from "./env.mjs";
const { ok, done } = checker();
const E = await start();
const D = () => E.data(), sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// 화면 시계: 오늘 10:39:40 (한국)
const T = kday(Date.now()), OFF = Date.parse(T + "T10:39:40+09:00") - Date.now();
await E.ctx.addInitScript((off) => { const RD = Date; class SD extends RD { constructor(...a) { if (a.length) super(...a); else super(RD.now() + off); } static now() { return RD.now() + off; } } window.Date = SD; }, OFF);
const vnow = () => Date.now() + OFF;
// 이 PC 한도: 시험하는 책상은 "실제까지" 허락된 매장 PC 라고 침 (맨 끝에서 허락 안 한 PC 도 따로 봄)
await E.ctx.addInitScript(() => { try { if (location.pathname.endsWith("/desk.html") && !/nocap/.test(location.search)) localStorage.setItem("asideCap", "live"); } catch (e) {} });
seed(E.gas, T);
const LIM = { fullRun: 2000, closeShow: 4000, deskBeat: 60e3 };

// 가짜 어사이드: 책상 글을 보고만 움직임. lazy = 시작 코드를 안 돌리는 어사이드
async function aside(desk, page, o = {}) {
  const seen = []; let mis = null, armed = null, stop = false;
  const loop = (async () => {
    while (!stop) {
      const code = await desk.evaluate(() => document.getElementById("instr").dataset.code).catch(() => "");
      if (code && seen[seen.length - 1] !== code) seen.push(code);
      if (code === "READ" && !mis && !o.lazy) {
        mis = await E.ctx.newPage(); mis.on("dialog", (d) => d.accept());
        await mis.goto("https://mis.test/" + page); await mis.waitForTimeout(250);
        const js = await desk.evaluate(() => document.getElementById("code").value);
        await mis.evaluate(js); // 어사이드가 '시작 코드'를 실행
      }
      if (code === "ARM" && !armed) {
        armed = await E.ctx.newPage(); armed.on("dialog", (d) => d.accept());
        await armed.goto("https://mis.test/main.html");
        if (o.master) await armed.evaluate((m) => { window.__master = m; window.__saved = {}; }, o.master);
        await armed.waitForTimeout(400);
        await armed.evaluate(await desk.evaluate(() => document.getElementById("code").value));
      }
      if (code === "CLOSE" && mis) { await mis.close(); mis = null; }
      await sleep(300);
    }
  })();
  return { seen, armedPage: () => armed, end: async () => { stop = true; await loop; if (mis) await mis.close(); if (armed) await armed.close(); } };
}
const openDesk = async () => { const p = await E.ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(e.message)); await p.goto("https://mfgkorea.github.io/order.html/aside/desk.html?tick=1500&fresh=1"); p.__errs = errs; return p; };
const until = async (fn, ms = 60e3) => { const t = Date.now(); while (Date.now() - t < ms) { if (await fn()) return true; await sleep(300); } return false; };
const codeOf = (desk) => desk.evaluate(() => document.getElementById("instr").dataset.code);
const stOf = (desk) => desk.evaluate(() => window.__desk.state().st);

// ---- A) 섀도 · 입고현황 한 바퀴 ----
await E.gwRead({ kind: "recv", from: "2026-11-01", to: "2026-11-12" }, "recv-main.html"); // GW Agent 가 읽어 둔 값
const recvB = JSON.stringify(Object.keys(D()).filter((k) => k.startsWith("misRecv.")).sort().map((k) => D()[k]));
const spB = JSON.stringify(D().salesPush);
E.set("asideCfg", { reads: "shadow", shadow: { kinds: ["recv"], times: ["10:40"] }, lim: LIM });
let desk = await openDesk(), A = await aside(desk, "recv-main.html");
ok(await until(async () => (await codeOf(desk)) === "READ", 60e3), "섀도: 10:40 이 되자 책상이 '읽기 시작'을 띄움");
ok((await desk.evaluate(() => document.getElementById("code").value)).includes("starter.js?mode=shadow"), "시작 코드는 섀도용");
ok(await until(async () => A.seen.includes("CLOSE"), 90e3), "섀도: 읽기 시작 → 기다림 → 탭 닫기 · 본 글: " + A.seen.join(" → "));
ok(await until(async () => (await codeOf(desk)) === "IDLE", 30e3), "섀도: 끝난 뒤 '할 일 없음'");
let s = await stOf(desk), runs = (D().asideShadow || {}).runs || {};
ok(s.shadowLast && s.shadowLast.nDiff === 0 && s.shadowLast.same >= 1 && s.fails === 0, `섀도 결과: 같음 ${s.shadowLast && s.shadowLast.same} · 다름 ${s.shadowLast && s.shadowLast.nDiff} · 실패 0`);
ok(Object.keys(runs).length === 1 && D().asidePush.status === "done", "시트에 섀도 요약 한 줄 · 섀도 요청 done");
ok(JSON.stringify(Object.keys(D()).filter((k) => k.startsWith("misRecv.")).sort().map((k) => D()[k])) === recvB && JSON.stringify(D().salesPush) === spB, "진짜 자료(misRecv)·진짜 요청 칸은 그대로");
ok(D().asideDesk && D().asideDesk.reads === "shadow", "책상이 살아 있다는 소식(asideDesk)을 적음");
await sleep(4000);
ok(Object.keys((D().asideShadow || {}).runs || {}).length === 1, "같은 날 같은 시각에 두 번 돌리지 않음");
ok(!desk.__errs.length, "책상 화면 오류 없음" + (desk.__errs.length ? " · " + desk.__errs[0] : ""));
await A.end(); await desk.close();

// ---- B) 어사이드가 시작 코드를 안 돌리면: 책상이 요청에 오류를 적고 실패로 셈 ----
E.set("asideCfg", { reads: "shadow", shadow: { kinds: ["recv"], times: ["10:40"] }, lim: { ...LIM, pickup: 6000 } });
desk = await openDesk();
await desk.evaluate(() => { localStorage.removeItem("asideDeskSt"); }); await desk.reload();
A = await aside(desk, "recv-main.html", { lazy: true });
ok(await until(async () => A.seen.includes("READ") && A.seen.includes("CLOSE"), 60e3), "게으른 어사이드: 읽기 시작 → (안 함) → 책상이 접음 · " + A.seen.join(" → "));
s = await stOf(desk);
ok(s.fails === 1 && D().asidePush.status === "error" && /시작 못 함/.test(D().asidePush.text), "요청 칸에 '시작 못 함' · 실패 1번 · " + D().asidePush.text);
await A.end(); await desk.close();

// ---- C) 실제(live) · 폰에서 온 요청 ----
E.set("asideCfg", { reads: "live", lim: LIM });
for (const k of Object.keys(D()).filter((x) => x.startsWith("misRecv."))) E.gas.post({ action: "set", key: k, value: null });
E.gas.post({ action: "set", key: "misAgent", value: null });
// 하루 한 번 일은 이미 받아 둔 것으로(상시 수집이 끼어들지 않게) — 끼어드는 경우는 되돌려 보기(bt)에서 따로 봄
const VT0 = kday(vnow());
for (const k of ["hourShare", "misOrderScan", "misRecvScan", "misXferScan", "misSetScan"]) E.set(k, { at: vnow(), to: VT0 });
E.set("gwScout", { at: vnow(), menus: [] });
desk = await openDesk();
await until(async () => !!(await codeOf(desk)), 20e3); await sleep(2500);
ok((await codeOf(desk)) === "IDLE", "실제: 받을 것이 없으면 '할 일 없음' · " + (await desk.evaluate(() => document.getElementById("iWhy").textContent)));
A = await aside(desk, "recv-main.html");
E.set("salesPush", { id: vnow(), at: vnow(), status: "pending", kind: "recv", from: "2026-11-01", to: "2026-11-12" });
ok(await until(async () => A.seen.includes("CLOSE"), 90e3), "실제: 들어온 요청 → 읽기 시작 → 탭 닫기 · " + A.seen.join(" → "));
ok(D().salesPush.status === "done" && Object.keys(D()).filter((k) => k.startsWith("misRecv.")).length === 12, "실제: 요청 done · 입고현황 12일이 시트에 들어감 · " + D().salesPush.text);
ok((D().misAgent || {}).ver === "aside-desk 1", "실제: 책상이 'PC 대기 중' 소식(misAgent)을 적음");
// 확장이 켜져 있는 흔적이 보이면 물러섬
E.set("misAgent", { at: vnow(), mode: "ondemand", ver: "1.17.7", auto: 1 });
ok(await until(async () => (await codeOf(desk)) === "STOP", 30e3), "실제: GW Agent 확장 소식이 보이면 '멈춤'");
await A.end(); await desk.close();

// ---- D) 발주(orders live): 대기 탭 켜기 → 폰 전송 → 입력·저장 ----
const GRP = { "온세물류": "46492", "새싹농산": "49212" }, rows = D()["master.order"].rows;
const master = rows.map((r) => ({ code: r.code, grp: GRP[r.vendor] }));
const VT = kday(vnow());
E.set("input." + VT, { "시험품목1": { s: "1", o: "3" }, "시험품목2": { s: "2", o: "5" }, "시험품목5": { s: "0", o: "2" }, "시험품목7": { s: "4", o: "" } });
E.gas.post({ action: "set", key: "misAgent", value: null });
E.set("asideCfg", { orders: "live", lim: LIM });
desk = await openDesk();
A = await aside(desk, "main.html", { master });
ok(await until(async () => A.seen.includes("ARM"), 30e3), "발주: 책상이 '발주 대기 켜기'를 띄움");
ok(await until(async () => (D().misAgent || {}).grid === true, 40e3), "발주: 대기 탭이 켜져 소식을 적음 (주문등록 화면)");
ok(await until(async () => (await codeOf(desk)) === "IDLE", 30e3), "발주: 대기 탭이 살아 있으면 '할 일 없음'");
E.set("misPush", { date: VT, id: vnow(), at: vnow(), status: "pending" });
ok(await until(async () => /done|error/.test((D().misPush || {}).status || ""), 90e3), "발주: 폰 전송을 대기 탭이 받아 처리 · " + (D().misPush || {}).status + " · " + String((D().misPush || {}).text || "").split("\n")[0]);
const saved = await A.armedPage().evaluate(() => window.__saved);
ok(D().misPush.status === "done" && saved["46492"] && saved["46492"]["900001"] === 3 && saved["46492"]["900002"] === 5 && saved["49212"] && saved["49212"]["900005"] === 2, "발주: 가짜 MIS 에 수량이 맞게 저장됨 " + JSON.stringify(saved));
ok(!A.seen.includes("READ"), "발주만 켠 설정에서는 읽기를 시키지 않음");
await A.end(); await desk.close();

// ---- E) 허락 안 한 PC(폰·집 PC·남)에서 책상을 열면: 보기만, 시트에 아무것도 안 씀 ----
E.set("asideCfg", { reads: "shadow", shadow: { kinds: ["recv"], times: ["10:40"] }, lim: LIM });
E.gas.post({ action: "set", key: "asidePush", value: null }); E.gas.post({ action: "set", key: "asideDesk", value: null });
const guest = await E.ctx.newPage();
await guest.goto("https://mfgkorea.github.io/order.html/aside/desk.html?tick=1500&fresh=1&nocap=1");
await guest.evaluate(() => { localStorage.removeItem("asideCap"); }); await guest.reload();
const postsB = E.hits.sheetPost; await sleep(6000);
ok((await codeOf(guest)) === "IDLE" && E.hits.sheetPost === postsB && !D().asidePush && !D().asideDesk, "허락 안 한 PC: 섀도 설정이어도 '할 일 없음' · 시트 쓰기 0번");
ok(/보기만/.test(await guest.evaluate(() => document.getElementById("cCap").textContent)), "허락 안 한 PC: '이 PC 보기만' 표시 · " + (await guest.evaluate(() => document.getElementById("cCap").textContent)));
await guest.close();

await E.stop();
process.exit(done("책상 화면 시험") ? 1 : 0);
