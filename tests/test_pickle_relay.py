import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import pickle_relay as pr  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 13, 11, 0)  # 2 hours after the inventory snapshot


class Formats(unittest.TestCase):
    def test_inventory_backs_out_reservations_and_burn(self):
        items = {i["name"]: i for i in pr.load(FIX, "inventory")["items"]}
        msg = pr.fmt_inventory(items["양파"], NOW)  # 20 - 4 - 1.5*2 = 13.0
        self.assertEqual(msg, "양파: 예상 13.0개")
        self.assertEqual(pr.lint(msg, "inventory"), [])

    def test_inventory_never_negative(self):
        items = {i["name"]: i for i in pr.load(FIX, "inventory")["items"]}
        self.assertEqual(pr.fmt_inventory(items["치즈"], NOW), "치즈: 예상 0.0개")

    def test_sales(self):
        msg = pr.fmt_sales(pr.load(FIX, "sales"))
        self.assertEqual(msg, "2026-11-13 매장 당일 그로스 세일즈: 3,250,000원 "
                              "(목표 포캐스트 400만 원 대비 81.3% 달성)")
        self.assertEqual(pr.lint(msg, "sales"), [])

    def test_boh(self):
        msg = pr.fmt_boh(pr.load(FIX, "boh"))
        self.assertEqual(msg, "[BOH 리포트 (14:05)]\n"
                              "- 신규 출근/퇴근: OP 김민수 (퇴근 14:00), CL 이지은 (출근 14:00)\n"
                              "- 근무 중: 5명\n"
                              "- 퇴근 완료: 2명\n"
                              "- 특이사항: 없음")
        self.assertEqual(pr.lint(msg, "boh"), [])

    def test_question(self):
        msg = pr.fmt_question("오늘 양파 발주량?", NOW)
        self.assertTrue(msg.startswith("## 질문: [2026-11-13 11:00] 오늘 양파 발주량?\n"))
        self.assertEqual(pr.lint(msg, "question"), [])


class Lint(unittest.TestCase):
    def test_rejects_banned_words_and_timestamps(self):
        self.assertIn("banned word: 관제", pr.lint("관제 양파: 예상 3.0개", "inventory"))
        self.assertIn("banned word: 전산기준", pr.lint("양파: 예상 3.0개 전산기준", "inventory"))
        self.assertIn("inventory answer contains a timestamp", pr.lint("양파(14:00): 예상 3.0개", "inventory"))

    def test_strip_filler(self):
        raw = "안녕하세요!\n결론: 양파: 예상 13.0개\n근거: 예약 4개 반영\n감사합니다"
        self.assertEqual(pr.strip_filler(raw), "양파: 예상 13.0개\n예약 4개 반영")


class Cache(unittest.TestCase):
    def test_fixture_dir_passes_check(self):
        self.assertTrue(pr.check_cache(FIX))


if __name__ == "__main__":
    unittest.main()
