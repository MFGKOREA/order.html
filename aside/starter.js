// 어사이드 시작 코드: MIS 첫 화면(로그인된 탭)에서 어사이드가 한 번 실행함
//  GW Agent(크롬 확장)의 start.js + "읽기 스크립트 넣기" 자리를 대신함. 화면을 읽는 일은 지금 쓰는 코드 그대로:
//    읽기 = label-list 의 mis-sales.js (요청 칸을 보고 메뉴 이동·조회·읽기·시트 쓰기까지 스스로 함)
//    발주 = label-list 의 mis-agent.js → mis.js (주문등록 화면에서 폰 [GW 전송]을 기다렸다가 입력·저장)
//  어사이드(AI)는 숫자를 읽거나 옮겨 적지 않음 → 옮겨 적다 틀릴 일이 없음. AI는 창을 열고 이 코드를 실행하고 닫기만 함
//
//  방식(mode)
//    shadow(기본): GW Agent 와 같이 돌려 보는 시험. 요청은 asidePush 칸으로 따로 받고, 읽은 결과는 시트에 쓰지 않고
//                  시트에 이미 있는 값(GW Agent 가 넣은 값)과 맞춰 본 뒤 "같음/다름 몇 건"만 asideShadow 에 남김.
//                  알림 보내기 같은 바깥 요청도 보내지 않음(직원 폰에 알림이 두 번 가지 않게)
//    live: 진짜로 맡음. 아무것도 가로채지 않고 mis-sales.js 를 그대로 돌림(salesPush 칸)
//  일(job): read(기본) · order(live 에서만. 주문등록 화면을 열고 자동 대기를 켬)
//  쓰는 법: <script src=".../aside/starter.js?mode=shadow"> 를 MIS 첫 화면에 넣음 (desk.html 이 그 한 줄을 만들어 줌)
(() => {
  const W = window, VER = "aside-starter 1";
  const SRC = (document.currentScript && document.currentScript.src) || "";
  let Q; try { Q = new URL(SRC).searchParams; } catch (e) { Q = new URLSearchParams(""); }
  const O = Object.assign({}, W.__asideOpt || {}); // 시험·REPL 에서 미리 넣어 둘 수 있음
  const MODE = (O.mode || Q.get("mode") || "shadow") === "live" ? "live" : "shadow";
  const JOB = (O.job || Q.get("job") || "read") === "order" ? "order" : "read";
  const REQ = MODE === "live" ? "salesPush" : "asidePush";
  // 읽기 코드가 있는 곳. 주소로는 못 바꿈(아무 데서나 코드를 불러오지 않게) — 시험에서만 __asideOpt.base 로 바꿈
  const BASE = String(O.base || "https://mfgkorea.github.io/label-list/").replace(/\/?$/, "/");
  const HERE = SRC ? SRC.replace(/[^/]*(\?.*)?$/, "") : "https://mfgkorea.github.io/order.html/aside/";
  const T = Object.assign({ total: 13 * 60e3, claim: 25e3, settle: 600 }, O.t || {});
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  if (W.__asideStarter && !W.__asideStarter.done) { try { W.__asideStarter.say("이미 도는 중 (이 탭을 닫지 마세요)"); } catch (e) {} return; }
  const S = (W.__asideStarter = { ver: VER, mode: MODE, job: JOB, at: Date.now(), phase: "시작", text: "", done: false, ok: null, api: null, req: null, captures: [], suppressed: 0, summary: null });

  // 화면 표시: 왼쪽 아래 배지 + 탭 제목. 어사이드는 이 글만 보고 끝났는지 앎
  const baseTitle = document.title.replace(/^\[[^\]]*\]\s*/, "");
  const say = (S.say = (text, phase) => {
    if (phase) S.phase = phase; S.text = text;
    try {
      document.title = `[어사이드 ${S.phase}] ${baseTitle}`;
      let el = document.getElementById("asideBadge");
      if (!el && document.body) {
        el = document.createElement("div"); el.id = "asideBadge";
        el.style.cssText = "position:fixed;left:12px;bottom:12px;z-index:99999;max-width:60vw;background:#123;color:#fff;font:700 13px/1.5 sans-serif;padding:8px 12px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,.3);pointer-events:none";
        document.body.appendChild(el);
      }
      if (el) el.textContent = `어사이드 시작 코드 · ${MODE === "live" ? "실제" : "섀도"} · ${text}`;
    } catch (e) {}
  });
  const end = (ok, text) => { S.done = true; S.ok = !!ok; say(text, ok ? "끝" : "멈춤"); };

  const load = (url) => new Promise((ok, no) => {
    const s = document.createElement("script"); s.charset = "utf-8"; s.src = url;
    s.onload = () => { s.remove(); ok(); }; s.onerror = () => { s.remove(); no(new Error("load " + url.split("?")[0].split("/").pop())); };
    (document.body || document.documentElement).appendChild(s);
  });

  // ---------- 시트로 가는 요청 살피기 ----------
  const realFetch = W.fetch.bind(W);
  const isGas = (u) => /^https:\/\/script\.google\.com\/macros\//.test(u);
  const baseOf = (u) => String(u).split("?")[0];
  const fake = (obj) => new Response(JSON.stringify(obj), { status: 200, headers: { "Content-Type": "application/json" } });
  let KEY = ""; // 가게 키(시트가 잠겨 있을 때): 읽기 코드가 보내는 것을 그대로 따라 씀
  // 섀도: 읽기 코드에는 asidePush 를 salesPush 인 것처럼 보여 줌
  const view = (data) => { const d = Object.assign({}, data); if (d[REQ]) d.salesPush = d[REQ]; else delete d.salesPush; delete d[REQ]; return d; };
  let finalSeen = null; // 읽기 코드가 마지막에 적은 상태(done | error)
  const observe = (body) => {
    if (!body || body.key !== "salesPush") return;
    const p = body.action === "merge" ? body.patch : body.value;
    if (!p) return;
    if (p.status === "running") { S.claimed = true; say(`읽는 중${S.req && S.req.kind ? " (" + S.req.kind + ")" : ""}`, "읽는 중"); }
    if (p.cur) say(`읽는 중 (${p.cur})`, "읽는 중");
    if (/^(done|error)$/.test(p.status || "")) finalSeen = { status: p.status, text: String(p.text || "").slice(0, 300) };
  };
  W.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : (input && (input.url || input.href)) || "";
    if (!isGas(url)) return realFetch(input, init);
    const method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
    if (method === "GET") {
      let u = null; try { u = new URL(url); } catch (e) {}
      if (u && u.searchParams.get("api") && !S.api) { S.api = baseOf(url); KEY = u.searchParams.get("k") || KEY; }
      const res = await realFetch(input, init);
      if (!u || baseOf(url) !== S.api || u.searchParams.get("status")) return res;
      let j; try { j = await res.clone().json(); } catch (e) { return res; }
      if (!j || !j.data || typeof j.data !== "object") return res;
      if (MODE === "shadow") j = Object.assign({}, j, { data: view(j.data) });
      if (!S.req) { // 첫 읽기: 맡을 요청이 있는지
        const r = j.data.salesPush;
        S.req = r ? { id: r.id, kind: r.kind || "gross", status: r.status, also: Object.keys(r.also || {}) } : { status: "none" };
      }
      return MODE === "shadow" ? fake(j) : res;
    }
    let body = null; try { body = JSON.parse(init && init.body); } catch (e) {}
    if (body && body.k) KEY = body.k;
    if (!S.api || baseOf(url) !== S.api) {
      // 발주 시트가 아닌 다른 Apps Script (알림 보내기 등): 섀도에서는 보내지 않음
      if (MODE === "shadow") { S.suppressed++; return fake({ ok: true, shadow: 1, sent: 0 }); }
      return realFetch(input, init);
    }
    if (!body || !body.key) return realFetch(input, init);
    observe(body);
    if (MODE === "live") return realFetch(input, init);
    if (body.key === "salesPush") { // 요청 칸은 asidePush 로 바꿔 진짜로 씀 (책상 화면이 진행을 봄)
      const res = await realFetch(url, Object.assign({}, init, { body: JSON.stringify(Object.assign({}, body, { key: REQ })) }));
      let j; try { j = await res.clone().json(); } catch (e) { return res; }
      if (j && j.data && j.data[REQ] !== undefined) j = Object.assign({}, j, { data: { salesPush: j.data[REQ] } });
      return fake(j);
    }
    // 그 밖의 쓰기(읽은 결과·기록)는 시트에 쓰지 않고 모아 둠
    S.captures.push({ action: body.action, key: body.key, value: body.value, patch: body.patch, item: body.item, t: Date.now() });
    return fake({ ok: true, data: { [body.key]: body.action === "merge" ? body.patch : body.value === undefined ? null : body.value }, ver: "shadow" });
  };

  const post = (body) => realFetch(S.api, { method: "POST", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify(Object.assign({}, body, { k: KEY })) }).then((r) => r.json()).catch(() => null);
  const readAll = async () => { const j = await (await realFetch(S.api + "?api=1&t=" + Date.now() + (KEY ? "&k=" + encodeURIComponent(KEY) : ""))).json(); return (j && j.data) || {}; };

  // 섀도 마무리: 모아 둔 결과를 시트 값과 맞춰 보고 요약만 남김
  async function shadowFinish(status, why) {
    let sum = { keys: 0, same: 0, diff: [], miss: [], today: { n: 0, ok: 0, bad: [] }, meta: 0, other: 0 }, data = {};
    try { data = await readAll(); sum = W.AsideVerify.summarize(S.captures, data); } catch (e) { why = (why ? why + " · " : "") + "맞춰 보기 실패"; }
    const id = (S.req && S.req.id) || S.at;
    const one = {
      id, at: Date.now(), kind: (S.req && S.req.kind) || "", also: (S.req && S.req.also) || [], status, ok: status === "done" && !sum.diff.length && !sum.today.bad.length,
      ms: Date.now() - S.at, keys: sum.keys, same: sum.same, diff: sum.diff.slice(0, 30), miss: sum.miss.slice(0, 30), nDiff: sum.diff.length, nMiss: sum.miss.length,
      today: sum.today, meta: sum.meta, suppressed: S.suppressed, why: why || "", ver: VER, ua: (navigator.userAgent.match(/(Aside|Edg|Chrome)\/[\d.]+/g) || []).join(" ").slice(0, 60),
    };
    S.summary = Object.assign({}, one, { digest: sum.digest });
    const runs = { [id]: one }, old = Object.keys(((data.asideShadow || {}).runs) || {}).filter((k) => String(k) !== String(id)).sort((a, b) => b - a);
    old.slice(39).forEach((k) => { runs[k] = null; }); // 최근 40번만 남김
    await post({ action: "merge", key: "asideShadow", patch: { last: id, lastAt: one.at, runs } });
    return one;
  }

  // ---------- 발주 대기 켜기 (live 에서만): 주문정보관리 → 주문등록 화면 → 자동 대기(mis-agent.js) ----------
  async function armOrder() {
    const frames = () => { const out = []; const walk = (w) => { try { void w.document; out.push(w); } catch (e) { return; } for (let i = 0; i < w.frames.length; i++) walk(w.frames[i]); }; walk(W); return out; };
    const q = (sel) => { for (const w of frames()) { try { const el = w.document.querySelector(sel); if (el) return el; } catch (e) {} } return null; };
    const ready = () => !!q("#custBtn input.btn_basic");
    const clickText = (txt) => {
      for (const sel of [".tree-title", "a, span, li, div, td"]) {
        const els = [];
        for (const w of frames()) { try { els.push(...[...w.document.querySelectorAll(sel)].filter((e) => e.children.length === 0 && e.textContent.trim() === txt)); } catch (e) {} }
        if (els.length) { const el = els[els.length - 1]; el.scrollIntoView && el.scrollIntoView({ block: "center" }); el.click(); el.dispatchEvent(new MouseEvent("dblclick", { bubbles: true })); return true; }
      }
      return false;
    };
    say("주문등록 화면 여는 중", "여는 중");
    for (let t = 0; t < 60 && !q(".tree-title") && !ready(); t++) await sleep(250);
    for (let t = 0; t < 4 && !ready(); t++) {
      if (t === 0 || t === 2) clickText("주문정보관리");
      await sleep(400); clickText("주문등록");
      for (let k = 0; k < 20 && !ready(); k++) await sleep(250);
    }
    if (!ready()) return end(false, "주문등록 화면을 못 열었어요 (메뉴를 못 찾음)");
    await sleep(300);
    try { await load(BASE + "mis-agent.js?quiet=1&t=" + Date.now()); } catch (e) { return end(false, "자동 대기 코드를 못 불러옴 (인터넷 확인)"); }
    S.armed = true; S.done = true; S.ok = true; say("발주 대기 켜짐 (이 탭을 닫지 마세요)", "대기");
  }

  // ---------- 읽기 ----------
  async function runRead() {
    if ([...document.querySelectorAll('input[type="password"]')].some((el) => el.offsetParent !== null && !el.disabled)) return end(false, "로그인 화면이에요 (KM 확인)");
    if (MODE === "shadow") { try { await load(HERE + "verify-core.js?t=" + Date.now()); } catch (e) { return end(false, "검증 코드를 못 불러옴 (인터넷 확인)"); } }
    say("요청 확인 중", "확인 중");
    try { await load(BASE + "mis-sales.js?quiet=1&t=" + Date.now()); } catch (e) { return end(false, "읽기 코드를 못 불러옴 (인터넷 확인)"); }
    const t0 = Date.now();
    while (!S.req && Date.now() - t0 < T.claim) await sleep(200);
    if (!S.req) return end(false, "시트에 못 닿음 (인터넷·가게 키 확인)");
    if (S.req.status !== "pending") return end(true, "할 일 없음 (대기 요청 없음)");
    while (!finalSeen && Date.now() - S.at < T.total) {
      if (!S.claimed && Date.now() - t0 > T.claim) break; // 다른 탭이 먼저 맡았거나 못 맡음
      await sleep(250);
    }
    await sleep(T.settle);
    if (!finalSeen && !S.claimed) return end(true, "다른 쪽이 먼저 맡음 (이 탭은 안 함)");
    const status = finalSeen ? finalSeen.status : "timeout";
    if (MODE === "live") return end(status === "done", status === "done" ? "성공" : status === "error" ? `실패 — ${finalSeen.text}` : "시간 초과");
    if (!finalSeen) await post({ action: "merge", key: REQ, patch: { status: "error", doneAt: Date.now(), text: "어사이드 시작 코드: 시간 안에 못 끝냄", cur: null, prog: null } });
    const one = await shadowFinish(status, finalSeen ? "" : "시간 초과");
    end(one.ok, `${status === "done" ? "" : "읽기 " + (status === "error" ? "실패" : "시간 초과") + " · "}같음 ${one.same} · 다름 ${one.nDiff} · 없음 ${one.nMiss}${one.today.n ? ` · 오늘 값 ${one.today.ok}/${one.today.n}` : ""}`);
  }

  (JOB === "order" ? (MODE === "live" ? armOrder() : Promise.resolve(end(false, "발주는 섀도로 하지 않아요"))) : runRead()).catch((e) => end(false, "멈춤: " + ((e && e.message) || e)));
})();
