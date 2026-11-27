// 책상 판단(desk-core.js) 시험 — node --test aside/test/
//  label-list 사본이 있으면 진짜 판단 함수(auto.js·periodic.js)로, 없으면 그 부분은 건너뜀
import test from "node:test";
import assert from "node:assert/strict";
import fs from "fs";
import path from "path";
import { createRequire } from "module";
import { fileURLToPath } from "url";
const require = createRequire(import.meta.url), HERE = path.dirname(fileURLToPath(import.meta.url)), REPO = path.resolve(HERE, "../..");
require("../desk-core.js");
const LL = [process.env.LABEL_LIST, path.resolve(REPO, "../mfgkorea/label-list"), path.resolve(REPO, "../label-list"), "/home/user/mfgkorea/label-list"].filter(Boolean).find((p) => fs.existsSync(path.join(p, "gw-agent/periodic.js")));
if (LL) { require(path.join(LL, "gw-agent/auto.js")); require(path.join(LL, "gw-agent/periodic.js")); }
const D = globalThis.AsideDesk, MIN = 60e3;
const at = (day, hhmm) => Date.parse(`${day}T${hhmm}:00+09:00`);
const posts = (r, key) => r.acts.filter((a) => a.type === "post" && (!key || a.body.key === key)).map((a) => a.body);
// 여러 번 이어 부르기: 책상 화면이 하는 것처럼 st 를 다음 차례로 넘김
const runner = (cfg) => { let st = {}; return (now, more = {}) => { const r = D.decide({ now, cfg, st, light: {}, ...more }); st = r.st; return r; }; };

test("꺼져 있으면 아무것도 쓰지 않음", () => {
  const go = runner(undefined);
  for (let i = 0; i < 50; i++) { const r = go(at("2026-11-30", "10:00") + i * 20e3); assert.equal(r.instr.code, "IDLE"); assert.equal(posts(r).length, 0); }
});

test("설정은 정해진 값만 받음", () => {
  const c = D.mergeCfg({ reads: "everything", orders: "live", shadow: { kinds: ["recv", "rm -rf", "menu"], times: ["9:5", "25:99x", "15:40"], slotMin: 5 }, lim: { pickup: -1, run: 5 * MIN } });
  assert.equal(c.reads, "off"); assert.equal(c.orders, "live");
  assert.deepEqual(c.shadow.kinds, ["recv", "menu"]); assert.deepEqual(c.shadow.times, ["15:40"]);
  assert.equal(c.shadow.slotMin, 180); assert.equal(c.lim.pickup, 10 * MIN); assert.equal(c.lim.run, 5 * MIN);
});

test("이 PC 한도: 시트 설정이 무엇이든 허락한 데까지만", () => {
  const live = { reads: "live", orders: "live", shadow: { kinds: ["recv"] } };
  assert.deepEqual([D.clampCfg(live, "off").reads, D.clampCfg(live, "off").orders], ["off", "off"]);
  assert.deepEqual([D.clampCfg(live, "shadow").reads, D.clampCfg(live, "shadow").orders], ["shadow", "off"]);
  assert.deepEqual([D.clampCfg(live, "live").reads, D.clampCfg(live, "live").orders], ["live", "live"]);
  assert.deepEqual([D.clampCfg(live, undefined).reads, D.clampCfg(live, "zzz").orders], ["off", "off"]);
  assert.equal(D.clampCfg({ reads: "shadow" }, "live").reads, "shadow"); assert.deepEqual(D.clampCfg(live, "shadow").shadow, { kinds: ["recv"] });
  assert.equal(D.clampCfg(undefined, "live").reads, "off");
});

