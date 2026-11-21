"""Data sources (made-up sample data; real store data never goes in the repo) and the labor check."""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import labor  # noqa: E402
import pickle_relay as pr  # noqa: E402
import router  # noqa: E402
import sources  # noqa: E402

TODAY = date(2026, 11, 13)
KV = {
    "hide": ["숨긴품목"],
    "input.2026-11-12": {"양파": {"s": "5", "t": "2026-11-12 13:00"}, "치즈": {"s": "1", "t": "2026-11-12 13:00"}},
    "input.2026-11-13": {"양파": {"s": "3.5", "o": "", "t": "2026-11-13 13:55"}, "숨긴품목": {"s": "9"},
                         "감자튀김": {"s": ""}},
    "input.2026-11-14": {"양파": {"s": "99", "t": "2026-11-14 09:00"}},  # future day: ignored
    "misRecv.2026-11-13": {"at": 0, "rows": [{"code": "1", "name": "양파", "qty": 2, "unit": "PK"}]},
    "nowSales": {"day": "2026-11-13", "gross": 3250000},
    "forecast": {"2026-11-13": {"fc": "4000000", "act": ""}},
    "hrStatus": {"date": "2026-11-13", "at": 1794549900000, "rows": [
        {"grp": "BOH", "name": "김민수", "in": "08:55", "out": ""},
        {"grp": "BOH", "name": "이지은", "in": "08:50", "out": "14:02"}]},
    "events": {"days": {"2026-11-12": {"names": ["푸드&#038;쇼"]}, "2026-11-13": {"names": ["푸드&#038;쇼"]},
                        "2026-11-15": {"names": ["푸드&#038;쇼"]}}},
}
BOARD = (date(2026, 11, 9), {
    "employees": [{"id": "a", "name": "김민수", "dept": "BOH", "active": True},
                  {"id": "b", "name": "박매니저", "dept": "FOH", "active": True, "excludeChecks": True},
                  {"id": "c", "name": "퇴사자", "dept": "FOH", "active": False}],
    "week": {"start": "2026-11-09", "cells": {
        "a": [{"in": "09:00", "out": "18:00", "brk": "01:00"}, {"status": "D/O"}, {"status": "주휴일"},
              {}, {"in": "17:00", "out": "01:00", "brk": "00:30"}, {}, {}],
        "b": [{"in": "10:00", "out": "22:00"}] + [{}] * 6,
        "c": [{"in": "10:00", "out": "22:00"}] + [{}] * 6}}})


class OrderApp(unittest.TestCase):
    def test_kv_to_cache_files(self):
        out = sources.order_app_files(KV, TODAY)
        inv = {i["name"]: i for i in out["inventory"]["items"]}
        self.assertEqual(set(inv), {"양파", "치즈"})
        self.assertEqual((inv["양파"]["on_hand"], inv["양파"]["snapshot_at"]), (3.5, "2026-11-13T13:55:00"))
        self.assertEqual(out["inbound"], {"deliveries": [{"date": "2026-11-13", "name": "양파", "qty": 2, "unit": "PK"}]})
        self.assertEqual(out["sales"], {"date": "2026-11-13", "gross_sales": 3250000, "forecast_manwon": 400})
        self.assertEqual((out["boh"]["on_duty"], out["boh"]["off_duty"]), (1, 1))
        self.assertEqual(out["promotions"]["promotions"], [
            {"name": "푸드&쇼", "start": "2026-11-12", "end": "2026-11-13", "detail": "컨벤션센터"},
            {"name": "푸드&쇼", "start": "2026-11-15", "end": "2026-11-15", "detail": "컨벤션센터"}])
        self.assertTrue(pr.BOH_RE.match(pr.fmt_boh(out["boh"])))
        self.assertTrue(pr.SALES_RE.match(pr.fmt_sales(out["sales"])))

    def test_yesterdays_hr_status_is_not_today(self):
        self.assertNotIn("boh", sources.order_app_files(KV, date(2026, 11, 14)))

    def test_hub_answers_from_synced_files(self):
        with tempfile.TemporaryDirectory() as d:
            written, problems = sources.sync(d, datetime(2026, 11, 13, 14, 0), {"ORDER_APP_API": "u", "HR_BOARD_PASSWORD": "p"},
                                             order_fetch=lambda url: KV, hr_fetch=lambda pw, day: [BOARD])
            self.assertEqual(problems, [])
            self.assertIn("live_roster.json", written)
            q = router.ActionQueue(Path(d) / "a.jsonl")
            self.assertEqual(router.route("양파 재고", d, q, datetime(2026, 11, 13, 14, 0)).text, "양파: 예상 3.5개")
            again, _ = sources.sync(d, datetime(2026, 11, 13, 14, 0), {"ORDER_APP_API": "u"}, order_fetch=lambda url: KV)
            self.assertEqual(again, [])  # unchanged files are not rewritten

    def test_a_failing_source_is_reported_without_secrets(self):
        def boom(*a):
            raise OSError("secret-password in message")
        with tempfile.TemporaryDirectory() as d:
            _, problems = sources.sync(d, datetime(2026, 11, 13), {"ORDER_APP_API": "u", "HR_BOARD_PASSWORD": "pw"},
                                       order_fetch=boom, hr_fetch=boom)
        self.assertEqual(problems, ["발주앱 연결 실패: OSError", "HR 보드 연결 실패: OSError"])


