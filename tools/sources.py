"""Data sources: turn the live apps into the hub's cache files, so data questions need no AI.

  발주앱 (label-list, sheet kv): ORDER_APP_API = the app's Apps Script URL (DEFAULT_API in
      label-list order-src/app.js). Read-only GET ?api=1. Gives
      재고 live_inventory_cache.json   latest count per item from input.<date> (s)
      입고 live_inbound.json           misRecv.<date> rows (what arrived)
      매출 live_sales.json             nowSales + forecast.<day>.fc
      BOH  live_boh_status.json        hrStatus (today's BOH punches from HR, the BOH 출퇴근 widget's feed)
      행사 store_promotions.json       events (convention-center events by day)
  HR 보드 (hr-board-teal.vercel.app): HR_BOARD_PASSWORD. Read-only GET /api/data?week=<Monday>
      근무표 live_roster.json          this week and next, BOH and FOH, with break minutes

Secrets come from the environment only and are never written to a file or a log line.
Stdlib only. `python3 tools/sources.py --cache downloads` syncs once and prints what changed.
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pickle_relay as pr  # noqa: E402

HR_BOARD = os.environ.get("HR_BOARD_URL", "https://hr-board-teal.vercel.app")
OFF = {"휴무", "D/O", "주휴일", "연차", "무급휴무", "공휴일"}
DAY_KEY = re.compile(r"^(input|misRecv)\.(\d{4}-\d{2}-\d{2})$")


def _get_json(url, headers=None, data=None, method="GET", timeout=30):
    req = Request(url, data=data, headers={"Accept": "application/json", **(headers or {})}, method=method)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")), resp.headers


def _ms(at):
    return datetime.fromtimestamp(at / 1000) if isinstance(at, (int, float)) else None


# ---------- 발주앱 kv ----------

def fetch_order_app(api_url):
    body, _ = _get_json(f"{api_url}{'&' if '?' in api_url else '?'}api=1")
    if not body.get("ok", True):
        raise RuntimeError("발주앱 API ok=false")
    return body.get("data", body)


def order_app_files(kv, today):
    """kv dict -> {cache file key: json}. Only what the kv has; missing parts are left out."""
    out = {}
    days = {}
    for k in kv:
        m = DAY_KEY.match(k)
        if m:
            days.setdefault(m[1], []).append(m[2])
    hide = set(kv.get("hide") or [])

    inputs = sorted(d for d in days.get("input", []) if d <= today.isoformat())[-3:]
    latest = {}
    for d in inputs:  # later days win
        for name, v in (kv.get(f"input.{d}") or {}).items():
            s = v.get("s") if isinstance(v, dict) else None
            if name in hide or s in (None, ""):
                continue
            try:
                t = v.get("t")
                latest[name] = {"name": name, "on_hand": float(s), "reserved": 0, "burn_per_hour": 0,
                                "snapshot_at": t.replace(" ", "T")[:16] + ":00" if t else f"{d}T00:00:00"}
            except (TypeError, ValueError):
                pass
    if latest:
        out["inventory"] = {"items": sorted(latest.values(), key=lambda i: i["name"])}

    deliveries = []
    for d in sorted(days.get("misRecv", []))[-14:]:
        for r in (kv.get(f"misRecv.{d}") or {}).get("rows", []):
            if r.get("name") and r.get("qty") is not None:
                deliveries.append({"date": d, "name": r["name"], "qty": r["qty"], "unit": r.get("unit") or "개"})
    if deliveries:
        out["inbound"] = {"deliveries": deliveries}

    sales, fc = kv.get("nowSales") or {}, kv.get("forecast") or {}
    day = sales.get("day")
    target = (fc.get(day) or {}).get("fc") if day else None
    if day and sales.get("gross") is not None and target:
        out["sales"] = {"date": day, "gross_sales": int(sales["gross"]), "forecast_manwon": round(int(target) / 10_000)}

    hr = kv.get("hrStatus") or {}
    if hr.get("date") == today.isoformat() and hr.get("rows") is not None:
        out["boh"] = boh_status(hr)

    ev = (kv.get("events") or {}).get("days") or {}
    if ev:
        out["promotions"] = {"promotions": event_runs(ev)}
    return out


def boh_status(hr):
    """hrStatus -> live_boh_status.json: the latest punches, on duty and off duty counts, and the raw
    rows (kept for the labor check)."""
    at = _ms(hr.get("at"))
    events = []
    for r in hr["rows"]:
        if r.get("in"):
            events.append({"shift": r.get("grp", ""), "name": r["name"], "type": "출근", "time": r["in"]})
        if r.get("out"):
            events.append({"shift": r.get("grp", ""), "name": r["name"], "type": "퇴근", "time": r["out"]})
    events.sort(key=lambda e: e["time"])
    on = sum(1 for r in hr["rows"] if r.get("in") and not r.get("out"))
    off = sum(1 for r in hr["rows"] if r.get("out"))
    return {"as_of": f"{at:%H:%M}" if at else "", "date": hr["date"], "events": events[-4:],
            "on_duty": on, "off_duty": off, "notes": "", "rows": [
                {"name": r["name"], "grp": r.get("grp", ""), "in": r.get("in", ""), "out": r.get("out", "")}
                for r in hr["rows"]]}


def event_runs(days):
    """{day: {names: [...]}} -> promotions: one entry per event name and run of consecutive days."""
    runs = []
    open_runs = {}
    for d in sorted(days):
        for name in days[d].get("names") or []:
            name = re.sub(r"&#0*38;", "&", name)
            cur = open_runs.get(name)
            if cur and date.fromisoformat(cur["end"]) + timedelta(days=1) == date.fromisoformat(d):
                cur["end"] = d
            else:
                cur = {"name": name, "start": d, "end": d, "detail": "컨벤션센터"}
                open_runs[name] = cur
                runs.append(cur)
    return runs


# ---------- HR 보드 ----------

def monday(d):
    return d - timedelta(days=d.weekday())


def hr_board_login(password, base=HR_BOARD):
    _, headers = _get_json(f"{base}/api/login", {"Content-Type": "application/json"},
                           json.dumps({"password": password}).encode(), "POST")
    m = re.search(r"hr_session=([^;]+)", headers.get("Set-Cookie") or "")
    if not m:
        raise RuntimeError("HR 보드 로그인 실패")
    return m[1]


def fetch_hr_board(password, today, base=HR_BOARD):
    session = hr_board_login(password, base)
    weeks = []
    for start in (monday(today), monday(today) + timedelta(days=7)):
        data, _ = _get_json(f"{base}/api/data?{urlencode({'week': start.isoformat()})}",
                            {"Cookie": f"hr_session={session}"})
        weeks.append((start, data))
    return weeks


def _minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def roster_file(weeks):
    """[(monday, /api/data body)] -> live_roster.json shifts (work days only), with hours."""
    shifts = []
    for start, data in weeks:
        people = {e["id"]: e for e in data.get("employees") or [] if e.get("active", True)}
        cells = ((data.get("week") or {}).get("cells")) or {}
        for emp_id, row in cells.items():
            e = people.get(emp_id)
            if not e:
                continue
            for i, c in enumerate(row or []):
                if not isinstance(c, dict) or c.get("status") in OFF or not (c.get("in") and c.get("out")):
                    continue
                span = (_minutes(c["out"]) - _minutes(c["in"])) % (24 * 60)
                brk = _minutes(c["brk"]) if c.get("brk") else 0
                shifts.append({"date": (start + timedelta(days=i)).isoformat(), "shift": e.get("dept", ""),
                               "name": e["name"], "start": c["in"], "end": c["out"],
                               "hours": round((span - brk) / 60, 2),
                               "exclude": bool(e.get("excludeChecks"))})
    return {"shifts": sorted(shifts, key=lambda s: (s["date"], s["start"], s["name"]))}


# ---------- sync ----------

def write_cache(cache_dir, files):
    """Write each cache file when it changed. Returns the names written."""
    written = []
    for key, data in files.items():
        path = Path(cache_dir) / pr.CACHE_FILES[key]
        if pr.write_if_changed(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n"):
            written.append(path.name)
    return written


def sync(cache_dir, now=None, env=None, order_fetch=fetch_order_app, hr_fetch=fetch_hr_board):
    """One pass over the configured sources. Returns (written file names, problems). A source with
    no setting is skipped; a failing source is reported and the others still sync."""
    env, now = env if env is not None else os.environ, now or datetime.now()
    written, problems = [], []
    if env.get("ORDER_APP_API"):
        try:
            written += write_cache(cache_dir, order_app_files(order_fetch(env["ORDER_APP_API"]), now.date()))
        except Exception as e:  # noqa: BLE001 — network, JSON, or format; the hub keeps running
            problems.append(f"발주앱 연결 실패: {type(e).__name__}")
    if env.get("HR_BOARD_PASSWORD"):
        try:
            written += write_cache(cache_dir, {"roster": roster_file(hr_fetch(env["HR_BOARD_PASSWORD"], now.date()))})
        except Exception as e:  # noqa: BLE001
            problems.append(f"HR 보드 연결 실패: {type(e).__name__}")
    return written, problems


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="downloads", help="cache directory (default: downloads)")
    args = p.parse_args(argv)
    if not (os.environ.get("ORDER_APP_API") or os.environ.get("HR_BOARD_PASSWORD")):
        print("ORDER_APP_API, HR_BOARD_PASSWORD 둘 다 없음: 동기화할 곳 없음", file=sys.stderr)
        return 1
    written, problems = sync(args.cache)
    for line in problems:
        print(line, file=sys.stderr)
    print("갱신: " + (", ".join(written) or "변경 없음"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