test("섀도 요청 모양: 어제까지 · 메뉴/세트는 다시 읽기(force) · Gross 는 이번 주 월요일부터", () => {
  const now = at("2026-11-26", "10:40"); // 목요일
  const r = D.shadowBundle(now, ["recv", "menu", "sets", "gross", "now", "zzz", "recv"]);
  assert.equal(r.kind, "now"); assert.equal(r.status, "pending"); assert.equal(r.src, "aside-shadow"); assert.equal(r.today, 1);
  assert.deepEqual(Object.keys(r.also).sort(), ["gross", "menu", "recv", "sets"]);
  assert.deepEqual([r.also.menu.from, r.also.menu.to, r.also.menu.force], ["2026-11-25", "2026-11-25", 1]);
  assert.deepEqual([r.also.gross.from, r.also.gross.to], ["2026-11-23", "2026-11-25"]);
  const g = D.shadowBundle(now, ["gross", "recv"]);
  assert.equal(g.kind, undefined); assert.equal(g.from, "2026-11-23"); assert.ok(g.also.recv);
  assert.equal(D.shadowBundle(now, ["zzz"]), null);
});

test("섀도: 정한 시각에 한 번 요청 → 읽기 시작 → 기다림 → 탭 닫기 → 하루 한 번만", () => {
  const cfg = { reads: "shadow", shadow: { kinds: ["recv"], times: ["10:40"] } }, go = runner(cfg), day = "2026-11-30";
  let r = go(at(day, "10:30")); assert.equal(r.instr.code, "IDLE"); assert.match(r.instr.why, /다음 섀도 10:40/); assert.equal(posts(r, "asidePush").length, 0);
  // GW Agent 가 읽는 중이면 기다림
  r = go(at(day, "10:40"), { light: { salesPush: { id: 1, at: at(day, "10:39"), status: "running", startAt: at(day, "10:39") } } });
  assert.equal(r.instr.code, "IDLE"); assert.match(r.instr.why, /GW Agent 가 읽는 중/); assert.equal(posts(r, "asidePush").length, 0);
  r = go(at(day, "10:41")); assert.equal(posts(r, "asidePush").length, 0, "3분 뒤에 다시 봄");
  r = go(at(day, "10:44"));
  const req = posts(r, "asidePush")[0].value;
  assert.equal(r.instr.code, "READ"); assert.equal(r.instr.mode, "shadow"); assert.equal(req.kind, "recv"); assert.equal(req.status, "pending");
  assert.equal(posts(r, "salesPush").length, 0, "진짜 요청 칸은 안 건드림");
  const t1 = at(day, "10:45");
  r = go(t1, { full: { asidePush: { ...req, status: "running", startAt: t1 } }, fullAt: t1 }); assert.equal(r.instr.code, "WAIT");
  const t2 = at(day, "10:47");
  r = go(t2, { full: { asidePush: { ...req, status: "done", doneAt: t2 }, asideShadow: { runs: { [req.id]: { ok: true, same: 31, nDiff: 0, nMiss: 0, kind: "recv" } } } }, fullAt: t2 });
  assert.equal(r.instr.code, "CLOSE"); assert.match(r.instr.why, /같음 31 · 다름 0/); assert.equal(r.st.fails, 0); assert.equal(r.st.shadowLast.same, 31);
  r = go(at(day, "10:50")); assert.equal(r.instr.code, "IDLE"); assert.match(r.instr.why, /오늘 섀도 끝/);
  r = go(at(day, "12:00")); assert.equal(posts(r, "asidePush").length, 0, "같은 날 다시 요청하지 않음");
  r = go(at("2026-12-01", "10:40")); assert.equal(posts(r, "asidePush").length, 1, "다음 날 다시");
});

test("섀도: 발주 시간대(12:30~14:45)와 발주 전송 중에는 요청하지 않음", () => {
  const go = runner({ reads: "shadow", shadow: { kinds: ["recv"], times: ["12:20"], slotMin: 200 } }), day = "2026-11-30";
  let r = go(at(day, "12:35")); assert.equal(posts(r).filter((b) => b.key === "asidePush").length, 0); assert.match(r.instr.why, /발주 시간대/);
  r = go(at(day, "14:46"), { light: { misPush: { date: day, id: 5, at: at(day, "14:45"), status: "running" } } }); assert.equal(posts(r, "asidePush").length, 0); assert.match(r.instr.why, /발주 전송 중/);
  r = go(at(day, "14:50")); assert.equal(posts(r, "asidePush").length, 1);
});

