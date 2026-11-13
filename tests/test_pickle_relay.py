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
    def test_topic_files_hold_every_answer_and_pass_lint(self):
        sections, broken, problems = pr.feed_sections(FIX, NOW)
        self.assertEqual((broken, problems), (set(), []))
        self.assertEqual(pr.topic_texts(sections), {
            "재고.txt": "양파: 예상 13.0개\n치즈: 예상 0.0개\n감자튀김: 예상 20.0개\n브로콜리: 예상 4.0개\n",
            # one small file per first consonant, so a single-item question reads one slice
            "재고_ㅇ.txt": "양파: 예상 13.0개\n",
            "재고_ㅊ.txt": "치즈: 예상 0.0개\n",
            "재고_ㄱ.txt": "감자튀김: 예상 20.0개\n",
            "재고_ㅂ.txt": "브로콜리: 예상 4.0개\n",
            "매출.txt": "2026-11-13 매장 당일 그로스 세일즈: 3,250,000원 (목표 포캐스트 400만 원 대비 81.3% 달성)\n",
            # past delivery dropped, same-day deliveries of one item added up (4 + 2)
            "입고.txt": "감자튀김: 내일(11/14) 입고 10개\n피자치즈: 내일(11/14) 입고 6개\n양파: 모레(11/15) 입고 2.5kg\n",
            "입고_오늘.txt": "없음\n",
            "입고_내일.txt": "감자튀김: 내일(11/14) 입고 10개\n피자치즈: 내일(11/14) 입고 6개\n",
            "입고_모레.txt": "양파: 모레(11/15) 입고 2.5kg\n",
            "BOH.txt": "[BOH 리포트 (14:05)]\n"
                       "- 신규 출근/퇴근: OP 김민수 (퇴근 14:00), CL 이지은 (출근 14:00)\n"
                       "- 근무 중: 5명\n"
                       "- 퇴근 완료: 2명\n"
                       "- 특이사항: 없음\n",
            "근무표.txt": "오늘(11/13) 출근: OP 김민수 09:00~15:00, CL 이지은 15:00~22:00\n"
                       "내일(11/14) 출근: OP 최다인 09:00~15:00\n"
                       "모레(11/15) 출근: 없음\n",
            # this week (11/9~11/15): the Black Friday promotion is later
            "행사.txt": "행사: 런치 세트 20% 할인 (11/10~11/16, 평일 11~14시)\n행사: 수능 응원 음료 1+1 (11/13~11/13)\n",
        })

    def test_first_consonant(self):
        self.assertEqual([pr.initial(n) for n in ("감자튀김", "꽃게", "BBQ소스", "3분카레")], ["ㄱ", "ㄲ", "B", "기타"])

    def test_a_slice_whose_items_are_gone_reads_none(self):
        with tempfile.TemporaryDirectory() as d:
            cache, out = Path(d) / "cache", Path(d) / "drive"
            shutil.copytree(FIX, cache)
            feed = pr.Feed(cache, out)
            feed.step(NOW)
            self.assertEqual((out / "재고_ㅇ.txt").read_text(encoding="utf-8"), "양파: 예상 13.0개\n")
            inv = cache / pr.CACHE_FILES["inventory"]
            inv.write_text(inv.read_text(encoding="utf-8").replace('"양파"', '"대파"'), encoding="utf-8")
            feed.step(NOW)
            self.assertEqual((out / "재고_ㅇ.txt").read_text(encoding="utf-8"), "없음\n")
            self.assertEqual((out / "재고_ㄷ.txt").read_text(encoding="utf-8"), "대파: 예상 13.0개\n")

    def test_inbound_label(self):
        today = NOW.date()
        self.assertEqual(pr.fmt_inbound("피자치즈", today, 6, "개", today), "피자치즈: 오늘(11/13) 입고 6개")
        self.assertEqual(pr.fmt_inbound("피자치즈", today.replace(day=20), None, "개", today), "피자치즈: 11/20 입고 없음")

    def test_write_only_when_changed_and_leave_no_temp_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "drive" / "재고.txt"
            self.assertTrue(pr.write_if_changed(out, "a\n"))
            self.assertFalse(pr.write_if_changed(out, "a\n"))
            self.assertTrue(pr.write_if_changed(out, "b\n"))
            self.assertEqual(out.read_text(encoding="utf-8"), "b\n")
            self.assertEqual(sorted(p.name for p in out.parent.iterdir()), ["재고.txt"])

    def test_feed_with_no_readable_cache_leaves_the_files_alone(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "재고.txt"
            out.write_text("good answers\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(pr.main(["--dir", str(Path(d) / "empty"), "feed", "--out-dir", d]), 1)
            self.assertEqual(out.read_text(encoding="utf-8"), "good answers\n")
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["재고.txt"])

    def test_watch_keeps_last_good_answers_until_the_file_is_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            cache, out = Path(d) / "cache", Path(d) / "drive"
            shutil.copytree(FIX, cache)
            boh = cache / pr.CACHE_FILES["boh"]
            snapshots = []
            steps = iter([lambda: boh.write_text("{", encoding="utf-8"),  # caught mid-write
                          lambda: boh.unlink(),  # removed on purpose
                          None])

            def stop():
                snapshots.append({p.name: p.read_text(encoding="utf-8") for p in out.iterdir()})
                step = next(steps)
                if step is None:
                    return True
                step()
                return False

            pr.watch_feed(cache, out, interval=0, stop=stop, log=io.StringIO())
            self.assertEqual(sorted(snapshots[0]), [
                "BOH.txt", "근무표.txt", "매출.txt", "입고.txt", "입고_내일.txt", "입고_모레.txt", "입고_오늘.txt",
                "재고.txt", "재고_ㄱ.txt", "재고_ㅂ.txt", "재고_ㅇ.txt", "재고_ㅊ.txt", "행사.txt"])
            self.assertIn("[BOH 리포트 (14:05)]", snapshots[0]["BOH.txt"])
            self.assertEqual(snapshots[1], snapshots[0])
            self.assertEqual(snapshots[2]["BOH.txt"], "없음\n")
            self.assertEqual(snapshots[2]["매출.txt"], snapshots[0]["매출.txt"])


if __name__ == "__main__":
    unittest.main()
