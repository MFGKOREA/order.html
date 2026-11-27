// 검증 도구 (순수 함수): 어사이드가 읽은 값과 시트에 있는 값(GW Agent 가 넣은 값)을 맞춰 봄
//  화면·저장소·네트워크를 건드리지 않음 → 매장 PC 화면(starter.js · desk.html · inbox.html)과 시험(node)이 같은 코드를 씀
//  원칙: 결과는 "같음/다름 몇 건"과 키 이름만. 매출·수량 같은 값은 요약에 담지 않음(허브가 공개 저장소라서)
(function (G) {
  const DAY = 86400e3;
  const isObj = (v) => v && typeof v === "object" && !Array.isArray(v);

  // 키 순서를 정해 글로 (같은 내용이면 같은 글)
  function stable(v) {
    if (Array.isArray(v)) return "[" + v.map(stable).join(",") + "]";
    if (isObj(v)) return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + stable(v[k])).join(",") + "}";
    return JSON.stringify(v === undefined ? null : v);
  }
  // 짧은 지문(53비트). 값 대신 이것만 남겨도 같은지 알 수 있음
  function digest(v) {
    const s = typeof v === "string" ? v : stable(v);
    let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
    for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); h1 = Math.imul(h1 ^ c, 2654435761); h2 = Math.imul(h2 ^ c, 1597334677); }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16).padStart(14, "0");
  }

  // 키 종류: data(끝난 날의 자료 → 같아야 함) · today(오늘 중간값 → 시각이 달라 값은 다를 수 있음) · meta(읽은 기록·열 이름) · request(요청 칸)
  const DATA_RE = /^(misRecv|misOrder|misXfer|menuDay|setDay|lineCheck)\.\d{4}-\d\d-\d\d$/;
  const TODAY_RE = /^(nowSales|setNow|menuNow)$/;
  const META_RE = /(Probe|Scan|Diag)$|^(gwScout|hourProbe)$/;
  const REQ_RE = /^(salesPush|misPush|asidePush|misAgent)$/;
  function classify(key) {
    key = String(key || "");
    if (REQ_RE.test(key)) return "request";
    if (DATA_RE.test(key) || key === "forecast" || key === "hourShare") return "data";
    if (TODAY_RE.test(key)) return "today";
    if (META_RE.test(key)) return "meta";
    return "other";
  }

  // 견줄 때 빼는 칸: 쓴 시각(at)·쓴 쪽(by)처럼 읽을 때마다 달라지는 것
  const VOLATILE = { at: 1, by: 1, nowAt: 1 };
  function norm(v) {
    if (Array.isArray(v)) return v.map(norm);
    if (!isObj(v)) return typeof v === "number" && !isFinite(v) ? null : v;
    const o = {};
    Object.keys(v).forEach((k) => { if (!VOLATILE[k] && v[k] !== undefined) o[k] = norm(v[k]); });
    return o;
  }
  // 줄 목록은 순서가 달라도 같은 것으로 (줄을 글로 바꿔 정렬)
  const rowBag = (rows) => (Array.isArray(rows) ? rows.map((r) => stable(norm(r))).sort() : []);
  function bagDiff(a, b) {
    const A = rowBag(a), B = rowBag(b);
    let i = 0, j = 0, onlyA = 0, onlyB = 0;
    while (i < A.length || j < B.length) {
      if (j >= B.length || (i < A.length && A[i] < B[j])) { onlyA++; i++; }
      else if (i >= A.length || B[j] < A[i]) { onlyB++; j++; }
      else { i++; j++; }
    }
    return { rowsA: A.length, rowsB: B.length, onlyA, onlyB };
  }

  // set(key, value) 로 쓰려던 값 ↔ 시트 값
  function cmpSet(mine, actual) {
    if (actual === undefined || actual === null) return { r: "miss" };
    const a = norm(mine), b = norm(actual);
    if (isObj(a) && isObj(b) && Array.isArray(a.rows) && Array.isArray(b.rows)) {
      const d = bagDiff(a.rows, b.rows);
      const restA = Object.assign({}, a), restB = Object.assign({}, b); delete restA.rows; delete restB.rows;
      const restSame = stable(restA) === stable(restB);
      if (!d.onlyA && !d.onlyB && restSame) return { r: "same" };
      return { r: "diff", d: Object.assign(d, restSame ? {} : { rest: 1 }) };
    }
    return stable(a) === stable(b) ? { r: "same" } : { r: "diff", d: {} };
  }
  // merge(key, patch) 로 바꾸려던 칸 ↔ 시트 값: 패치의 잎마다 견줌
  function cmpMerge(patch, actual) {
    let same = 0, diff = 0, miss = 0;
    const walk = (p, a) => {
      Object.keys(p || {}).forEach((k) => {
        if (VOLATILE[k]) return;
        const pv = p[k], av = a == null ? undefined : a[k];
        if (isObj(pv)) { if (av === undefined || av === null) miss++; else walk(pv, av); return; }
        if (pv === null) { if (av === undefined || av === null) same++; else diff++; return; }
        if (av === undefined || av === null) miss++;
        else if (stable(norm(pv)) === stable(norm(av)) || String(pv) === String(av)) same++;
        else diff++;
      });
    };
    walk(patch, actual);
    return { r: diff ? "diff" : miss ? "miss" : "same", d: { same, diff, miss } };
  }

  // 한 번 읽은 것(쓰려던 것 목록)을 시트와 맞춰 요약. captures = [{ action, key, value, patch }]
  //  요약에는 건수와 키 이름만 담김
  function summarize(captures, data) {
    data = data || {};
    const out = { keys: 0, same: 0, diff: [], miss: [], today: { n: 0, ok: 0, bad: [] }, meta: 0, other: 0, digest: {} };
    const byKey = new Map(); // 같은 키를 set 으로 여러 번 쓰면 마지막 것만, merge 는 모두 견줌
    (captures || []).forEach((c) => {
      if (!c || !c.key) return;
      const arr = byKey.get(c.key) || [];
      if (c.action === "merge") arr.push(c); else { for (let i = arr.length - 1; i >= 0; i--) if (arr[i].action !== "merge") arr.splice(i, 1); arr.push(c); }
      byKey.set(c.key, arr);
    });
    for (const [key, list] of byKey) {
      const cls = classify(key);
      if (cls === "request") continue;
      if (cls === "meta") { out.meta++; continue; }
      if (cls === "other") { out.other++; continue; }
      const c = list.length === 1 && list[0].action !== "merge" ? list[0] : list;
      let worst = "same", detail = null;
      list.forEach((x) => {
        const r = x.action === "merge" ? cmpMerge(x.patch, data[key]) : cmpSet(x.value, data[key]);
        if (r.r === "diff" || (r.r === "miss" && worst === "same")) { worst = r.r; detail = r.d || null; }
      });
      if (cls === "today") {
        out.today.n++;
        const mine = list[list.length - 1].value;
        const t = todayCheck(key, mine, data[key]);
        if (t.ok) out.today.ok++; else out.today.bad.push(key + ":" + t.why);
        continue;
      }
      out.keys++;
      if (!Array.isArray(c)) out.digest[key] = digest(norm(c.value));
      if (worst === "same") out.same++;
      else if (worst === "miss") out.miss.push(key);
      else out.diff.push(detail && detail.rowsA != null ? `${key} (줄 ${detail.rowsA}/${detail.rowsB} · 한쪽만 ${detail.onlyA}/${detail.onlyB})` : key);
    }
    out.diff.sort(); out.miss.sort();
    return out;
  }

  // 오늘 중간값: 값이 같을 수는 없으니 모양과 "나중에 읽은 쪽이 작지 않다"만 봄
  function todayCheck(key, mine, actual) {
    if (!isObj(mine)) return { ok: false, why: "모양" };
    if (key === "nowSales") {
      if (!(typeof mine.gross === "number" && mine.gross >= 0 && /^\d{4}-\d\d-\d\d$/.test(mine.day || ""))) return { ok: false, why: "모양" };
      if (isObj(actual) && actual.day === mine.day && typeof actual.gross === "number" && (mine.at || 0) >= (actual.at || 0) && mine.gross < actual.gross) return { ok: false, why: "나중 값이 더 작음" };
      return { ok: true };
    }
    if (!Array.isArray(mine.rows)) return { ok: false, why: "줄 없음" };
    if (isObj(actual) && Array.isArray(actual.rows) && actual.day === mine.day && (mine.at || 0) >= (actual.at || 0) && mine.rows.length < Math.floor(actual.rows.length * 0.5)) return { ok: false, why: "줄이 반 넘게 줄어듦" };
    return { ok: true };
  }

  // 모양 검사: 시트에 들어가기 전에 "이 키에 이런 값이 맞나". 틀린 이유를 글로 돌려줌(빈 배열 = 통과)
  const isDay = (s) => /^\d{4}-\d\d-\d\d$/.test(String(s || "")) && !isNaN(Date.parse(s + "T00:00:00Z"));
  const isNum = (v) => typeof v === "number" && isFinite(v);
  function shapeCheck(key, v) {
    const errs = [], bad = (m) => { if (errs.length < 5) errs.push(m); };
    const m = /^(misRecv|misOrder|misXfer|menuDay|setDay)\.(\d{4}-\d\d-\d\d)$/.exec(String(key || ""));
    if (m) {
      if (!isDay(m[2])) bad("날짜가 이상함");
      if (!isObj(v)) { bad("값이 묶음이 아님"); return errs; }
      if (!Array.isArray(v.rows)) { bad("rows 없음"); return errs; }
      const fam = m[1];
      v.rows.forEach((r, i) => {
        if (!isObj(r)) return bad(`${i + 1}번째 줄이 묶음이 아님`);
        if (fam === "misRecv" || fam === "misOrder" || fam === "misXfer") {
          if (!String(r.code || "").trim()) bad(`${i + 1}번째 줄 품목코드 없음`);
          if (!isNum(r.qty)) bad(`${i + 1}번째 줄 수량이 숫자가 아님`);
          else if (fam === "misOrder" && !(r.qty > 0)) bad(`${i + 1}번째 줄 주문 수량이 0 이하`);
          else if (r.qty === 0) bad(`${i + 1}번째 줄 수량 0`);
          else if (fam === "misRecv" && r.qty < 0 && r.ret !== 1) bad(`${i + 1}번째 줄 반품인데 표시(ret) 없음`);
          if (Math.abs(r.qty) > 1e6) bad(`${i + 1}번째 줄 수량이 너무 큼`);
        } else if (fam === "menuDay") {
          if (!String(r.m || "").trim()) bad(`${i + 1}번째 줄 메뉴 이름 없음`);
          if (!isNum(r.q)) bad(`${i + 1}번째 줄 수량이 숫자가 아님`);
        }
      });
      return errs;
    }
    if (key === "nowSales") { if (!isObj(v) || !isNum(v.gross) || v.gross < 0 || !isDay(v.day)) bad("nowSales 모양"); return errs; }
    if (key === "forecast") {
      if (!isObj(v)) { bad("forecast 가 묶음이 아님"); return errs; }
      Object.keys(v).forEach((d) => { if (!isDay(d)) bad(`날짜 아님: ${String(d).slice(0, 12)}`); else if (isObj(v[d]) && v[d].act != null && String(v[d].act).trim() !== "" && !isFinite(parseFloat(v[d].act))) bad(`${d} act 가 숫자 아님`); });
      return errs;
    }
    return errs;
  }

  // 시트 사본 두 개(또는 시점 두 개)를 키 묶음별로 견줌 → { 묶음: { same, diff, onlyA, onlyB } }
  function compareSnap(a, b, o) {
    o = o || {}; a = a || {}; b = b || {};
    const fam = (k) => (DATA_RE.test(k) ? k.split(".")[0] : k);
    const out = {}, keys = new Set(Object.keys(a).concat(Object.keys(b)));
    const want = (k) => classify(k) === "data" && (!o.from || !DATA_RE.test(k) || k.slice(-10) >= o.from) && (!o.to || !DATA_RE.test(k) || k.slice(-10) <= o.to);
    keys.forEach((k) => {
      if (!want(k)) return;
      const f = fam(k), t = out[f] || (out[f] = { same: 0, diff: 0, onlyA: 0, onlyB: 0, diffKeys: [] });
      if (!(k in a)) t.onlyB++; else if (!(k in b)) t.onlyA++;
      else if (cmpSet(a[k], b[k]).r === "same") t.same++;
      else { t.diff++; if (t.diffKeys.length < 20) t.diffKeys.push(k); }
    });
    return out;
  }

  // 도착 지연 기준선: "어제 자료가 다음 날 몇 시에 들어왔나". menuDay·setDay 는 처음 받을 때만 쓰므로 at = 처음 받은 시각
  //  결과: { n, missing(빈 날), medianH, p90H, maxH, late(다음 날 정오 넘김), days: [{ d, h }] } — 시각만, 값 없음
  function lagReport(data, o) {
    o = o || {}; data = data || {};
    const fam = o.family || "menuDay", now = o.now || Date.now();
    const to = o.to || new Date(now + 9 * 3600e3 - DAY).toISOString().slice(0, 10), span = o.days || 21;
    const days = []; let missing = 0;
    for (let i = span - 1; i >= 0; i--) {
      const d = new Date(Date.parse(to + "T00:00:00Z") - i * DAY).toISOString().slice(0, 10), v = data[fam + "." + d];
      if (!isObj(v) || !v.at || v.at < 1e12) { missing++; continue; }
      const end = Date.parse(d + "T00:00:00+09:00") + DAY; // 그날이 끝난 때(한국 자정)
      days.push({ d, h: Math.round(((v.at - end) / 3600e3) * 10) / 10 });
    }
    const hs = days.map((x) => x.h).sort((x, y) => x - y), q = (p) => (hs.length ? hs[Math.min(hs.length - 1, Math.floor(p * hs.length))] : null);
    return { family: fam, span, n: days.length, missing, medianH: q(0.5), p90H: q(0.9), maxH: hs.length ? hs[hs.length - 1] : null, late: days.filter((x) => x.h > 12).length, days };
  }

  G.AsideVerify = { stable, digest, classify, norm, bagDiff, cmpSet, cmpMerge, summarize, todayCheck, shapeCheck, compareSnap, lagReport };
})(typeof self !== "undefined" ? self : globalThis);
