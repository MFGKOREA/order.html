// 검증 도구(verify-core.js) 시험 — node --test aside/test/
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "module";
createRequire(import.meta.url)("../verify-core.js");
const V = globalThis.AsideVerify;
const recv = (rows, at = 1) => ({ at, rows });
const R = [{ code: "900001", name: "시험양파", qty: 3, unit: "KG" }, { code: "900002", name: "시험마늘", qty: -2, unit: "EA", ret: 1 }];

test("같은 내용은 키 순서·쓴 시각·줄 순서가 달라도 같음", () => {
  assert.equal(V.stable({ b: 1, a: [2, { d: 1, c: 2 }] }), V.stable({ a: [2, { c: 2, d: 1 }], b: 1 }));
  assert.equal(V.cmpSet(recv(R, 1), recv([R[1], R[0]], 999)).r, "same");
  assert.equal(V.digest(V.norm(recv(R, 1))), V.digest(V.norm(recv(R, 2))));
  assert.notEqual(V.digest({ a: 1 }), V.digest({ a: 2 }));
});

test("수량 하나·줄 하나만 달라도 다름으로 잡고, 몇 줄이 다른지 알려 줌", () => {
  const b = [{ ...R[0], qty: 4 }, R[1]];
  const d = V.cmpSet(recv(R), recv(b));
  assert.equal(d.r, "diff"); assert.deepEqual([d.d.rowsA, d.d.rowsB, d.d.onlyA, d.d.onlyB], [2, 2, 1, 1]);
  assert.equal(V.cmpSet(recv(R), recv([R[0]])).d.onlyA, 1);
  assert.equal(V.cmpSet(recv(R), undefined).r, "miss");
  assert.equal(V.cmpSet(recv([]), recv([])).r, "same");
});

test("merge 로 바꾸려던 칸은 잎마다 견줌 (글자·숫자 차이는 같은 것으로)", () => {
  const actual = { "2026-11-20": { fc: "100", act: "5000000", total: 5200000 }, "2026-11-21": { act: "4000000" } };
  assert.equal(V.cmpMerge({ "2026-11-20": { act: 5000000 } }, actual).r, "same");
  assert.equal(V.cmpMerge({ "2026-11-20": { act: 5000001 } }, actual).r, "diff");
  assert.equal(V.cmpMerge({ "2026-11-22": { act: 1 } }, actual).r, "miss");
  assert.deepEqual(V.cmpMerge({ "2026-11-20": { act: 5000000, total: 1 }, "2026-11-21": { act: 4000000 } }, actual).d, { same: 2, diff: 1, miss: 0 });
});

test("요약에는 건수와 키 이름만 — 값이 새지 않음", () => {
  const data = { "misRecv.2026-11-20": recv(R), "misRecv.2026-11-21": recv([{ ...R[0], qty: 9 }]), forecast: { "2026-11-20": { act: "100" } }, nowSales: { at: 5, day: "2026-11-22", gross: 1000 } };
  const cap = [
    { action: "set", key: "misRecv.2026-11-20", value: recv(R, 7) },
    { action: "set", key: "misRecv.2026-11-21", value: recv([{ ...R[0], qty: 8 }], 7) },
    { action: "set", key: "misRecv.2026-11-22", value: recv([], 7) },
    { action: "merge", key: "forecast", patch: { "2026-11-20": { act: 100 } } },
    { action: "set", key: "recvProbe", value: { at: 7, grids: [] } }, { action: "set", key: "misRecvScan", value: { at: 7 } },
    { action: "set", key: "nowSales", value: { at: 9, day: "2026-11-22", gross: 1500 } },
    { action: "merge", key: "salesPush", patch: { status: "done" } },
  ];
  const s = V.summarize(cap, data);
  assert.deepEqual([s.keys, s.same, s.diff.length, s.miss.length, s.meta, s.today.n, s.today.ok], [4, 2, 1, 1, 2, 1, 1]);
  assert.match(s.diff[0], /^misRecv\.2026-11-21 \(줄 1\/1 · 한쪽만 1\/1\)$/); assert.equal(s.miss[0], "misRecv.2026-11-22");
  const text = JSON.stringify({ ...s, digest: undefined });
  assert.doesNotMatch(text, /시험양파|"qty"|1500|900001/);
});

