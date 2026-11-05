// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: deep-purple; icon-glyph: fingerprint;
/* ============================================================================
 *  BOH 출퇴근 대시보드 위젯 · 매드포갈릭 수원컨벤션센터점
 *  Stageshow × Linear 벤토 스타일 / iOS Scriptable 홈 화면 위젯
 * ----------------------------------------------------------------------------
 *  · 당일 BOH(주방) 직원 + KM 전원의 세콤 지문 출퇴근 현황을 한눈에 표시
 *  · 스케줄상 출퇴근 시간(예정)과 지문 인식 시간(실제)을 나란히 표시
 *  · 외부 JSON(GitHub raw 등) 로드 → 실패 시 마지막 성공 캐시 → 내장 Fallback 순으로 안전 렌더
 *  · Large(권장) / Medium 위젯 지원, 30분 단위 자동 갱신
 *  · 테마: dark(기본, Stageshow 다크) / cream(발주앱 크림테마)
 *
 *  [설치]
 *   1. Scriptable 앱 → 새 스크립트 → 이 파일 내용 붙여넣기 → 저장
 *   2. 앱에서 ▶ 실행하면 Large 미리보기(presentLarge)가 바로 뜸
 *   3. 홈 화면 → 위젯 추가 → Scriptable(Large 또는 Medium) → Script 선택
 *   4. (선택) 위젯 Parameter 에 "cream" / "medium" / JSON URL 을 공백으로 구분해 입력
 *        예) cream https://raw.githubusercontent.com/.../boh-attendance.json
 *
 *  [JSON 스키마]  → boh-attendance.sample.json 참고
 *   {
 *     "store": "수원컨벤션 BOH",
 *     "date": "2026-11-05",
 *     "updatedAt": "2026-11-05T21:55:00+09:00",
 *     "closing": "완료",                       // 마감 상태 (생략 시 자동 계산)
 *     "note": "원대연 출근 지문 누락",          // 특이사항 메모 (선택)
 *     "staff": [
 *       { "name": "유신우", "role": "KM",
 *         "sched": { "in": "08:30", "out": "22:00" },   // 스케줄
 *         "tag":   { "in": "08:43", "out": "21:51" },   // 지문 인식
 *         "status": "off" }                              // 생략 시 자동 판정
 *     ]
 *   }
 *   status: off(퇴근완료) | working(근무중) | missing_in(출근미태그)
 *           | missing_out(퇴근미태그) | scheduled(출근예정) | dayoff(휴무)
 * ========================================================================== */

// ─────────────────────────────── 설정 ───────────────────────────────
const CONFIG = {
  // 세콤 출퇴근 현황 JSON (GitHub raw URL 등). 위젯 Parameter 의 URL 이 우선.
  DATA_URL: "https://raw.githubusercontent.com/mfgkorea/order.html/main/boh-attendance.json",
  THEME: "dark",              // "dark" | "cream"
  REFRESH_MINUTES: 30,        // 자동 갱신 주기(분)
  FETCH_TIMEOUT_SEC: 10,      // 네트워크 타임아웃(초)
  TAP_URL: "",                // 위젯 탭 시 열 URL (비우면 동작 없음)
  LATE_GRACE_MIN: 10,         // 스케줄 출근시간 + N분까지는 "출근예정"으로 표시
  OUT_GRACE_MIN: 60,          // 스케줄 퇴근시간 + N분 지나도 퇴근 지문 없으면 "퇴근미태그"
  PREVIEW_FAMILY: "large",    // 앱 내 실행 시 미리보기 크기 "large" | "medium"
};

// ─────────────────────────────── 테마 ───────────────────────────────
const THEMES = {
  dark: {
    name: "dark",
    bg: "#0B0F17", bgEnd: "#0D1320",
    tile: "#151D2A", tile2: "#1C2638", border: "#263247",
    text: "#F1F5F9", sub: "#94A3B8", muted: "#5B6B82",
    chipText: "#0B0F17",
  },
  cream: {
    name: "cream",
    bg: "#FAF9F5", bgEnd: "#F0EBDE",
    tile: "#FFFFFF", tile2: "#F5F0E8", border: "#E6DFD1",
    text: "#1C1917", sub: "#57534E", muted: "#A8A29E",
    chipText: "#FFFFFF",
  },
};

