/*
 * 예약 알림판 화면. 데이터는 안드로이드 쪽(window.Android)에서 받고,
 * 브라우저에서 미리 볼 때는 mock.js의 견본 데이터(window.MockAndroid)를 씁니다.
 */
(function () {
  'use strict';

  const api = window.Android || window.MockAndroid;
  const SCALES = [1, 1.15, 1.3];
  const DAY = 24 * 60 * 60 * 1000;
  const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

  let state = null;
  let filter = -1;
  let pickerSource = 0;
  let pickerApps = [];
  let pickerChosen = new Set();

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pad2 = (n) => String(n).padStart(2, '0');
  const hhmm = (t) => { const d = new Date(t); return pad2(d.getHours()) + ':' + pad2(d.getMinutes()); };

  function startOfDay(t) {
    const d = new Date(t);
    d.setHours(0, 0, 0, 0);
    return d.getTime();
  }

  function ago(ms) {
    const min = Math.floor(ms / 60000);
    if (min < 1) return '방금';
    if (min < 60) return min + '분 전';
    const h = Math.floor(min / 60);
    return h < 24 ? h + '시간 전' : '';
  }

  function sourceName(i) {
    return state.sources[i] ? state.sources[i].name : '';
  }

  function load() {
    state = JSON.parse(api.state());
    document.documentElement.style.setProperty('--scale', SCALES[state.settings.textSize] || 1);
  }

  // ---- 위쪽 막대 ----

  function renderTop() {
    const now = new Date();
    $('date').textContent = (now.getMonth() + 1) + '월 ' + now.getDate() + '일 ' + WEEKDAYS[now.getDay()] + '요일';
    $('time').textContent = hhmm(now);
    const live = state.listener.enabled && state.listener.connected;
    const status = $('status');
    status.className = 'pill ' + (live ? 'pill-positive' : 'pill-negative');
    status.textContent = live ? '수신 중' : '수신 안 됨';
  }

  // ---- 알림판 ----

  function today() {
    const start = startOfDay(Date.now());
    return state.entries.filter((e) => e.posted >= start);
  }

  function renderFinding() {
    const fresh = state.entries.filter((e) => e.isNew).length;
    const last = state.entries[0];
    const lastText = last ? '마지막 수신 ' + hhmm(last.posted) + ' ' + esc(sourceName(last.source)) : '';
    let html;
    if (today().length === 0 && fresh === 0) {
      html = '아직 오늘 들어온 예약 알림이 없어요.' + (last ? ' · ' + lastText : '');
    } else if (fresh > 0) {
      html = '<strong>확인 안 한 새 예약 ' + fresh + '건</strong>이 있어요 · ' + lastText;
    } else {
      html = '모두 확인했어요 · ' + lastText;
    }
    $('finding').innerHTML = html;
  }

  /** 오늘 받은 알림을 영업시간 축 위에 점으로 찍습니다. 몰리는 시간대가 한눈에 보여요. */
  function renderFlow() {
    const now = Date.now();
    const base = startOfDay(now);
    const rows = today();
    const hours = rows.map((e) => (e.posted - base) / 3600000);
    const nowH = (now - base) / 3600000;
    let start = Math.min(9, Math.floor(Math.min(nowH, ...hours)));
    let end = Math.max(22, Math.ceil(Math.max(nowH, ...hours)));
    end = Math.min(24, end);
    start = Math.max(0, Math.min(start, end - 6));
    const span = end - start;
    const step = span > 14 ? 3 : 2;
    const at = (h) => ((h - start) / span) * 100;

    let track = '<span class="flow-now" style="left:' + at(nowH).toFixed(2) + '%" title="지금 ' + hhmm(now) + '"></span>';
    rows.slice().reverse().forEach((e) => {
      const h = (e.posted - base) / 3600000;
      track += '<button type="button" class="flow-dot' + (e.isNew ? ' is-new' : '') + '" data-id="' + e.id + '"'
        + ' style="left:' + at(h).toFixed(2) + '%;background:var(' + (e.source === 0 ? '--naver' : '--own') + ')"'
        + ' aria-label="' + hhmm(e.posted) + ' ' + esc(sourceName(e.source)) + ' ' + esc(e.title) + '"></button>';
    });
    $('flow-track').innerHTML = track;

    let axis = '';
    for (let h = start; h <= end; h += step) axis += '<span style="left:' + at(h).toFixed(2) + '%">' + h + '시</span>';
    if ((end - start) % step !== 0) axis += '<span style="left:100%">' + end + '시</span>';
    $('flow-axis').innerHTML = axis;

    $('legend').innerHTML = state.sources.map((s, i) =>
      '<span><i style="background:var(' + (i === 0 ? '--naver' : '--own') + ')"></i>' + esc(s.name) + '</span>').join('')
      + '<span><i class="ring"></i>확인 전</span>';
  }

  function renderNotice() {
    let html = '';
    if (!state.listener.enabled) {
      html = '<div class="notice notice-negative"><p><strong>알림 접근 권한이 꺼져 있어서 예약을 받을 수 없어요.</strong> '
        + '권한을 켜면 바로 여기에 모이기 시작해요.</p>'
        + '<button class="button button-primary" type="button" data-call="openListenerSettings">권한 켜기</button></div>';
    } else if (!state.sources.some((s) => s.packages.length)) {
      html = '<div class="notice notice-notice"><p><strong>네이버와 자사앱이 태블릿의 어떤 앱인지 아직 고르지 않았어요.</strong> '
        + '설정에서 한 번만 골라 주세요.</p>'
        + '<a class="button button-primary" href="#settings">앱 고르기</a></div>';
    }
    $('notice').innerHTML = html;
  }

  function renderTabs() {
    const rows = today();
    const tabs = [{ i: -1, name: '전체', n: rows.length }].concat(
      state.sources.map((s, i) => ({ i, name: s.name, n: rows.filter((e) => e.source === i).length })));
    $('tabs').innerHTML = tabs.map((t) =>
      '<button type="button" class="tab" role="tab" data-filter="' + t.i + '" aria-selected="' + (filter === t.i) + '">'
      + esc(t.name) + ' <b>' + t.n + '</b></button>').join('');
    const fresh = state.entries.filter((e) => e.isNew).length;
    const ack = $('ack-all');
    ack.hidden = fresh === 0;
    ack.textContent = '새 예약 ' + fresh + '건 모두 확인';
  }

  function icon(e) {
    const url = state.icons[e.pkg];
    if (url) return '<img src="' + esc(url) + '" alt="">';
    return '<span class="glyph" aria-hidden="true">' + esc(sourceName(e.source).charAt(0)) + '</span>';
  }

  function dayLabel(t) {
    const base = startOfDay(Date.now());
    if (t >= base - DAY) return '어제';
    const d = new Date(t);
    return (d.getMonth() + 1) + '월 ' + d.getDate() + '일 ' + WEEKDAYS[d.getDay()] + '요일';
  }

  /** 제목 앞의 "[네이버 예약]" 같은 말머리는 출처 표시와 겹치니 화면에서만 뺍니다. */
  function displayTitle(e) {
    const t = (e.title || '').replace(/^\[[^\]]{1,16}\]\s*/, '');
    return t || e.title || sourceName(e.source) + ' 알림';
  }

  function rowHtml(e, now) {
    const name = sourceName(e.source);
    const side = e.isNew
      ? '<button class="button button-outline" type="button" data-ack="' + e.id + '">확인</button>'
      : '<span class="seen-label">확인함</span>';
    return '<article class="row ' + (e.isNew ? 'is-new' : 'is-seen') + '" data-id="' + e.id + '" tabindex="0"'
      + ' aria-label="' + esc(name + ' ' + hhmm(e.posted) + ' ' + e.title) + '">'
      + '<div class="row-time"><time class="num">' + hhmm(e.posted) + '</time><small data-posted="' + e.posted + '">' + ago(now - e.posted) + '</small></div>'
      + '<span class="source source-' + e.source + '">' + icon(e) + esc(name) + '</span>'
      + '<div class="row-main"><div class="row-title">'
      + (e.isNew ? '<span class="pill pill-notice">새 예약</span>' : '')
      + '<span>' + esc(displayTitle(e)) + '</span></div>'
      + (e.body ? '<p class="row-body">' + esc(e.body) + '</p>' : '') + '</div>'
      + '<div class="row-side">' + side
      + '<svg class="chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m7.5 5 5 5-5 5"/></svg></div>'
      + '</article>';
  }

  function renderList() {
    const now = Date.now();
    const base = startOfDay(now);
    const rows = state.entries.filter((e) => filter < 0 || e.source === filter);
    if (!rows.length) {
      const scope = filter < 0 ? '' : esc(sourceName(filter)) + ' ';
      $('list').innerHTML = '<div class="empty"><strong>최근 이틀 동안 들어온 ' + scope + '예약 알림이 없어요</strong>'
        + '새 예약이 오면 소리와 함께 여기 맨 위에 나타나요.<br>'
        + '<button class="button button-outline" type="button" id="empty-test">테스트 알림 보내기</button></div>';
      return;
    }
    const groups = [];
    rows.forEach((e) => {
      const key = e.posted >= base ? 'today' : String(startOfDay(e.posted));
      let g = groups[groups.length - 1];
      if (!g || g.key !== key) groups.push(g = { key, label: key === 'today' ? '' : dayLabel(e.posted), rows: [] });
      g.rows.push(e);
    });
    let html = '';
    if (groups[0].key !== 'today') {
      html += '<p class="empty-today">오늘 들어온 ' + (filter < 0 ? '' : esc(sourceName(filter)) + ' ') + '예약 알림은 아직 없어요.</p>';
    }
    groups.forEach((g) => {
      if (g.label) html += '<h2 class="day-label">' + g.label + '</h2>';
      html += '<div class="rows">' + g.rows.map((e) => rowHtml(e, now)).join('') + '</div>';
    });
    $('list').innerHTML = html;
  }

  function renderBoard() {
    renderFinding();
    renderFlow();
    renderNotice();
    renderTabs();
    renderList();
  }

  function tickTimes() {
    const now = Date.now();
    document.querySelectorAll('small[data-posted]').forEach((el) => {
      el.textContent = ago(now - Number(el.dataset.posted));
    });
  }

  // ---- 설정 ----

  function renderSettings() {
    const perm = $('perm-pill');
    perm.className = 'pill ' + (state.listener.enabled ? 'pill-positive' : 'pill-negative');
    perm.textContent = state.listener.enabled ? '허용됨' : '꺼져 있음';

    $('sources').innerHTML = '<h2>예약 출처</h2>' + state.sources.map((s, i) => {
      const chosen = s.packages.length
        ? s.packages.map((p) => '<span class="chosen-app">'
          + (state.icons[p.pkg] ? '<img src="' + esc(state.icons[p.pkg]) + '" alt="">' : '')
          + esc(p.label) + '</span>').join('')
        : '<span class="chosen-none">아직 고르지 않았어요</span>';
      return '<div class="setting">'
        + '<div class="setting-label"><h3><span class="source-name"><i style="background:var(' + (i === 0 ? '--naver' : '--own') + ')"></i>'
        + esc(s.name) + '</span></h3>'
        + '<p>' + (i === 0
          ? '네이버 예약 알림이 오는 앱을 골라요. 보통 네이버 스마트플레이스 앱이에요.'
          : '자사앱 예약 알림이 오는 앱을 골라요. 외주로 만든 사장님용 앱이에요.') + '</p></div>'
        + '<div class="setting-control">'
        + '<label class="control-label" for="name-' + i + '">화면에 표시할 이름</label>'
        + '<input class="field" id="name-' + i + '" data-source="' + i + '" data-key="name" value="' + esc(s.name) + '" maxlength="12">'
        + '<span class="control-label">알림을 읽어올 앱</span>'
        + '<div class="chosen">' + chosen + '</div>'
        + '<button class="button button-outline" type="button" data-pick="' + i + '">앱 고르기</button>'
        + '<label class="control-label" for="kw-' + i + '">키워드 (선택)</label>'
        + '<input class="field" id="kw-' + i + '" data-source="' + i + '" data-key="keywords" value="' + esc(s.keywords) + '" placeholder="비워 두면 이 앱의 알림을 모두 보여 줘요">'
        + '<p class="help">리뷰·광고 알림까지 섞여 보이면 ‘예약’을 넣어 주세요. 쉼표로 여러 개 넣을 수 있어요 (예: 예약, 주문).</p>'
        + '</div></div>';
    }).join('');

    $('opt-sound').checked = state.settings.sound;
    $('opt-voice').checked = state.settings.voice;
    document.querySelectorAll('#opt-size button').forEach((b) => {
      b.setAttribute('aria-checked', String(Number(b.dataset.size) === state.settings.textSize));
    });
  }

  // ---- 앱 고르기 ----

  function openPicker(i) {
    pickerSource = i;
    pickerApps = JSON.parse(api.apps());
    pickerChosen = new Set(state.sources[i].packages.map((p) => p.pkg));
    $('picker-title').textContent = state.sources[i].name + ' 예약 알림을 보내는 앱';
    $('picker-search').value = '';
    renderPicker();
    $('picker').showModal();
  }

  function renderPicker() {
    const q = $('picker-search').value.trim().toLowerCase();
    const now = Date.now();
    const apps = pickerApps.filter((a) => !q || a.label.toLowerCase().includes(q));
    $('picker-list').innerHTML = apps.length ? apps.map((a) => {
      const recent = a.seen ? '<small class="recent">최근 알림 ' + (ago(now - a.seen) || '하루 넘음') + '</small>' : '<small>' + esc(a.pkg) + '</small>';
      const img = a.icon ? '<img src="' + esc(a.icon) + '" alt="">' : '<span class="glyph">' + esc(a.label.charAt(0)) + '</span>';
      return '<li><label>' + img + '<span><b>' + esc(a.label) + '</b>' + recent + '</span>'
        + '<input type="checkbox" value="' + esc(a.pkg) + '"' + (pickerChosen.has(a.pkg) ? ' checked' : '') + '></label></li>';
    }).join('') : '<li class="apps-empty">‘' + esc(q) + '’ 이름의 앱이 없어요.</li>';
  }

  // ---- 화면 전환과 알림 ----

  function route() {
    const view = location.hash === '#settings' ? 'settings' : 'board';
    document.body.dataset.view = view;
    $('view-board').hidden = view !== 'board';
    $('view-settings').hidden = view !== 'settings';
    if (view === 'settings') renderSettings();
    else renderBoard();
    window.scrollTo(0, 0);
  }

  function refresh() {
    load();
    renderTop();
    if (document.body.dataset.view === 'settings') renderSettings();
    else renderBoard();
  }

  let toastTimer;
  function toast(text) {
    const t = $('toast');
    t.textContent = text;
    t.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('on'), 2200);
  }

  function pulse(source) {
    const a = $('arrival');
    a.dataset.source = String(source);
    a.classList.remove('on');
    void a.offsetWidth;
    a.classList.add('on');
  }

  function point(id) {
    filter = -1;
    renderTabs();
    renderList();
    const row = document.querySelector('.row[data-id="' + id + '"]');
    if (!row) return;
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    row.classList.add('is-pointed');
    setTimeout(() => row.classList.remove('is-pointed'), 1600);
  }

  document.addEventListener('click', (ev) => {
    const t = ev.target.closest('[data-ack],[data-filter],[data-call],[data-pick],.row,.flow-dot,#ack-all,#empty-test,#test,#clear');
    if (!t) return;
    if (t.dataset.ack) {
      api.ack(t.dataset.ack);
      refresh();
    } else if (t.dataset.filter !== undefined) {
      filter = Number(t.dataset.filter);
      renderTabs();
      renderList();
    } else if (t.dataset.call) {
      api[t.dataset.call]();
    } else if (t.dataset.pick !== undefined) {
      openPicker(Number(t.dataset.pick));
    } else if (t.classList.contains('flow-dot')) {
      point(t.dataset.id);
    } else if (t.classList.contains('row')) {
      api.open(String(t.dataset.id));
      refresh();
    } else if (t.id === 'ack-all') {
      api.ackAll();
      refresh();
    } else if (t.id === 'empty-test' || t.id === 'test') {
      if (location.hash) location.hash = '';
      setTimeout(() => api.test(), 250);
    } else if (t.id === 'clear') {
      if (confirm('알림판의 기록을 모두 지울까요?\n네이버·자사앱의 실제 예약은 지워지지 않아요.')) {
        api.clear();
        refresh();
        toast('기록을 지웠어요');
      }
    }
  });

  document.addEventListener('keydown', (ev) => {
    if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.classList && ev.target.classList.contains('row')) {
      ev.preventDefault();
      ev.target.click();
    }
  });

  document.addEventListener('change', (ev) => {
    const t = ev.target;
    if (t.dataset && t.dataset.source !== undefined) {
      const i = Number(t.dataset.source);
      const s = state.sources[i];
      const name = t.dataset.key === 'name' ? (t.value.trim() || (i === 0 ? '네이버' : '자사앱')) : s.name;
      const keywords = t.dataset.key === 'keywords' ? t.value.trim() : s.keywords;
      api.saveSource(String(i), JSON.stringify({ name, keywords }));
      load();
      toast('저장했어요');
    } else if (t.id === 'opt-sound' || t.id === 'opt-voice') {
      api.setSetting(t.id === 'opt-sound' ? 'sound' : 'voice', String(t.checked));
      load();
      toast('저장했어요');
    } else if (t.closest && t.closest('#picker-list') && t.type === 'checkbox') {
      if (t.checked) pickerChosen.add(t.value); else pickerChosen.delete(t.value);
    }
  });

  $('opt-size').addEventListener('click', (ev) => {
    const b = ev.target.closest('button');
    if (!b) return;
    api.setSetting('textSize', b.dataset.size);
    load();
    renderSettings();
  });

  $('picker-search').addEventListener('input', renderPicker);
  $('picker').addEventListener('close', () => {
    if ($('picker').returnValue !== 'save') return;
    api.setPackages(String(pickerSource), JSON.stringify(Array.from(pickerChosen)));
    load();
    renderSettings();
    toast('저장했어요');
  });

  window.addEventListener('hashchange', route);

  // 안드로이드 쪽에서 부릅니다.
  window.board = {
    refresh,
    onEntry(id, source) {
      refresh();
      pulse(source);
      const row = document.querySelector('.row[data-id="' + id + '"]');
      if (row) row.classList.add('is-arriving');
    },
  };

  load();
  renderTop();
  route();
  setInterval(() => { renderTop(); tickTimes(); }, 10000);
  // 놓친 신호가 있어도 1분마다 다시 맞춥니다.
  setInterval(refresh, 60000);
})();