test("어사이드가 시작 코드를 안 돌리면 10분 뒤 요청에 오류를 적고, 3번 잇달아 실패하면 멈춤 → 1시간 쉬고 한 번 다시 → 또 실패하면 2시간", () => {
  const go = runner({ reads: "shadow", shadow: { kinds: ["recv"], times: ["08:00", "09:00", "10:00", "12:00", "15:00"], slotMin: 60 } }), day = "2026-11-30";
  const once = (hhmm) => {
    const t = at(day, hhmm); let r = go(t); const req = posts(r, "asidePush")[0].value;
    r = go(t + 5 * MIN, { full: { asidePush: req }, fullAt: t + 5 * MIN }); assert.equal(r.instr.code, "READ");
    r = go(t + 11 * MIN, { full: { asidePush: req }, fullAt: t + 11 * MIN });
    const e = posts(r, "asidePush")[0]; assert.equal(e.action, "merge"); assert.equal(e.patch.status, "error"); assert.match(e.patch.text, /10분 안에 시작 못 함/);
    return r;
  };
  let r = once("08:00"); assert.equal(r.st.fails, 1); assert.equal(r.instr.code, "CLOSE");
  r = once("09:00"); assert.equal(r.st.fails, 2);
  r = once("10:00"); assert.equal(r.st.fails, 3); assert.ok(r.st.stop); assert.equal(posts(r, "asideDiag").length, 1);
  r = go(at(day, "10:30")); assert.equal(r.instr.code, "STOP"); assert.match(r.instr.why, /잇달아 3번 실패.*60분 쉬고/);
  r = go(at(day, "11:05")); assert.equal(r.instr.code, "STOP", "쉬는 동안에는 아무것도 안 시킴"); assert.equal(posts(r, "asidePush").length, 0);
  r = once("12:00"); assert.equal(r.st.fails, 3, "쉰 뒤 한 번 해 보고 또 실패 → 바로 다시 멈춤"); assert.match(r.st.stop.why, /120분 쉬고/);
  r = go(at(day, "13:59")); assert.equal(r.instr.code, "STOP");
  // 쉰 뒤 성공하면 실패 횟수 0
  const t = at(day, "15:00"); r = go(t); const req = posts(r, "asidePush")[0].value;
  r = go(t + 3 * MIN, { full: { asidePush: { ...req, status: "done", doneAt: t + 3 * MIN }, asideShadow: { runs: { [req.id]: { ok: true, same: 5, nDiff: 0, nMiss: 0 } } } }, fullAt: t + 3 * MIN });
  assert.equal(r.st.fails, 0); assert.equal(r.st.stop, null);
});

test("어사이드가 [막힘]을 누르면 하던 일을 접고 멈춤 · 쉬는 시간 뒤 스스로 다시", () => {
  const cfg = { reads: "live" }, t = at("2026-11-30", "10:00"), sp = { id: 7, at: t, status: "pending" };
  let r = D.decide({ now: t, cfg, st: {}, light: { salesPush: sp } }); assert.equal(r.instr.code, "READ");
  const k = D.stuck(r.st, t + MIN, "GW 가 안 열림 (인터넷·VPN)", cfg);
  assert.equal(k.st.run, null); assert.deepEqual(k.posts.map((b) => b.key), ["salesPush", "asideDiag"]);
  assert.equal(k.posts[0].patch.status, "error", "하던 요청은 오류로 풀어 폰이 갇히지 않게"); assert.equal(k.posts[1].value.code, "stuck");
  r = D.decide({ now: t + 2 * MIN, cfg, st: k.st, light: { salesPush: sp } }); assert.equal(r.instr.code, "STOP"); assert.match(r.instr.why, /GW 가 안 열림/);
  // 쉬는 동안 들어온 새 요청: 3분 뒤 오류를 적어 풀어 줌 (한 번만)
  const sp2 = { id: 8, at: t + 10 * MIN, status: "pending" };
  r = D.decide({ now: t + 11 * MIN, cfg, st: r.st, light: { salesPush: sp2 } }); assert.equal(posts(r, "salesPush").length, 0);
  r = D.decide({ now: t + 14 * MIN, cfg, st: r.st, light: { salesPush: sp2 } }); assert.match(posts(r, "salesPush")[0].patch.text, /쉬는 중/);
  r = D.decide({ now: t + 15 * MIN, cfg, st: r.st, light: { salesPush: sp2 } }); assert.equal(posts(r, "salesPush").length, 0);
  r = D.decide({ now: t + 62 * MIN, cfg, st: r.st, light: { salesPush: { id: 9, at: t + 61 * MIN, status: "pending" } } }); assert.equal(r.instr.code, "READ", "1시간 뒤 새 요청은 다시 받음");
});