const ACCENT = {
  amber: "#F59E0B",   // KM 강조
  live: "#22C55E",    // 라이브 인디케이터
  macRed: "#FF5F57", macYellow: "#FEBC2E", macGreen: "#28C840",
};

const ROLE = {
  KM: { label: "KM", color: ACCENT.amber },
  OP: { label: "OP", color: "#38BDF8" },
  CL: { label: "CL", color: "#2DD4BF" },
  DEFAULT: { label: "BOH", color: "#94A3B8" },
};

const STATUS = {
  off:         { label: "퇴근완료",  color: "#C084FC", warn: false },
  working:     { label: "근무중",    color: "#4ADE80", warn: false },
  missing_in:  { label: "출근미태그", color: "#F87171", warn: true },
  missing_out: { label: "퇴근미태그", color: "#FB923C", warn: true },
  scheduled:   { label: "출근예정",  color: "#60A5FA", warn: false },
  dayoff:      { label: "휴무",      color: "#64748B", warn: false },
};

// ─────────────────────────── 내장 Fallback 데이터 ───────────────────────────
// 네트워크/캐시 모두 실패했을 때 사용. (스케줄 시간은 예시값)
const FALLBACK = {
  store: "수원컨벤션 BOH",
  date: "2026-11-05",
  updatedAt: "2026-11-05T21:55:00+09:00",
  closing: "완료",
  note: "원대연 출근 지문 누락",
  staff: [
    { name: "유신우", role: "KM", sched: { in: "08:30", out: "22:00" }, tag: { in: "08:43", out: "21:51" }, status: "off" },
    { name: "김해영", role: "OP", sched: { in: "09:00", out: "15:00" }, tag: { in: "08:57", out: "15:06" }, status: "off" },
    { name: "원대연", role: "OP", sched: { in: "09:00", out: "15:00" }, tag: { in: null,    out: "15:03" }, status: "missing_in" },
    { name: "박진석", role: "OP", sched: { in: "11:00", out: "16:00" }, tag: { in: "10:57", out: "16:18" }, status: "off" },
    { name: "정인욱", role: "CL", sched: { in: "17:00", out: "22:00" }, tag: { in: "16:52", out: "21:48" }, status: "off" },
    { name: "황아미", role: "CL", sched: { in: "17:00", out: "22:00" }, tag: { in: "16:57", out: "21:50" }, status: "off" },
    { name: "김동환", role: "CL", sched: { in: "17:00", out: "22:00" }, tag: { in: "16:58", out: "21:50" }, status: "off" },
  ],
};

// ─────────────────────────────── 유틸 ───────────────────────────────
const pad2 = (n) => String(n).padStart(2, "0");
const col = (hex, a) => (a == null ? new Color(hex) : new Color(hex, a));

function toMin(hhmm) {
  if (!hhmm || typeof hhmm !== "string") return null;
  const m = hhmm.match(/^(\d{1,2}):(\d{2})/);
  if (!m) return null;
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}

function parseYMD(s) {
  if (!s || typeof s !== "string") return null;
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  return new Date(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10));
}