class HrBoard(unittest.TestCase):
    def test_roster_from_board_cells(self):
        shifts = sources.roster_file([BOARD])["shifts"]
        self.assertEqual([(s["date"], s["name"], s["hours"]) for s in shifts],
                         [("2026-11-09", "김민수", 8.0), ("2026-11-09", "박매니저", 12.0), ("2026-11-13", "김민수", 7.5)])
        self.assertTrue(shifts[1]["exclude"])


class Labor(unittest.TestCase):
    def roster(self, hours_per_day, days=6, name="김민수"):
        return {"shifts": [{"date": f"2026-11-{9 + i:02d}", "shift": "BOH", "name": name, "start": "09:00",
                            "end": "18:00", "hours": hours_per_day} for i in range(days)]}

    def test_52h_levels(self):
        now = datetime(2026, 11, 13, 8, 0)
        self.assertEqual(labor.check(self.roster(8.0), None, now)[0], ["52h 임박: 김민수 이번 주 48시간 (스케줄 기준)"])
        self.assertEqual(labor.check(self.roster(9.0), None, now)[0], ["52h 초과: 김민수 이번 주 54시간 (스케줄 기준)"])
        self.assertEqual(labor.check(self.roster(7.0), None, now)[0], [])
        excluded = {"shifts": [dict(s, exclude=True) for s in self.roster(9.0)["shifts"]]}
        self.assertEqual(labor.check(excluded, None, now)[0], [])

    def test_month_close_reminders(self):
        self.assertIn("월 근태 마감: 내일(12/1) 12:00까지", labor.check(None, None, datetime(2026, 11, 30, 9))[0])
        self.assertIn("월 근태 마감: 오늘 12:00까지", labor.check(None, None, datetime(2026, 12, 1, 9))[0])
        self.assertEqual(labor.check(None, None, datetime(2026, 12, 1, 12, 1))[0], [])

    def test_unscheduled_punch_only_when_the_board_has_the_day(self):
        boh = {"date": "2026-11-13", "rows": [{"name": "김민수", "in": "08:55"}, {"name": "최다인", "in": "09:10"},
                                              {"name": "이지은", "in": "09:00"}]}
        roster = {"shifts": [{"date": "2026-11-13", "shift": "BOH", "name": n, "start": "09:00", "end": "15:00",
                              "hours": 5.5} for n in ("김민수", "이지은")]}
        lines, _ = labor.check(roster, boh, datetime(2026, 11, 13, 10))
        self.assertEqual(lines, ["스케줄 없이 출근: 최다인 09:10 (오늘 안에 스케줄 변경 신청)"])
        lines, _ = labor.check({"shifts": roster["shifts"][:1]}, boh, datetime(2026, 11, 13, 10))
        self.assertEqual(lines, ["스케줄 없이 출근: 점검 안 함 (HR 보드에 오늘 스케줄 1/3명뿐)"])

    def test_punches_are_judged_at_the_snapshot_time(self):
        roster = {"shifts": [{"date": "2026-11-13", "shift": "BOH", "name": "김민수", "start": "09:00", "end": "15:00",
                              "hours": 5.5}]}
        boh = {"date": "2026-11-13", "as_of": "14:00", "rows": [{"name": "김민수", "in": "08:55", "out": ""}]}
        self.assertEqual(labor.check(roster, boh, datetime(2026, 11, 13, 18))[0], [])
        boh["as_of"] = "15:40"
        self.assertEqual(labor.check(roster, boh, datetime(2026, 11, 13, 18))[0], ["퇴근 미태그: 김민수 15:00 퇴근 예정"])

    def test_alerted_keys_survive_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "k.json"
            self.assertEqual(labor.Alerted(path).new([("a", "A"), ("b", "B")]), ["A", "B"])
            self.assertEqual(labor.Alerted(path).new([("a", "A"), ("c", "C")]), ["C"])


if __name__ == "__main__":
    unittest.main()