test("오늘 중간값: 나중에 읽은 Gross 가 더 작으면 이상함", () => {
  assert.equal(V.todayCheck("nowSales", { at: 9, day: "2026-11-22", gross: 900 }, { at: 5, day: "2026-11-22", gross: 1000 }).ok, false);
  assert.equal(V.todayCheck("nowSales", { at: 9, day: "2026-11-23", gross: 10 }, { at: 5, day: "2026-11-22", gross: 1000 }).ok, true, "날이 다르면 견주지 않음");
  assert.equal(V.todayCheck("setNow", { at: 9, day: "d", rows: [] }, { at: 5, day: "d", rows: [1, 2, 3, 4] }).ok, false);
});

test("모양 검사: 틀린 값은 까닭과 함께 걸러 냄", () => {
  assert.deepEqual(V.shapeCheck("misRecv.2026-11-20", recv(R)), []);
  assert.match(V.shapeCheck("misRecv.2026-11-20", recv([{ code: "", qty: 1 }]))[0], /품목코드 없음/);
  assert.match(V.shapeCheck("misRecv.2026-11-20", recv([{ code: "1", qty: "3" }]))[0], /숫자가 아님/);
  assert.match(V.shapeCheck("misRecv.2026-11-20", recv([{ code: "1", qty: -3 }]))[0], /반품인데 표시/);
  assert.match(V.shapeCheck("misOrder.2026-11-20", recv([{ code: "1", qty: -3 }]))[0], /0 이하/);
  assert.match(V.shapeCheck("misRecv.2026-13-45", recv([]))[0], /날짜가 이상함/);
  assert.match(V.shapeCheck("menuDay.2026-11-20", recv([{ c: "x", m: "", q: 1 }]))[0], /메뉴 이름 없음/);
  assert.match(V.shapeCheck("nowSales", { day: "2026-11-20", gross: -1 })[0], /nowSales/);
  assert.match(V.shapeCheck("forecast", { "2026-11-20": { act: "abc" } })[0], /act 가 숫자 아님/);
  assert.deepEqual(V.shapeCheck("somethingElse", 123), []);
});

test("사본 비교: 묶음별 같음/다름/한쪽에만", () => {
  const a = { "misRecv.2026-11-20": recv(R, 1), "misRecv.2026-11-21": recv([], 1), "menuDay.2026-11-20": recv([{ c: "x", m: "a", q: 1 }]), forecast: { x: 1 }, salesPush: { id: 1 } };
  const b = { "misRecv.2026-11-20": recv(R, 2), "misRecv.2026-11-21": recv([R[0]], 2), "menuDay.2026-11-21": recv([]), forecast: { x: 1 }, salesPush: { id: 2 } };
  const r = V.compareSnap(a, b);
  assert.deepEqual([r.misRecv.same, r.misRecv.diff], [1, 1]); assert.deepEqual(r.misRecv.diffKeys, ["misRecv.2026-11-21"]);
  assert.deepEqual([r.menuDay.onlyA, r.menuDay.onlyB], [1, 1]); assert.equal(r.forecast.same, 1); assert.equal(r.salesPush, undefined);
  assert.equal(V.compareSnap(a, b, { from: "2026-11-21" }).misRecv.same, 0);
});

test("도착 지연: 그날 자정부터 처음 들어온 때까지", () => {
  const at = (d, h) => Date.parse(d + "T00:00:00+09:00") + 86400e3 + h * 3600e3;
  const data = { "menuDay.2026-11-20": { at: at("2026-11-20", 9), rows: [] }, "menuDay.2026-11-21": { at: at("2026-11-21", 30), rows: [] }, "menuDay.2026-11-22": { at: 1, rows: [] } };
  const r = V.lagReport(data, { family: "menuDay", to: "2026-11-23", days: 4 });
  assert.deepEqual([r.n, r.missing, r.late, r.maxH], [2, 2, 1, 30]); assert.deepEqual(r.days.map((x) => x.h), [9, 30]);
});