function isSameDay(a, b) {
  return a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function fmtDateKo(d) {
  const days = ["일", "월", "화", "수", "목", "금", "토"];
  return `${pad2(d.getMonth() + 1)}.${pad2(d.getDate())} (${days[d.getDay()]})`;
}

function fmtHM(d) {
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function parseWidgetParam(raw) {
  const out = { theme: null, family: null, url: null };
  if (!raw || typeof raw !== "string") return out;
  for (const tok of raw.split(/[\s,|]+/).filter(Boolean)) {
    const t = tok.toLowerCase();
    if (t === "cream" || t === "dark") out.theme = t;
    else if (t === "medium" || t === "large") out.family = t;
    else if (/^https?:\/\//i.test(tok)) out.url = tok;
  }
  return out;
}

// ─────────────────────────── 데이터 로드 ───────────────────────────
function cachePath() {
  const fm = FileManager.local();
  return { fm, path: fm.joinPath(fm.cacheDirectory(), "boh-attendance-cache.json") };
}

function isValidPayload(d) {
  const list = d && (Array.isArray(d.staff) ? d.staff : Array.isArray(d.workers) ? d.workers : null);
  return !!(list && list.length && list.every((s) => s && typeof s.name === "string"));
}

function normalizePayload(d) {
  const list = Array.isArray(d.staff) ? d.staff : d.workers;
  return {
    store: d.store || FALLBACK.store,
    date: d.date || null,
    updatedAt: d.updatedAt || null,
    closing: d.closing || null,
    note: d.note || null,
    staff: list.map((s) => ({
      name: s.name,
      role: (s.role || "").toUpperCase(),
      sched: { in: s.sched?.in ?? s.schedIn ?? null, out: s.sched?.out ?? s.schedOut ?? null },
      tag: { in: s.tag?.in ?? s.tagIn ?? null, out: s.tag?.out ?? s.tagOut ?? null },
      status: s.status || null,
    })),
  };
}

async function fetchAttendance(url) {
  const { fm, path } = cachePath();

  // 1) 네트워크
  try {
    const req = new Request(url);
    req.timeoutInterval = CONFIG.FETCH_TIMEOUT_SEC;
    const json = await req.loadJSON();
    if (isValidPayload(json)) {
      try { fm.writeString(path, JSON.stringify(json)); } catch (_) {}
      return { data: normalizePayload(json), source: "live" };
    }
    console.warn("[BOH] JSON 스키마 불일치 → 캐시/Fallback 사용");
  } catch (e) {
    console.warn(`[BOH] fetch 실패: ${e}`);
  }

  // 2) 마지막 성공 캐시
  try {
    if (fm.fileExists(path)) {
      const cached = JSON.parse(fm.readString(path));
      if (isValidPayload(cached)) return { data: normalizePayload(cached), source: "cache" };
    }
  } catch (e) {
    console.warn(`[BOH] 캐시 읽기 실패: ${e}`);
  }

  // 3) 내장 Fallback
  return { data: normalizePayload(FALLBACK), source: "fallback" };
}

// ─────────────────────────── 상태 판정 / 집계 ───────────────────────────
function deriveStatus(s, nowMin) {
  if (s.status && STATUS[s.status]) return s.status;
  const tin = s.tag.in, tout = s.tag.out;
  if (tin && tout) return "off";
  if (!tin && tout) return "missing_in";
  if (tin && !tout) {
    const so = toMin(s.sched.out);
    if (so != null && nowMin > so + CONFIG.OUT_GRACE_MIN) return "missing_out";
    return "working";
  }
  const si = toMin(s.sched.in);
  if (si != null && nowMin < si + CONFIG.LATE_GRACE_MIN) return "scheduled";
  if (si == null && !s.sched.out) return "dayoff";
  return "missing_in";
}

function summarize(data, now) {
  const dataDate = parseYMD(data.date);
  // 데이터 날짜가 오늘이 아니면(지난 날짜) 하루가 끝난 것으로 간주해 판정
  const nowMin = !dataDate || isSameDay(dataDate, now) ? now.getHours() * 60 + now.getMinutes() : 24 * 60 + 1;

  const rows = data.staff
    .map((s) => ({ ...s, state: deriveStatus(s, nowMin) }))
    .filter((s) => s.state !== "dayoff");

  const checkedIn = rows.filter((s) => !!s.tag.in).length;
  const working = rows.filter((s) => s.state === "working").length;
  const issues = rows.filter((s) => STATUS[s.state].warn).length;

  let closing = data.closing;
  if (!closing) {
    const lastOut = Math.max(-1, ...rows.map((s) => toMin(s.sched.out) ?? -1));
    if (working > 0) closing = "진행중";
    else if (rows.length && rows.every((s) => s.state === "off" || s.state === "missing_in") && (lastOut < 0 || nowMin >= lastOut - 30)) closing = "완료";
    else closing = "대기";
  }

  // 정렬: KM 최상단 → 스케줄 출근 시간 → 이름
  const roleRank = { KM: 0, OP: 1, CL: 2 };
  rows.sort((a, b) => {
    const r = (roleRank[a.role] ?? 9) - (roleRank[b.role] ?? 9);
    if (r !== 0) return r;
    const t = (toMin(a.sched.in) ?? 9999) - (toMin(b.sched.in) ?? 9999);
    return t !== 0 ? t : a.name.localeCompare(b.name, "ko");
  });

  return { rows, checkedIn, working, issues, closing, total: rows.length, dataDate };
}

// ─────────────────────────── UI 프리미티브 ───────────────────────────
function dot(parent, size, color, opts = {}) {
  const s = parent.addStack();
  s.size = new Size(size, size);
  s.cornerRadius = size / 2;
  s.backgroundColor = color;
  if (opts.border) { s.borderWidth = 1; s.borderColor = opts.border; }
  return s;
}

function text(parent, str, font, color, opts = {}) {
  const t = parent.addText(String(str));
  t.font = font;
  t.textColor = color;
  t.lineLimit = opts.lines ?? 1;
  t.minimumScaleFactor = opts.scale ?? 0.75;
  if (opts.right) t.rightAlignText();
  if (opts.center) t.centerAlignText();
  return t;
}

function chip(parent, label, hex, T, opts = {}) {
  const size = opts.size ?? 9;
  const s = parent.addStack();
  s.layoutHorizontally();
  s.centerAlignContent();
  s.setPadding(2, 6, 2, 6);
  s.cornerRadius = opts.radius ?? 6;
  if (opts.solid) {
    s.backgroundColor = col(hex);
    text(s, label, Font.heavySystemFont(size), col(T.chipText));
  } else {
    s.backgroundColor = col(hex, T.name === "dark" ? 0.16 : 0.14);
    s.borderWidth = 1;
    s.borderColor = col(hex, T.name === "dark" ? 0.45 : 0.55);
    text(s, label, Font.boldSystemFont(size), col(hex));
  }
  return s;
}

function liveIndicator(parent, color) {
  const outer = parent.addStack();
  outer.size = new Size(12, 12);
  outer.cornerRadius = 6;
  outer.backgroundColor = col(color, 0.22);
  outer.layoutHorizontally();
  outer.centerAlignContent();
  outer.addSpacer();
  dot(outer, 6, col(color));
  outer.addSpacer();
  return outer;
}

function tile(parent, T, opts = {}) {
  const s = parent.addStack();
  s.backgroundColor = col(opts.bg ?? T.tile);
  s.cornerRadius = opts.radius ?? 12;
  s.borderWidth = 1;
  s.borderColor = col(opts.border ?? T.border, opts.borderAlpha ?? 1);
  const p = opts.pad ?? 8;
  s.setPadding(p, p + 2, p, p + 2);
  return s;
}

// ─────────────────────────── 섹션: 상단 크롬 ───────────────────────────
function renderChrome(parent, T, data, meta, now, family) {
  const h = parent.addStack();
  h.layoutHorizontally();
  h.centerAlignContent();

  // Mac 윈도우 도트
  const dots = h.addStack();
  dots.layoutHorizontally();
  dots.centerAlignContent();
  dots.spacing = 4;
  dot(dots, 8, col(ACCENT.macRed));
  dot(dots, 8, col(ACCENT.macYellow));
  dot(dots, 8, col(ACCENT.macGreen));
  h.addSpacer(8);

  text(h, data.store || "수원컨벤션 BOH", Font.boldSystemFont(family === "large" ? 13 : 12), col(T.text));
  h.addSpacer(6);
  liveIndicator(h, meta.source === "fallback" ? ACCENT.amber : ACCENT.live);
  h.addSpacer(4);
  const liveLabel = meta.source === "live" ? "LIVE" : meta.source === "cache" ? "CACHE" : "OFFLINE";
  text(h, liveLabel, Font.heavySystemFont(8), col(meta.source === "fallback" ? ACCENT.amber : ACCENT.live));

  h.addSpacer();

  // 우측: 날짜 · 갱신시각
  const d = meta.dataDate || now;
  const upd = data.updatedAt ? new Date(data.updatedAt) : now;
  const right = `${fmtDateKo(d)} · ${isNaN(upd) ? fmtHM(now) : fmtHM(upd)} 갱신`;
  text(h, right, Font.mediumSystemFont(9), col(T.sub), { right: true });
}

// ─────────────────────────── 섹션: 벤토 스탯 ───────────────────────────
function statTile(parent, T, label, value, unit, accent, opts = {}) {
  const t = tile(parent, T, { pad: opts.compact ? 5 : 7 });
  t.layoutVertically();
  text(t, label, Font.mediumSystemFont(opts.compact ? 8 : 9), col(T.sub));
  t.addSpacer(opts.compact ? 1 : 3);
  const v = t.addStack();
  v.layoutHorizontally();
  v.bottomAlignContent();
  text(v, value, Font.heavySystemFont(opts.compact ? 14 : 18), col(accent ?? T.text));
  if (unit) {
    v.addSpacer(2);
    const u = text(v, unit, Font.mediumSystemFont(opts.compact ? 8 : 9), col(T.sub));
    u.lineLimit = 1;
  }
  v.addSpacer();
  return t;
}

function renderStats(parent, T, meta, family) {
  const compact = family !== "large";
  const row = parent.addStack();
  row.layoutHorizontally();
  row.spacing = compact ? 5 : 7;

  const closingColor = meta.closing === "완료" ? STATUS.off.color : meta.closing === "진행중" ? STATUS.working.color : T.sub;
  const issueColor = meta.issues > 0 ? STATUS.missing_in.color : STATUS.working.color;

  statTile(row, T, "출근 인원", `${meta.checkedIn}`, `/ ${meta.total}명`, null, { compact });
  statTile(row, T, "마감 상태", meta.closing, null, closingColor, { compact });
  statTile(row, T, "특이사항", `${meta.issues}`, "건", issueColor, { compact });
}

// ─────────────────────────── 섹션: 근무자 타일 ───────────────────────────
function renderWorkerRow(parent, T, s, mode) {
  const isKM = s.role === "KM";
  const st = STATUS[s.state];
  const role = ROLE[s.role] || ROLE.DEFAULT;
  const two = mode === "two-line";

  const r = tile(parent, T, {
    bg: isKM ? T.tile2 : T.tile,
    border: isKM ? ACCENT.amber : T.border,
    borderAlpha: isKM ? 0.55 : 1,
    pad: two ? 4 : 3,
    radius: 10,
  });
  r.layoutHorizontally();
  r.centerAlignContent();

  // KM 앰버 액센트 바
  if (isKM) {
    const bar = r.addStack();
    bar.size = new Size(3, two ? 24 : 16);
    bar.cornerRadius = 1.5;
    bar.backgroundColor = col(ACCENT.amber);
    r.addSpacer(7);
  } else {
    r.addSpacer(2);
  }

  // 이름 + 직무 칩
  const left = r.addStack();
  left.layoutHorizontally();
  left.centerAlignContent();
  text(left, s.name, Font.boldSystemFont(two ? 12 : 11), col(isKM ? ACCENT.amber : T.text));
  left.addSpacer(5);
  chip(left, role.label, role.color, T, { size: 8, radius: 5, solid: isKM });
  left.size = new Size(two ? 84 : 78, 0);

  r.addSpacer(6);

  // 시간: 지문(실제) + 스케줄(예정)
  const tagIn = s.tag.in, tagOut = s.tag.out;
  const warnIn = !tagIn, warnOut = !tagOut && s.state !== "working" && s.state !== "scheduled";
  const schedStr = `${s.sched.in || "--:--"}~${s.sched.out || "--:--"}`;

  if (two) {
    const mid = r.addStack();
    mid.layoutVertically();
    const l1 = mid.addStack();
    l1.layoutHorizontally();
    l1.centerAlignContent();
    text(l1, "지문", Font.mediumSystemFont(7), col(T.muted));
    l1.addSpacer(4);
    text(l1, tagIn || "미태그", Font.boldMonospacedSystemFont(11), col(warnIn ? STATUS.missing_in.color : T.text));
    text(l1, " → ", Font.mediumMonospacedSystemFont(10), col(T.muted));
    const outLabel = tagOut || (s.state === "working" ? "근무중" : s.state === "scheduled" ? "예정" : "미태그");
    text(l1, outLabel, Font.boldMonospacedSystemFont(11), col(warnOut ? STATUS.missing_out.color : tagOut ? T.text : st.color));
    mid.addSpacer(1);
    const l2 = mid.addStack();
    l2.layoutHorizontally();
    l2.centerAlignContent();
    text(l2, "예정", Font.mediumSystemFont(7), col(T.muted));
    l2.addSpacer(4);
    text(l2, schedStr, Font.regularMonospacedSystemFont(8), col(T.sub));
  } else {
    const mid = r.addStack();
    mid.layoutHorizontally();
    mid.centerAlignContent();
    text(mid, tagIn || "미태그", Font.boldMonospacedSystemFont(10), col(warnIn ? STATUS.missing_in.color : T.text));
    text(mid, "→", Font.mediumMonospacedSystemFont(9), col(T.muted));
    const outLabel = tagOut || (s.state === "working" ? "근무중" : "미태그");
    text(mid, outLabel, Font.boldMonospacedSystemFont(10), col(warnOut ? STATUS.missing_out.color : tagOut ? T.text : st.color));
    mid.addSpacer(5);
    text(mid, `(${schedStr})`, Font.regularMonospacedSystemFont(7), col(T.muted));
  }

  r.addSpacer();

  // 상태 뱃지
  const badgeLabel = st.warn ? `⚠️ ${st.label}` : st.label;
  chip(r, badgeLabel, st.color, T, { size: two ? 8 : 7, radius: 6 });
}

function renderWorkers(parent, T, meta, family) {
  const rows = meta.rows;
  let mode, max;
  if (family === "large") {
    if (rows.length <= 7) { mode = "two-line"; max = 7; }
    else { mode = "compact"; max = 10; }
  } else {
    mode = "compact"; max = 3;
  }

  const list = parent.addStack();
  list.layoutVertically();
  list.spacing = family === "large" ? 3 : 2;

  const shown = rows.slice(0, max);
  for (const s of shown) renderWorkerRow(list, T, s, mode);

  const rest = rows.length - shown.length;
  if (rest > 0) {
    list.addSpacer(1);
    const names = rows.slice(max).map((s) => s.name).join(", ");
    text(list, `+${rest}명 · ${names}`, Font.mediumSystemFont(8), col(T.sub));
  }
}

// ─────────────────────────── 위젯 조립 ───────────────────────────
function buildWidget(data, meta, T, family, now) {
  const w = new ListWidget();
  const g = new LinearGradient();
  g.colors = [col(T.bg), col(T.bgEnd)];
  g.locations = [0, 1];
  g.startPoint = new Point(0, 0);
  g.endPoint = new Point(1, 1);
  w.backgroundGradient = g;
  w.setPadding(family === "large" ? 12 : 10, family === "large" ? 12 : 10, family === "large" ? 12 : 10, family === "large" ? 12 : 10);
  w.spacing = 0;
  if (CONFIG.TAP_URL) w.url = CONFIG.TAP_URL;
  w.refreshAfterDate = new Date(Date.now() + 1000 * 60 * CONFIG.REFRESH_MINUTES);

  renderChrome(w, T, data, meta, now, family);
  w.addSpacer(family === "large" ? 8 : 5);
  renderStats(w, T, meta, family);
  w.addSpacer(family === "large" ? 8 : 5);
  renderWorkers(w, T, meta, family);

  if (family === "large" && data.note) {
    w.addSpacer(4);
    const n = w.addStack();
    n.layoutHorizontally();
    n.centerAlignContent();
    dot(n, 5, col(meta.issues > 0 ? STATUS.missing_in.color : T.muted));
    n.addSpacer(5);
    text(n, data.note, Font.mediumSystemFont(8), col(T.sub));
  }
  w.addSpacer();
  return w;
}

// ─────────────────────────────── 실행 ───────────────────────────────
async function main() {
  const param = parseWidgetParam(args.widgetParameter);
  const T = THEMES[param.theme || CONFIG.THEME] || THEMES.dark;
  const url = param.url || CONFIG.DATA_URL;
  const now = new Date();

  const { data, source } = await fetchAttendance(url);
  const meta = { ...summarize(data, now), source };

  const family = config.runsInWidget
    ? (config.widgetFamily === "medium" ? "medium" : "large")
    : (param.family || CONFIG.PREVIEW_FAMILY);

  const widget = buildWidget(data, meta, T, family, now);

  if (config.runsInWidget) {
    Script.setWidget(widget);
  } else if (family === "medium") {
    await widget.presentMedium();
  } else {
    await widget.presentLarge();
  }
  Script.complete();
}

await main();