test("내 요청이 시트에 안 보이면 남의 요청 칸에 오류를 적지 않음", () => {
  const go = runner({ reads: "live" }), day = "2026-11-30", t = at(day, "10:00");
  let r = go(t, { light: { salesPush: { id: 7, at: t - MIN, status: "pending" } } }); assert.equal(r.instr.code, "READ");
  // 그새 다른(끝난) 요청으로 바뀌어 보임
  r = go(t + 3 * MIN, { light: { salesPush: { id: 99, at: t - 60 * MIN, status: "done", doneAt: t - 50 * MIN } } });
  assert.equal(posts(r, "salesPush").length, 0); assert.equal(r.instr.code, "CLOSE"); assert.match(r.instr.why, /시트에 안 보임/);
});

test("실제(live): 들어온 요청 → 읽기 시작 → 기다림 → 탭 닫기 · 같은 요청은 한 번만", () => {
  const go = runner({ reads: "live" }), day = "2026-11-30", t = at(day, "10:00"), sp = { id: 7, at: t - MIN, status: "pending" };
  let r = go(t, { light: { salesPush: sp } }); assert.equal(r.instr.code, "READ"); assert.equal(r.instr.mode, "live");
  assert.equal(posts(r, "misAgent").length, 1, "폰에 'PC 대기 중'이 보이게 소식을 적음");
  r = go(t + MIN, { light: { salesPush: { ...sp, status: "running", startAt: t + MIN } } }); assert.equal(r.instr.code, "WAIT");
  r = go(t + 3 * MIN, { light: { salesPush: { ...sp, status: "error", doneAt: t + 3 * MIN } } }); assert.equal(r.instr.code, "CLOSE"); assert.equal(r.st.fails, 1);
  r = go(t + 6 * MIN, { light: { salesPush: { ...sp, status: "pending" } } }); assert.notEqual(r.instr.code, "READ", "한 번 해 본 요청은 다시 안 함");
  const sp2 = { id: 8, at: t + 7 * MIN, status: "pending" };
  r = go(t + 7 * MIN, { light: { salesPush: sp2 } }); assert.equal(r.instr.code, "READ");
  r = go(t + 9 * MIN, { light: { salesPush: { ...sp2, status: "done", doneAt: t + 9 * MIN } } }); assert.equal(r.instr.code, "CLOSE"); assert.equal(r.st.fails, 0, "성공하면 실패 횟수 0");
});

test("실제(live): 도는 중에 새 요청이 들어오면 탭을 닫고 새로 시작 (실패로 세지 않음)", () => {
  const go = runner({ reads: "live" }), t = at("2026-11-30", "10:00"), a = { id: 7, at: t, status: "pending" }, b = { id: 8, at: t + 2 * MIN, status: "pending" };
  go(t, { light: { salesPush: a } });
  go(t + MIN, { light: { salesPush: { ...a, status: "running", startAt: t + MIN } } });
  let r = go(t + 2 * MIN, { light: { salesPush: b } });
  assert.equal(r.instr.code, "CLOSE"); assert.match(r.instr.why, /새 요청/); assert.equal(r.st.fails, 0); assert.equal(posts(r, "salesPush").length, 0);
  r = go(t + 2 * MIN + 10e3, { light: { salesPush: b } }); assert.equal(r.instr.code, "CLOSE", "20초는 탭 닫기를 보여 줌");
  r = go(t + 2 * MIN + 25e3, { light: { salesPush: b } }); assert.equal(r.instr.code, "READ"); assert.equal(r.st.run.id, 8);
});

