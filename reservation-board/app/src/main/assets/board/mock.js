/*
 * 브라우저 미리보기용 견본 데이터. 안드로이드 앱 안에서는 window.Android가 있어서 쓰이지 않습니다.
 * 이름과 예약 내용은 모두 지어낸 견본이에요.
 */
(function () {
  'use strict';
  if (window.Android) return;

  const now = Date.now();
  const min = 60000;
  const d = new Date(now);
  const md = (d.getMonth() + 1) + '.' + d.getDate() + '(' + '일월화수목금토'[d.getDay()] + ')';
  const t = new Date(now + 86400000);
  const mdNext = (t.getMonth() + 1) + '.' + t.getDate() + '(' + '일월화수목금토'[t.getDay()] + ')';
  const NAVER = 'com.naver.smartplace';
  const OWN = 'kr.co.ourshop.owner';

  let nextId = 100;
  let testSource = 0;
  const sources = [
    { name: '네이버', packages: [{ pkg: NAVER, label: '네이버 스마트플레이스' }], keywords: '' },
    { name: '자사앱', packages: [{ pkg: OWN, label: '우리가게 사장님' }], keywords: '' },
  ];
  const settings = { sound: true, voice: true, textSize: 0 };
  let entries = [
    [2, 0, NAVER, '[네이버 예약] 새로운 예약이 들어왔어요', '박민수님 · ' + md + ' 20:00 · 6명\n요청사항: 유아용 의자 1개 부탁드려요', true],
    [9, 1, OWN, '예약 접수', '최지우님 · 오늘 20:30 · 3명', true],
    [41, 0, NAVER, '[네이버 예약] 예약이 확정되었어요', '김서연님 · ' + md + ' 19:00 · 4명\n요청사항: 창가 자리 부탁드려요', false],
    [112, 1, OWN, '예약 접수', '이도윤님 · 오늘 19:30 · 2명', false],
    [190, 0, NAVER, '[네이버 예약] 예약이 취소되었어요', '정하은님 · ' + md + ' 18:00 · 2명', false],
    [251, 0, NAVER, '[네이버 예약] 새로운 예약이 들어왔어요', '윤재희님 · ' + mdNext + ' 12:30 · 5명', false],
    [1460, 1, OWN, '단체 예약 접수', '한지민님 · ' + md + ' 18:30 · 8명\n단체석 요청', false],
  ].map(([ago, source, pkg, title, body, isNew], i) => ({ id: i + 1, posted: now - ago * min, source, pkg, title, body, isNew }));

  const seen = { [NAVER]: now - 2 * min, [OWN]: now - 9 * min, 'com.kakao.talk': now - 30 * min };
  const apps = [
    { pkg: NAVER, label: '네이버 스마트플레이스' },
    { pkg: OWN, label: '우리가게 사장님' },
    { pkg: 'com.kakao.talk', label: '카카오톡' },
    { pkg: 'com.nhn.android.search', label: '네이버' },
    { pkg: 'com.samsung.android.messaging', label: '메시지' },
    { pkg: 'com.baemin.owner', label: '배민사장님' },
    { pkg: 'com.coupang.eats.store', label: '쿠팡이츠 스토어' },
    { pkg: 'com.google.android.gm', label: 'Gmail' },
  ];

  function toast(text) {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = text;
    el.classList.add('on');
    setTimeout(() => el.classList.remove('on'), 2000);
  }

  window.MockAndroid = {
    state() {
      return JSON.stringify({
        listener: { enabled: true, connected: true },
        settings,
        sources,
        icons: {},
        entries: entries.slice().sort((a, b) => b.posted - a.posted),
      });
    },
    apps() {
      return JSON.stringify(apps.map((a) => ({ ...a, seen: seen[a.pkg] || 0 }))
        .sort((a, b) => (b.seen - a.seen) || a.label.localeCompare(b.label, 'ko')));
    },
    ack(id) { entries.forEach((e) => { if (String(e.id) === String(id)) e.isNew = false; }); },
    ackAll() { entries.forEach((e) => { e.isNew = false; }); },
    open(id) { this.ack(id); toast('원래 앱에서 이 예약을 열어요'); },
    test() {
      const source = testSource;
      testSource = (testSource + 1) % 2;
      const e = { id: nextId++, posted: Date.now(), source, pkg: 'kr.store.reservationboard',
        title: '[테스트] 홍길동님 예약', body: '오늘 19:00 · 4명\n테스트 알림이에요.', isNew: true };
      entries.push(e);
      window.board.onEntry(e.id, source);
    },
    clear() { entries = []; },
    saveSource(i, json) { Object.assign(sources[Number(i)], JSON.parse(json)); },
    setPackages(i, json) {
      const picked = JSON.parse(json);
      sources.forEach((s, j) => { if (j !== Number(i)) s.packages = s.packages.filter((p) => !picked.includes(p.pkg)); });
      sources[Number(i)].packages = picked.map((pkg) => ({ pkg, label: (apps.find((a) => a.pkg === pkg) || { label: pkg }).label }));
    },
    setSetting(key, value) { settings[key] = key === 'textSize' ? Number(value) : value === 'true'; },
    openListenerSettings() { toast('태블릿의 알림 접근 설정이 열려요'); },
    openBatterySettings() { toast('태블릿의 배터리 설정이 열려요'); },
  };
})();
