"""Daily labor check (노무 점검) from the cache, the same criteria as the monthly 노무점검:

  52h          scheduled hours this Monday–Sunday week (HR 보드), 48h+ warns, over 52h is a violation
  출근 미태그   on today's schedule, no punch-in in HR 15 min after the start (BOH, hrStatus)
  퇴근 미태그   punched in, no punch-out 30 min after the scheduled end
  스케줄 없이   punched in with no shift today: file a schedule change request the same day (사후신청 감점)
  월 근태 마감  the month closes on the 1st at 12:00: reminders on the last day and on the 1st

People with excludeChecks on the HR board (managers, helpers) are skipped for 52h. Stdlib only.
Writes nothing itself: check() returns lines; the hub writes 노무.txt and raises each new alert once.
"""
import calendar
import json
from datetime import date, datetime, timedelta
from pathlib import Path

WEEK_LIMIT, WEEK_WARN = 52.0, 48.0
IN_GRACE, OUT_GRACE = 15, 30  # minutes


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=h, minutes=m)


def week_hours(roster, today):
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=7)
    hours = {}
    for s in roster.get("shifts", []):
        d = date.fromisoformat(s["date"])
        if start <= d < end and not s.get("exclude") and s.get("hours") is not None:
            hours[s["name"]] = hours.get(s["name"], 0.0) + float(s["hours"])
    return hours


def check(roster, boh, now):
    """(lines, alerts): lines for 노무.txt; alerts are (key, message) pairs, raised once per key."""
    today, lines, alerts = now.date(), [], []
    if roster:
        for name, h in sorted(week_hours(roster, today).items(), key=lambda x: -x[1]):
            if h > WEEK_LIMIT:
                msg = f"52h 초과: {name} 이번 주 {h:g}시간 (스케줄 기준)"
            elif h >= WEEK_WARN:
                msg = f"52h 임박: {name} 이번 주 {h:g}시간 (스케줄 기준)"
            else:
                continue
            lines.append(msg)
            alerts.append((f"52h:{today - timedelta(days=today.weekday())}:{name}:{'over' if h > WEEK_LIMIT else 'warn'}", msg))

    if roster and boh and boh.get("date") == today.isoformat() and boh.get("rows") is not None:
        punched = {r["name"]: r for r in boh["rows"]}
        boh_names = set(punched)
        todays = [s for s in roster.get("shifts", []) if s["date"] == today.isoformat()]
        scheduled = {s["name"] for s in todays}
        # Judge punches as of the HR snapshot, not now: a late snapshot must not read as a missing punch.
        seen = min(now, _at(today, boh["as_of"])) if boh.get("as_of") else now
        for s in todays:
            if s.get("shift") != "BOH" and s["name"] not in boh_names:
                continue  # hrStatus covers BOH only; FOH has no punch data here
            r = punched.get(s["name"], {})
            if not r.get("in") and seen >= _at(today, s["start"]) + timedelta(minutes=IN_GRACE):
                msg = f"출근 미태그: {s['name']} {s['start']} 출근 예정"
                lines.append(msg)
                alerts.append((f"in:{today}:{s['name']}", msg))
            end = _at(today, s["end"]) + (timedelta(days=1) if s["end"] <= s["start"] else timedelta())
            if r.get("in") and not r.get("out") and seen >= end + timedelta(minutes=OUT_GRACE):
                msg = f"퇴근 미태그: {s['name']} {s['end']} 퇴근 예정"
                lines.append(msg)
                alerts.append((f"out:{today}:{s['name']}", msg))
        came = [n for n, r in punched.items() if r.get("in")]
        if came and sum(n in scheduled for n in came) < len(came) / 2:
            # The board does not hold today's schedule (not entered yet): checking it would flag everyone.
            lines.append(f"스케줄 없이 출근: 점검 안 함 (HR 보드에 오늘 스케줄 {sum(n in scheduled for n in came)}/{len(came)}명뿐)")
            came = []
        for name in sorted(came):
            r = punched[name]
            if name not in scheduled:
                msg = f"스케줄 없이 출근: {name} {r['in']} (오늘 안에 스케줄 변경 신청)"
                lines.append(msg)
                alerts.append((f"nosched:{today}:{name}", msg))

    last = calendar.monthrange(today.year, today.month)[1]
    if today.day == last:
        msg = f"월 근태 마감: 내일({today.month % 12 + 1}/1) 12:00까지"
        lines.append(msg)
        alerts.append((f"close:{today}", msg))
    elif today.day == 1 and now.hour < 12:
        msg = "월 근태 마감: 오늘 12:00까지"
        lines.append(msg)
        alerts.append((f"close:{today}", msg))
    return lines, alerts


def report(cache_dir, now):
    """노무.txt text and the alerts, from the cached roster and BOH status."""
    cache = Path(cache_dir)
    roster, boh = _load(cache / "live_roster.json"), _load(cache / "live_boh_status.json")
    lines, alerts = check(roster, boh, now)
    head = f"노무 점검 {now:%m/%d %H:%M} (HR 보드·HR 출퇴근 기준)"
    return "\n".join([head] + (lines or ["이상 없음"])) + "\n", alerts


class Alerted:
    """Keys already raised, kept in <state>/labor_alerted.json so a restart does not repeat them."""

    def __init__(self, path):
        self.path = Path(path)
        self.keys = set(_load(self.path) or [])

    def new(self, alerts):
        fresh = [(k, m) for k, m in alerts if k not in self.keys]
        if fresh:
            self.keys |= {k for k, _ in fresh}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(sorted(self.keys)[-500:], ensure_ascii=False), encoding="utf-8")
        return [m for _, m in fresh]