test("실제(live): 읽기가 14분 넘게 안 끝나면 오류를 적어 폰이 갇히지 않게", () => {
  const go = runner({ reads: "live" }), t = at("2026-11-30", "10:00"), sp = { id: 7, at: t, status: "pending" };
  go(t, { light: { salesPush: sp } });
  go(t + MIN, { light: { salesPush: { ...sp, status: "running", startAt: t + MIN } } });
  const r = go(t + 16 * MIN, { light: { salesPush: { ...sp, status: "running", startAt: t + MIN } } });
  const e = posts(r, "salesPush")[0]; assert.equal(e.patch.status, "error"); assert.match(e.patch.text, /14분 안에 못 끝냄/); assert.equal(r.instr.code, "CLOSE");
});

test("실제(live): 오류 쓰기가 사라져(인터넷 끊김) 남은 요청·죽은 탭의 요청을 나중에 거둠", () => {
  const go = runner({ reads: "live" }), t = at("2026-11-30", "10:00"), sp = { id: 7, at: t, status: "pending" };
  go(t, { light: { salesPush: sp } });
  let r = go(t + 11 * MIN, { light: { salesPush: sp } }); assert.equal(posts(r, "salesPush").length, 1, "시작 못 함 → 오류를 씀(이 쓰기가 사라졌다고 침)");
  r = go(t + 13 * MIN, { light: { salesPush: sp } }); assert.equal(posts(r, "salesPush").length, 0);
  r = go(t + 16 * MIN, { light: { salesPush: sp } }); assert.match(posts(r, "salesPush")[0].patch.text, /받지 못함/);
  r = go(t + 17 * MIN, { light: { salesPush: sp } }); assert.equal(posts(r, "salesPush").length, 0, "한 번만");
  // 책상이 모르는 '읽는 중' 요청이 20분 넘게 그대로면 거둠
  const go2 = runner({ reads: "live" }), run = { id: 9, at: t, status: "running", startAt: t };
  r = go2(t + 10 * MIN, { light: { salesPush: run } }); assert.equal(posts(r, "salesPush").length, 0);
  r = go2(t + 20 * MIN, { light: { salesPush: run } }); assert.match(posts(r, "salesPush")[0].patch.text, /읽다가 멈춤/);
});

test("실제(live): GW Agent 확장이 아직 켜져 있으면 물러섬", () => {
  const go = runner({ reads: "live" }), t = at("2026-11-30", "10:00");
  const r = go(t, { light: { misAgent: { at: t - 2 * MIN, mode: "ondemand", ver: "1.17.7" }, salesPush: { id: 7, at: t, status: "pending" } } });
  assert.equal(r.instr.code, "STOP"); assert.match(r.instr.why, /확장이 켜져/); assert.equal(posts(r, "salesPush").length, 0); assert.equal(r.st.run, undefined);
});

test("실제(live) · 발주는 확장이 맡는 동안: 발주 전송 중이면 읽기를 쉼", () => {
  const go = runner({ reads: "live" }), day = "2026-11-30", t = at(day, "13:00");
  const r = go(t, { light: { misPush: { date: day, id: 3, at: t - MIN, status: "pending" }, salesPush: { id: 7, at: t, status: "pending" } } });
  assert.equal(r.instr.code, "IDLE"); assert.match(r.instr.why, /발주 전송 중/);
});

