// 책상(감독) 판단: "지금 어사이드가 무엇을 해야 하나"를 정함 — GW Agent(크롬 확장) bg.js 의 일정·감시 자리를 대신함
//  화면·저장소·네트워크를 건드리지 않는 순수 함수 → 책상 화면(desk.html)과 시험·되돌려 보기(node)가 같은 코드를 씀
//  언제 무엇을 받을지는 새로 만들지 않고 label-list 의 판단을 그대로 부름: autoPlan(gw-agent/auto.js) · periodDue 등(gw-agent/periodic.js)
//
//  decide({ now, cfg, light, full, fullAt, plan, st }, lib) → { st, acts, instr, wantFull, nextAt }
//    cfg   시트 asideCfg (없으면 모두 꺼짐): { reads: "off" | "shadow" | "live", orders: "off" | "live", shadow: { kinds, times } }
//    light 시트 상태만(?api=1&status=1): misPush · salesPush · misAgent · gwDiag
//    full  시트 전체(가끔만 읽음) · fullAt 읽은 시각 · plan gw-plan.json
//    st    책상이 기억하는 것(브라우저에 저장). 처음엔 {}
//    acts  화면이 해 줄 일: { type: "post", body } (시트에 쓰기) · { type: "log", msg }
//    instr 어사이드에게 보여 줄 한 가지: { code, title, why, mode, job }
//          code = IDLE(쉼) · READ(읽기 시작) · ARM(발주 대기 켜기) · WAIT(기다림) · CLOSE(탭 닫기) · STOP(멈춤, KM 에게)
(function (G) {
  const MIN = 60e3, HOUR = 3600e3, DAY = 86400e3, VER = "aside-desk 1";
  const kst = (ms) => new Date(ms + 9 * HOUR);
  const ymd = (ms) => kst(ms).toISOString().slice(0, 10);
  const hmOf = (ms) => { const t = kst(ms); return t.getUTCHours() * 60 + t.getUTCMinutes(); };
  const addDay = (d, n) => new Date(Date.parse(d + "T00:00:00Z") + n * DAY).toISOString().slice(0, 10);
  const HHMM = (s) => { const m = /^(\d{1,2}):(\d{2})$/.exec(String(s == null ? "" : s).trim()); return m ? +m[1] * 60 + +m[2] : null; };
  const atKst = (day, hm) => Date.parse(day + "T00:00:00+09:00") + hm * MIN;
  const clone = (o) => JSON.parse(JSON.stringify(o == null ? {} : o));
  const isObj = (v) => v && typeof v === "object" && !Array.isArray(v);

  const DEF = {
    reads: "off", orders: "off",
    shadow: { kinds: ["recv"], times: ["10:40"], slotMin: 180 },
    lim: {
      pickup: 10 * MIN,      // 읽기 시작을 띄운 뒤 어사이드가 시작 코드를 실행할 때까지
      run: 14 * MIN,         // 읽기 시작 뒤 끝날 때까지 (확장의 12분 + 여유)
      closeShow: 2 * MIN,    // "탭 닫기"를 보여 주는 시간
      closeMin: 20e3,        // 기다리는 요청이 있으면 "탭 닫기"는 이만큼만 보여 주고 바로 다음 읽기로
      cfgEvery: 30 * MIN,    // 설정(asideCfg)을 다시 읽는 간격 = 시트 전체 읽기 (시트가 1MB 를 넘어 자주 읽지 않음. 확장의 상시 수집과 같은 30분)
      fullRun: 30e3,         // 섀도가 도는 동안 진행을 보는 간격 (화면은 먼저 시트 판 번호만 보고, 바뀌었을 때만 전체를 읽음)
      beat: 10 * MIN, deskBeat: 60 * MIN, // 책상 소식(asideDesk)은 1시간에 한 번 + 상태가 바뀔 때 (쓸 때마다 폰 앱이 시트를 다시 읽으므로 아낌)
      armStale: 4 * MIN,     // 발주 대기 탭이 이만큼 소식이 없으면 꺼진 것으로 봄 (대기 탭은 110초마다 적음)
      orderStuck: 6 * MIN,   // 폰 전송이 이만큼 안 풀리면 폰에 알림 (확장과 같음)
      orderAge: 30 * MIN, salesAge: 6 * HOUR,
      maxFail: 3,            // 잇달아 이만큼 실패하면 멈추고 KM 에게 (3회 멈춤 규칙)
      coolOff: 60 * MIN,     // 멈춘 뒤 이만큼 쉬고 한 번 다시 해 봄. 또 실패하면 2배씩(최대 4시간) — 인터넷·VPN 이 돌아오면 스스로 풀리게
      coolMax: 4 * HOUR,
      autoEvery: 30 * MIN, autoIdle: 3 * HOUR, autoRetry: 5 * MIN, autoMax: 4,
      perMax: 20, perWait: 3 * MIN, shadowWait: 3 * MIN,
    },
    orderSkip: [12 * 60 + 30, 14 * 60 + 45],
  };
  function mergeCfg(c) {
    c = isObj(c) ? c : {};
    const out = clone(DEF);
    if (/^(off|shadow|live)$/.test(c.reads || "")) out.reads = c.reads;
    if (/^(off|live)$/.test(c.orders || "")) out.orders = c.orders;
    if (isObj(c.shadow)) {
      if (Array.isArray(c.shadow.kinds)) out.shadow.kinds = c.shadow.kinds.filter((k) => SHADOW_ARGS[k]).slice(0, 12);
      if (Array.isArray(c.shadow.times)) out.shadow.times = c.shadow.times.filter((t) => HHMM(t) != null).slice(0, 6);
      if (+c.shadow.slotMin >= 10) out.shadow.slotMin = Math.min(600, Math.floor(+c.shadow.slotMin));
    }
    if (isObj(c.lim)) Object.keys(out.lim).forEach((k) => { if (+c.lim[k] > 0) out.lim[k] = +c.lim[k]; });
    return out;
  }

  // 섀도로 읽어 볼 종류와 요청 모양 (읽기 코드 mis-sales.js 의 종류 이름으로). Y = 어제, T = 오늘
  const SHADOW_ARGS = {
    recv: () => ["recv", {}], orders: () => ["orders", {}], xfer: () => ["xfer", {}], hour: () => ["hour", {}], scout: () => ["scout", {}],
    sets: (T, Y) => ["sets", { from: Y, to: Y, force: 1 }],
    menu: (T, Y) => ["menu", { from: Y, to: Y, force: 1 }],
    gross: (T, Y) => ["gross", { from: addDay(Y, -((new Date(Y + "T00:00:00Z").getUTCDay() + 6) % 7)), to: Y }],
    now: (T) => ["now", { from: T, to: T, today: 1 }],
    setsToday: (T) => ["sets", { from: T, to: T, force: 1, today: 1 }],
    menuToday: (T) => ["menu", { from: T, to: T, force: 1, today: 1 }],
    linecheck: (T) => ["linecheck", { to: T }],
  };
  // 섀도 요청 한 덩어리: 첫 종류가 본체, 나머지는 덧붙임(also) → 창 하나로 다 읽음. "지금 Gross(now)"는 본체로만 됨
  function shadowBundle(now, kinds) {
    const T = ymd(now), Y = addDay(T, -1), t = Math.floor(now);
    const list = (Array.isArray(kinds) ? kinds : []).filter((k, i, a) => SHADOW_ARGS[k] && a.indexOf(k) === i).map((k) => SHADOW_ARGS[k](T, Y));
    if (!list.length) return null;
    list.sort((a, b) => (b[0] === "now") - (a[0] === "now"));
    const seen = {}, uniq = list.filter(([k]) => (seen[k] ? false : (seen[k] = 1)));
    const [k0, a0] = uniq[0], r = Object.assign({ id: t, at: t, status: "pending", src: "aside-shadow" }, a0), also = {};
    if (k0 !== "gross") r.kind = k0;
    uniq.slice(1).forEach(([k, a]) => { also[k] = Object.assign({}, a, { at: t }); });
    if (Object.keys(also).length) r.also = also;
    return r;
  }

  const TEXT = {
    IDLE: "할 일 없음", READ: "읽기 시작", ARM: "발주 대기 켜기", WAIT: "기다리기", CLOSE: "탭 닫기", STOP: "멈춤 — KM 에게 알리기",
  };

  function decide(input, lib) {
    lib = lib || G;
    const now = input.now, cfg = mergeCfg(input.cfg), L = cfg.lim, light = input.light || {}, full = input.full || null, fullAt = input.fullAt || 0, plan = Array.isArray(input.plan) ? input.plan : undefined;
    const st = clone(input.st), acts = [];
    const post = (body) => acts.push({ type: "post", body }), log = (msg) => acts.push({ type: "log", msg });
    const T = ymd(now), hm = hmOf(now);
    let wantFull = false;
    const out = (code, why, more) => {
      const instr = Object.assign({ code, title: TEXT[code], why: why || "" }, more || {});
      if (st.instr !== code + "|" + (instr.mode || "") + "|" + (instr.job || "")) { st.instr = code + "|" + (instr.mode || "") + "|" + (instr.job || ""); st.instrAt = now; }
      instr.since = st.instrAt;
      return { st, acts, instr, wantFull, cfg };
    };

    // 날이 바뀌면 하루 횟수만 0으로
    if (st.day !== T) { st.day = T; st.sh = { done: {} }; st.tried = {}; st.rel = {}; st.stops = 0; }
    // 멈춤은 쉬는 시간이 지나면 풀고 한 번 다시 해 봄 (그때 또 실패하면 바로 다시 멈춤 — 실패 횟수는 성공해야 0이 됨)
    if (st.stop && st.stop.until && now >= st.stop.until) { acts.push({ type: "log", msg: "쉬는 시간이 지나 다시 해 봄" }); st.stop = null; st.fails = Math.max(0, (st.fails || 0) - 1); }
    st.sh = st.sh || { done: {} }; st.tried = st.tried || {}; st.rel = st.rel || {}; st.fails = st.fails || 0;
    st.auto = st.auto || {}; st.per = st.per || {};

    // 설정을 가끔 다시 읽음 (시트 전체 읽기)
    if (now - fullAt >= (cfg.reads === "off" && cfg.orders === "off" ? 2 : 1) * L.cfgEvery && now - (input.fullFailAt || 0) > MIN) wantFull = true;

    const sp = light.salesPush || {}, mp = light.misPush || {}, ag = light.misAgent || {};
    const orderPending = mp.date === T && mp.status === "pending" && now - (mp.at || 0) < L.orderAge;
    const orderBusy = /^(pending|running)$/.test(String(mp.status || "")) && now - (mp.at || 0) < 20 * MIN;
    const inSkip = hm >= cfg.orderSkip[0] && hm <= cfg.orderSkip[1];
    // 치우기(실제 방식): 아무도 안 맡는 요청이 남아 폰이 '받는 중'에 갇히지 않게 오류를 적어 풀어 줌 (요청마다 한 번).
    //  오류 쓰기가 인터넷 끊김으로 사라졌거나, 책상이 쉬는 동안 들어왔거나, 읽던 탭이 죽은 경우를 여기서 거둠
    const janitor = (stopped) => {
      if (cfg.reads !== "live" || !sp.id || st.rel[sp.id] || (st.run && String(st.run.id) === String(sp.id))) return;
      const age = now - (sp.at || 0);
      if (age > L.salesAge) return;
      const lost = sp.status === "pending" && (stopped ? age > 3 * MIN : !!st.tried[sp.id] && age > L.pickup + 5 * MIN);
      const dead = sp.status === "running" && now - (sp.startAt || sp.at || 0) > L.run + 5 * MIN;
      if (!lost && !dead) return;
      st.rel[sp.id] = now; st.tried[sp.id] = st.tried[sp.id] || now;
      post({ action: "merge", key: "salesPush", patch: { status: "error", doneAt: now, text: stopped ? "어사이드가 쉬는 중이라 못 받음 · 조금 뒤 다시 눌러 주세요" : dead ? "읽다가 멈춤 (탭이 닫힘) · 다시 눌러 주세요" : "어사이드가 받지 못함 · 다시 눌러 주세요", cur: null, prog: null } });
    };

    // 책상이 살아 있음을 가끔 적음 (클라우드에서 보임). 상태가 바뀔 때도 적음
    const deskBeat = (force) => {
      if (cfg.reads === "off" && cfg.orders === "off") return;
      if (!force && now - (st.deskBeatAt || 0) < L.deskBeat) return;
      st.deskBeatAt = now;
      post({ action: "set", key: "asideDesk", value: { at: now, reads: cfg.reads, orders: cfg.orders, instr: (st.instr || "").split("|")[0], fails: st.fails, stop: st.stop ? st.stop.why : "", run: st.run ? { ch: st.run.ch, id: st.run.id, stage: st.run.stage } : null, ver: VER } });
    };
    const failOne = (why) => {
      st.fails++;
      st.last = { at: now, ok: false, text: why };
      log("실패 " + st.fails + "번째: " + why);
      if (st.fails >= L.maxFail && !st.stop) {
        st.stops = (st.stops || 0) + 1;
        const cool = Math.min(L.coolMax, L.coolOff * Math.pow(2, st.stops - 1));
        st.stop = { at: now, until: now + cool, why: `잇달아 ${st.fails}번 실패 — 마지막: ${why} (${Math.round(cool / MIN)}분 쉬고 다시 해 봄)` };
        post({ action: "set", key: "asideDiag", value: { at: now, code: "fail3", why: st.stop.why.slice(0, 200), until: st.stop.until, ver: VER } });
      }
    };

    // ---------- 1) 하던 읽기 살피기 ----------
    if (st.run) {
      const R = st.run, shadow = R.ch === "asidePush";
      const rq = shadow ? (full && fullAt >= R.since ? full.asidePush : null) : sp;
      if (shadow && now - fullAt >= L.fullRun) wantFull = true;
      const mine = rq && String(rq.id) === String(R.id);
      const finish = (ok, text) => {
        // 스스로 낸 요청이면 다음 차례를 정함 (확장 bg.js 와 같은 규칙)
        if (R.src === "per") {
          const failN = ok ? 0 : Math.min(9, (+st.per.failN || 0) + 1), max = lib.periodMaxRetry == null ? 3 : lib.periodMaxRetry;
          st.per = Object.assign({}, st.per, { okAt: now, ok, failN, next: ok || failN > max ? 0 : now + lib.periodBackoff(failN) });
        }
        if (R.src === "auto") st.auto = Object.assign({}, st.auto, { doneAt: now }, ok ? { next: now + MIN } : {});
        st.run = null;
        st.close = { at: now, until: now + L.closeShow, text };
        if (ok) { st.fails = 0; st.last = { at: now, ok: true, text }; log("끝: " + text); } else failOne(text);
        deskBeat(true);
      };
      if (!shadow && !mine && sp.id && sp.status === "pending" && now - (sp.at || 0) < L.salesAge) {
        // 그새 새 요청이 들어옴(폰에서 다시 누름): 읽기 코드는 하던 일을 멈추고 새 요청은 맡지 않음 → 확장처럼 "이 탭 닫고 새로"
        //  실패로 세지 않음. 탭 닫기를 잠깐 보여 준 뒤 아래 4)에서 새 요청으로 읽기 시작을 다시 띄움
        log("새 매출 요청이 들어옴 → 이 탭 닫고 새로");
        if (R.src === "per") st.per = Object.assign({}, st.per, { next: now + L.perWait });
        st.run = null;
        st.close = { at: now, until: now + L.closeShow, text: "새 요청이 들어옴 — 하던 탭을 닫고 새로 시작" };
        return out("CLOSE", st.close.text);
      }
      if (mine && /^(done|error)$/.test(rq.status || "")) {
        if (shadow) {
          const one = (((full || {}).asideShadow || {}).runs || {})[R.id];
          if (!one) {
            if (now - (R.doneSeen || (R.doneSeen = now)) < 2 * MIN) { wantFull = true; return out("WAIT", "맞춰 본 결과를 기다리는 중", { mode: "shadow", job: "read" }); }
            finish(false, "섀도: 요약이 안 남음"); return out("CLOSE", st.close.text);
          }
          st.shadowLast = { id: R.id, at: now, ok: !!one.ok, same: one.same || 0, nDiff: one.nDiff || 0, nMiss: one.nMiss || 0, kind: one.kind };
          finish(rq.status === "done", `섀도 ${rq.status === "done" ? "읽음" : "읽기 실패"} · 같음 ${one.same || 0} · 다름 ${one.nDiff || 0} · 없음 ${one.nMiss || 0}`);
        } else finish(rq.status === "done", rq.status === "done" ? "읽기 끝" : "읽기 실패");
        return out("CLOSE", st.close.text);
      }
      if (mine && rq.status === "running") {
        if (R.stage !== "running") { R.stage = "running"; R.runAt = now; }
        if (now - R.runAt > L.run) {
          post({ action: "merge", key: R.ch, patch: { status: "error", doneAt: now, text: `어사이드가 ${Math.round(L.run / MIN)}분 안에 못 끝냄 · 다시 눌러 주세요`, cur: null, prog: null } });
          finish(false, "읽기 시간 초과"); return out("CLOSE", st.close.text);
        }
        return out("WAIT", "읽는 중 — MIS 탭을 닫지 마세요", { mode: shadow ? "shadow" : "live", job: "read" });
      }
      // 내 요청이 시트에 안 보임(쓰기 실패·시트 못 읽음): 남의 요청 칸에 오류를 적지 않고 이번 차례만 접음
      if (!mine && now - R.since > (shadow ? 3 : 2) * MIN && (!shadow || fullAt >= R.since)) { st.tried[R.id] = now; finish(false, "요청이 시트에 안 보임 (인터넷 확인)"); return out("CLOSE", st.close.text); }
      // 아직 아무도 안 맡음(pending) 또는 아직 못 읽음
      if (now - R.since > L.pickup) {
        if (mine) post({ action: "merge", key: R.ch, patch: { status: "error", doneAt: now, text: `어사이드가 ${Math.round(L.pickup / MIN)}분 안에 시작 못 함 · 멈춘 곳: 시작 코드 실행 전 · 다시 눌러 주세요`, cur: null, prog: null } });
        st.tried[R.id] = now;
        finish(false, "시작 코드가 실행되지 않음"); return out("CLOSE", st.close.text);
      }
      if (!shadow && orderPending && R.src !== "ext") return out("WAIT", "발주 전송이 먼저 — 끝나면 읽기 시작", { mode: "live", job: "read" });
      return out("READ", R.why || "", { mode: shadow ? "shadow" : "live", job: "read" });
    }

    // ---------- 2) 멈춤 ----------
    //  쉬는 동안 들어온 요청은 받지 못함 → 폰이 '받는 중'에 갇히지 않게 3분 뒤 오류를 적어 풀어 줌 (요청마다 한 번)
    if (st.stop) {
      janitor(true);
      if (cfg.orders === "live" && orderPending && now - (mp.at || 0) > L.orderStuck && st.orderErr !== mp.id && !(ag.at && ag.grid === true && now - ag.at < L.armStale)) {
        st.orderErr = mp.id;
        post({ action: "merge", key: "misPush", patch: { status: "error", doneAt: now, text: "PC 자동입력이 쉬는 중 · 멈춘 곳: 발주 대기 탭이 꺼져 있음 → MIS에 직접 넣어 주세요" } });
      }
      deskBeat(); return out("STOP", st.stop.why);
    }
    {
      const waiting = cfg.reads === "live" && (light.salesPush || {}).status === "pending" && now - ((light.salesPush || {}).at || 0) < L.salesAge && !st.tried[(light.salesPush || {}).id];
      if (st.close && now < (waiting ? Math.min(st.close.until, (st.close.at || 0) + L.closeMin) : st.close.until)) return out("CLOSE", st.close.text);
      st.close = null;
    }
    if (cfg.reads === "off" && cfg.orders === "off") return out("IDLE", "꺼져 있음 (asideCfg 가 없거나 off)");

    // ---------- 3) 발주 (orders: live) — 주문등록 화면에 자동 대기 탭을 켜 둠 ----------
    if (cfg.orders === "live") {
      const armed = !!ag.at && ag.grid === true && now - ag.at < L.armStale;
      if (orderPending && !armed && now - (mp.at || 0) > L.orderStuck && st.orderErr !== mp.id) {
        st.orderErr = mp.id;
        post({ action: "merge", key: "misPush", patch: { status: "error", doneAt: now, text: `PC 자동입력이 ${Math.round(L.orderStuck / MIN)}분 안에 시작 못 함 · 멈춘 곳: 발주 대기 탭이 꺼져 있음 → MIS에 직접 넣어 주세요` } });
        failOne("발주 대기 탭이 꺼져 있어 전송을 못 받음");
        if (st.stop) return out("STOP", st.stop.why);
      }
      if (!armed) { deskBeat(); return out("ARM", orderPending ? "급함: 폰이 전송을 기다리는 중" : "발주 대기 탭이 꺼져 있음", { mode: "live", job: "order", urgent: orderPending ? 1 : 0 }); }
    }

    // ---------- 4) 읽기 (reads: live) — 확장의 차례 그대로: 들어온 요청 → 당일 되풀이 → 상시 수집 ----------
    if (cfg.reads === "live") {
      // 확장(GW Agent)이 아직 켜져 있으면 같은 요청을 둘이 받게 됨 → 책상은 물러섬 (확장이 적는 misAgent.ver 는 "1.17.7" 같은 모양)
      if (ag.at && /^\d+\.\d+/.test(String(ag.ver || "")) && now - ag.at < 15 * MIN) { deskBeat(); return out("STOP", "GW Agent 확장이 켜져 있어요 — 확장을 끄거나 설정을 shadow 로 (둘이 같은 요청을 받으면 안 됨)", { soft: 1 }); }
      if (cfg.orders !== "live" && now - (st.beatAt || 0) > L.beat) { st.beatAt = now; post({ action: "set", key: "misAgent", value: { at: now, mode: "ondemand", ver: VER, auto: 1 } }); }
      const salesWaiting = sp.status === "pending" && now - (sp.at || 0) < L.salesAge && !st.tried[sp.id];
      janitor(false);
      if (orderPending && cfg.orders !== "live") { deskBeat(); return out("IDLE", "발주 전송 중 (GW Agent 가 맡음) — 읽기는 잠시 쉼"); }
      if (salesWaiting && !orderBusy) {
        st.tried[sp.id] = now;
        st.run = { ch: "salesPush", id: sp.id, since: now, src: "ext", stage: "pending", why: "들어온 요청" };
        deskBeat(true);
        return out("READ", "들어온 요청", { mode: "live", job: "read" });
      }
      // 당일 되풀이 (12·16·20시 등, gw-plan.json)
      if (lib.periodDue && now >= (st.per.next || 0)) {
        const r = lib.periodDue(now, st.per, lib.periodJobs(plan), { maxPerDay: L.perMax });
        if (r.go) {
          const why = lib.periodBlocked(light, now, st.per.reqId ? "s" + st.per.reqId : "");
          if (why) st.per = Object.assign({}, st.per, r.st, { why, next: now + L.perWait });
          else {
            const req = lib.periodBundle(now, r.jobs, "aside-hour"), jobAt = Object.assign({}, r.st.jobAt || {});
            r.jobs.forEach((j) => { jobAt[j.kind] = now; });
            post({ action: "set", key: "salesPush", value: req });
            st.per = Object.assign({}, st.per, r.st, { day: r.day, at: now, n: (r.st.n || 0) + 1, jobAt, reqId: req.id, reqAt: now, ok: null, why: r.why, next: now + L.perWait });
            st.tried[req.id] = now;
            st.run = { ch: "salesPush", id: req.id, since: now, src: "per", stage: "pending", why: r.why };
            log("당일 되풀이 · " + r.why + " → 요청");
            deskBeat(true);
            return out("READ", r.why, { mode: "live", job: "read" });
          }
        } else st.per = Object.assign({}, st.per, r.st, { why: r.why });
      }
      // 상시 수집 (어제까지 매출·메뉴 + 계획표의 하루 한 번 일): 30분마다 시트 전체를 보고 정함
      if (lib.autoPlan && now >= (st.auto.next || 0)) {
        const A = st.auto.day === T ? st.auto : Object.assign({}, st.auto, { day: T, n: 0 });
        const rest = inSkip ? ["쉼: 발주 시간대", atKst(T, cfg.orderSkip[1] + 1)] : hm < 6 * 60 ? ["쉼: 밤", atKst(T, 6 * 60)] : hm > 23 * 60 + 30 ? ["쉼: 밤", atKst(addDay(T, 1), 6 * 60)] : null;
        if (rest) st.auto = Object.assign({}, A, { msg: rest[0], next: rest[1] });
        else if (now - (input.fullFailAt || 0) < L.autoRetry) st.auto = Object.assign({}, A, { msg: "시트를 못 읽음 (인터넷 확인)", next: (input.fullFailAt || 0) + L.autoRetry });
        else if (!full || now - fullAt > MIN) { wantFull = true; st.auto = A; }
        else {
          const r = lib.autoPlan(full, now, plan || [], { pc: true });
          if (r.act === "request") {
            if ((A.n || 0) >= L.autoMax) st.auto = Object.assign({}, A, { msg: `오늘 ${A.n}번 요청했지만 다 못 받음 · 내일 다시`, next: now + L.autoIdle });
            else {
              const req = r.make(now);
              post({ action: "set", key: "salesPush", value: req });
              st.auto = Object.assign({}, A, { n: (A.n || 0) + 1, reqId: req.id, reqAt: now, msg: "받는 중: " + r.label, next: now + L.autoEvery });
              st.tried[req.id] = now;
              st.run = { ch: "salesPush", id: req.id, since: now, src: "auto", stage: "pending", why: r.label };
              log("상시 수집 · " + r.label + " → 요청");
              deskBeat(true);
              return out("READ", r.label, { mode: "live", job: "read" });
            }
          } else if (r.act === "none") st.auto = Object.assign({}, A, { msg: r.why === "최신" ? "다 받아 둠" : r.why, okAt: now, next: now + L.autoIdle });
          else st.auto = Object.assign({}, A, { msg: "쉼: " + r.why, next: now + L.autoEvery });
        }
      }
      deskBeat();
      return out("IDLE", st.per.why || st.auto.msg || "다음 차례를 기다림");
    }

    // ---------- 5) 읽기 (reads: shadow) — 정한 시각에 한 번, GW Agent 가 쉬는 틈에 ----------
    if (cfg.reads === "shadow") {
      const slot = cfg.shadow.times.map((t) => ({ t, hm: HHMM(t) })).find((s) => hm >= s.hm && hm < s.hm + cfg.shadow.slotMin && !st.sh.done[s.t]);
      if (slot && now >= (st.sh.next || 0)) {
        const busy = inSkip ? "발주 시간대" : orderBusy ? "발주 전송 중" : (sp.status === "running" && now - (sp.startAt || sp.at || 0) < 14 * MIN) || (sp.status === "pending" && now - (sp.at || 0) < 6 * MIN) ? "GW Agent 가 읽는 중" : "";
        if (busy) { st.sh.next = now + L.shadowWait; st.sh.why = busy; }
        else {
          const req = shadowBundle(now, cfg.shadow.kinds);
          if (req) {
            post({ action: "set", key: "asidePush", value: req });
            st.sh.done[slot.t] = req.id; st.sh.why = "";
            st.run = { ch: "asidePush", id: req.id, since: now, src: "shadow", stage: "pending", why: "섀도 " + slot.t + " · " + cfg.shadow.kinds.join("·") };
            log("섀도 " + slot.t + " → 요청 (" + cfg.shadow.kinds.join("·") + ")");
            deskBeat(true);
            return out("READ", st.run.why, { mode: "shadow", job: "read" });
          }
        }
      }
      deskBeat();
      const nextT = cfg.shadow.times.map((t) => ({ t, hm: HHMM(t) })).filter((s) => !st.sh.done[s.t] && s.hm + cfg.shadow.slotMin > hm).map((s) => s.t)[0];
      return out("IDLE", slot ? "섀도 대기: " + (st.sh.why || "") : nextT ? "다음 섀도 " + nextT : "오늘 섀도 끝");
    }
    deskBeat();
    return out("IDLE", "발주 대기 켜져 있음");
  }

  // 어사이드가 실행할 시작 코드 한 줄 (북마크로도 쓸 수 있는 모양)
  function snippet(here, mode, job) {
    const src = String(here || "").replace(/\/?$/, "/") + "starter.js?mode=" + (mode === "live" ? "live" : "shadow") + (job === "order" ? "&job=order" : "");
    return `(()=>{const s=document.createElement('script');s.charset='utf-8';s.src='${src}&t='+Date.now();document.body.appendChild(s)})()`;
  }
  // 어사이드에게 보여 줄 순서 글
  function steps(instr) {
    const c = instr.code;
    if (c === "READ") return ["새 탭에서 GW 를 열고 [경영정보]를 눌러 MIS 첫 화면을 띄운다 (로그인 창이 나오면 멈추고 [막힘: 로그인 창]을 누른다)", "MIS 첫 화면에서 아래 '시작 코드'를 실행한다", "이 화면이 '탭 닫기'로 바뀔 때까지 기다린다 (MIS 화면은 건드리지 않는다)"];
    if (c === "ARM") return ["새 탭에서 GW 를 열고 [경영정보]를 눌러 MIS 첫 화면을 띄운다", "MIS 첫 화면에서 아래 '시작 코드'를 실행한다", "MIS 화면 오른쪽 아래에 '발주앱 자동입력 · 대기 중'이 보이면 끝. 이 MIS 탭은 닫지 않는다"];
    if (c === "WAIT") return ["아무것도 누르지 않고 기다린다"];
    if (c === "CLOSE") return ["읽기에 쓴 MIS 탭과 GW 탭을 닫는다 (발주 대기 탭은 닫지 않는다)"];
    if (c === "STOP") return ["아무것도 하지 않는다", "KM 에게 '멈춤' 글을 그대로 알린다"];
    return ["할 일 없음"];
  }

  // 어사이드가 [막힘] 단추를 눌렀을 때: 하던 일을 접고 멈춤(쉬는 시간 뒤 스스로 다시 해 봄). 돌려주는 것은 새 st 와 시트에 적을 한 줄
  function stuck(stIn, now, why, cfgIn) {
    const st = clone(stIn), L = mergeCfg(cfgIn).lim;
    const posts = [];
    if (st.run) {
      posts.push({ action: "merge", key: st.run.ch, patch: { status: "error", doneAt: now, text: `어사이드가 알림: ${String(why).slice(0, 80)} · 조금 뒤 다시 눌러 주세요`, cur: null, prog: null } });
      st.tried = st.tried || {}; st.tried[st.run.id] = now; st.run = null;
    }
    st.stops = (st.stops || 0) + 1; st.fails = Math.max(st.fails || 0, L.maxFail);
    const cool = Math.min(L.coolMax, L.coolOff * Math.pow(2, st.stops - 1));
    st.stop = { at: now, until: now + cool, why: `어사이드가 알림: ${why} (${Math.round(cool / MIN)}분 쉬고 다시 해 봄)` };
    st.last = { at: now, ok: false, text: why };
    posts.push({ action: "set", key: "asideDiag", value: { at: now, code: "stuck", why: String(why).slice(0, 200), until: st.stop.until, ver: VER } });
    return { st, posts };
  }

  G.AsideDesk = { decide, mergeCfg, shadowBundle, snippet, steps, stuck, DEF, VER, ymd, hmOf };
})(typeof self !== "undefined" ? self : globalThis);
