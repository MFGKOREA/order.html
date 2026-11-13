import contextlib
import io
import shutil
import sys
import tempfile
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


class Feed(unittest.TestCase):
    def test_feed_holds_every_answer_and_passes_lint(self):
        sections, broken, problems = pr.feed_sections(FIX, NOW)
        self.assertEqual((broken, problems), (set(), []))
        self.assertEqual(pr.join_feed(sections),
                         "양파: 예상 13.0개\n"
                         "치즈: 예상 0.0개\n"
                         "\n"
                         "2026-11-13 매장 당일 그로스 세일즈: 3,250,000원 (목표 포캐스트 400만 원 대비 81.3% 달성)\n"
                         "\n"
                         "[BOH 리포트 (14:05)]\n"
                         "- 신규 출근/퇴근: OP 김민수 (퇴근 14:00), CL 이지은 (출근 14:00)\n"
                         "- 근무 중: 5명\n"
                         "- 퇴근 완료: 2명\n"
                         "- 특이사항: 없음\n")

    def test_write_only_when_changed_and_leave_no_temp_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "drive" / "pickle_feed.txt"
            self.assertTrue(pr.write_if_changed(out, "a\n"))
            self.assertFalse(pr.write_if_changed(out, "a\n"))
            self.assertTrue(pr.write_if_changed(out, "b\n"))
            self.assertEqual(out.read_text(encoding="utf-8"), "b\n")
            self.assertEqual(sorted(p.name for p in out.parent.iterdir()), ["pickle_feed.txt"])

    def test_feed_with_no_readable_cache_leaves_the_file_alone(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "pickle_feed.txt"
            out.write_text("good answers\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(pr.main(["--dir", str(Path(d) / "empty"), "feed", "--out", str(out)]), 1)
            self.assertEqual(out.read_text(encoding="utf-8"), "good answers\n")

    def test_watch_keeps_last_good_section_until_the_file_is_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "cache"
            shutil.copytree(FIX, cache)
            out = Path(d) / "pickle_feed.txt"
            boh = cache / pr.CACHE_FILES["boh"]
            snapshots = []
            steps = iter([lambda: boh.write_text("{", encoding="utf-8"),  # caught mid-write
                          lambda: boh.unlink(),  # removed on purpose
                          None])

            def stop():
                snapshots.append(out.read_text(encoding="utf-8"))
                step = next(steps)
                if step is None:
                    return True
                step()
                return False

            pr.watch_feed(cache, out, interval=0, stop=stop, log=io.StringIO())
            self.assertIn("[BOH 리포트 (14:05)]", snapshots[0])
            self.assertEqual(snapshots[1], snapshots[0])
            self.assertNotIn("BOH", snapshots[2])
            self.assertIn("매장 당일 그로스 세일즈", snapshots[2])


if __name__ == "__main__":
    unittest.main()