test("발주(orders live): 대기 탭이 꺼져 있으면 켜라고 하고, 폰이 6분 넘게 기다리면 폰에 알림", () => {
  const go = runner({ orders: "live" }), day = "2026-11-30", t = at(day, "13:00");
  let r = go(t); assert.equal(r.instr.code, "ARM"); assert.equal(r.instr.job, "order"); assert.equal(r.instr.urgent, 0);
  r = go(t + MIN, { light: { misAgent: { at: t + MIN - 30e3, grid: true, ver: "5" } } }); assert.equal(r.instr.code, "IDLE", "대기 탭이 살아 있으면 할 일 없음");
  const mp = { date: day, id: 3, at: t + 2 * MIN, status: "pending" };
  r = go(t + 7 * MIN, { light: { misPush: mp } }); assert.equal(r.instr.code, "ARM"); assert.equal(r.instr.urgent, 1); assert.equal(posts(r, "misPush").length, 0);
  r = go(t + 9 * MIN, { light: { misPush: mp } });
  const e = posts(r, "misPush")[0]; assert.equal(e.patch.status, "error"); assert.match(e.patch.text, /MIS에 직접 넣어 주세요/);
  r = go(t + 10 * MIN, { light: { misPush: mp } }); assert.equal(posts(r, "misPush").length, 0, "같은 전송에는 한 번만 알림");
});

test("읽기가 잇달아 실패해 쉬는 중이어도 발주 대기 탭은 켜 두게 함 · [막힘]이면 시키지 않음", () => {
  const cfg = { reads: "live", orders: "live" }, t = at("2026-11-30", "10:00"), armed = { misAgent: { at: t, grid: true, ver: "5" } };
  const st = { day: "2026-11-30", fails: 3, stops: 1, stop: { at: t, until: t + 60 * MIN, kind: "read", why: "잇달아 3번 실패" } };
  let r = D.decide({ now: t + MIN, cfg, st, light: { misAgent: { at: t + MIN, grid: true, ver: "5" } } }); assert.equal(r.instr.code, "STOP", "대기 탭이 살아 있으면 그냥 쉼");
  r = D.decide({ now: t + 10 * MIN, cfg, st, light: armed }); assert.equal(r.instr.code, "ARM", "대기 탭이 죽으면 쉬는 중에도 다시 켜게 함"); assert.equal(r.instr.job, "order");
  const k = D.stuck({ day: "2026-11-30" }, t, "GW 가 안 열림 (인터넷·VPN)", cfg);
  r = D.decide({ now: t + 10 * MIN, cfg, st: k.st, light: armed }); assert.equal(r.instr.code, "STOP", "GW 자체가 안 되면 발주 대기도 시키지 않음");
});

test("실제(live): 당일 되풀이(12·16·20시)는 label-list 의 판단 그대로", { skip: !LL }, () => {
  const plan = JSON.parse(fs.readFileSync(path.join(LL, "gw-plan.json"), "utf8")), day = "2026-11-30";
  const go = runner({ reads: "live" });
  let r = go(at(day, "11:59"), { plan, fullAt: at(day, "11:59") }); assert.equal(posts(r, "salesPush").length, 0);
  r = go(at(day, "12:00") + 5e3, { plan, fullAt: at(day, "12:00") });
  const req = posts(r, "salesPush")[0].value;
  assert.equal(req.kind, "now"); assert.equal(req.src, "aside-hour"); assert.ok(req.also.sets && req.also.menu); assert.equal(r.instr.code, "READ");
  // 발주 시간대에는 내지 않음
  const go2 = runner({ reads: "live" });
  r = go2(at(day, "13:00"), { plan, fullAt: at(day, "13:00") }); assert.equal(posts(r, "salesPush").length, 0);
});

test("시작 코드 한 줄과 순서 글", () => {
  const s = D.snippet("https://mfgkorea.github.io/order.html/aside", "shadow", "read");
  assert.match(s, /aside\/starter\.js\?mode=shadow&t=/); assert.doesNotMatch(s, /job=order/);
  assert.match(D.snippet("https://x/aside/", "live", "order"), /mode=live&job=order/);
  assert.equal(D.steps({ code: "READ" }).length, 3); assert.equal(D.steps({ code: "IDLE" })[0], "할 일 없음");
});
