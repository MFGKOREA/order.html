import io
import shutil
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import hub  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 13, 11, 0)
EXAMPLES = [  # the user's own requests and the exact answers Pickle passes on
    ("피클에게 브로컬리 발주 2개 넣어줘", "발주 접수 #1: 브로콜리 2개"),
    ("매장에 감자튀김 재고 몇개야", "감자튀김: 예상 20.0개"),
    ("지금 현재 그로스세일즈 얼마야",
     "2026-11-13 매장 당일 그로스 세일즈: 3,250,000원 (목표 포캐스트 400만 원 대비 81.3% 달성)"),
    ("내일 피자치즈 입고 몇개야", "피자치즈: 내일(11/14) 입고 6개"),
    ("HR 스케쥴 확정 눌러줘", "HR 스케줄 확정 접수 #2"),
]


def append(path, *lines):
    with open(path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


class InboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.file, self.state, self.log = d / "요청.txt", d / "state" / "inbox.json", io.StringIO()

    def tearDown(self):
        self.tmp.cleanup()

    def inbox(self):
        return hub.Inbox(self.file, self.state, self.log)

    def test_lines_already_there_on_first_start_are_history(self):
        append(self.file, "old request")
        box = self.inbox()
        self.assertEqual(box.poll(), [])
        append(self.file, "new request")
        self.assertEqual(box.poll(), ["new request"])
        self.assertEqual(box.poll(), [])

    def test_first_request_into_a_new_file_counts(self):
        box = self.inbox()
        append(self.file, "first")
        self.assertEqual(box.poll(), ["first"])

    def test_restart_never_repeats_and_catches_up(self):
        box = self.inbox()
        append(self.file, "a")
        self.assertEqual(box.poll(), ["a"])
        append(self.file, "b", "", "c")  # arrives while the hub is down
        self.assertEqual(self.inbox().poll(), ["b", "c"])

    def test_empty_file_mid_sync_is_ignored(self):
        box = self.inbox()
        append(self.file, "a")
        box.poll()
        self.file.write_text("", encoding="utf-8")
        self.assertEqual(box.poll(), [])
        self.file.write_text("a\n", encoding="utf-8")
        self.assertEqual(box.poll(), [])

    def test_rewritten_file_never_runs_old_lines_again(self):
        box = self.inbox()
        append(self.file, "브로콜리 발주 2개")
        box.poll()
        self.file.write_text("브로콜리 발주 20개\n", encoding="utf-8")  # an old line edited
        self.assertEqual(box.poll(), [])
        self.assertIn("rewritten", self.log.getvalue())
        append(self.file, "양파 재고")
        self.assertEqual(box.poll(), ["양파 재고"])


class HubTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.cache, self.drive, self.state = d / "cache", d / "drive", d / "state"
        shutil.copytree(FIX, self.cache)
        self.log = io.StringIO()

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, askers=None):
        return hub.Hub(self.cache, self.drive, self.state, askers, self.log)

    def read(self, name):
        return (self.drive / name).read_text(encoding="utf-8")

    def test_users_five_requests_end_to_end(self):
        h = self.make()
        h.tick(NOW)
        names = {p.name for p in self.drive.iterdir()}
        self.assertLessEqual({"재고.txt", "재고_ㄱ.txt", "매출.txt", "입고.txt", "입고_내일.txt", "BOH.txt", "작업.txt"},
                             names)
        for question, answer in EXAMPLES:  # 답.txt holds just the latest answer
            append(self.drive / hub.INBOX, question)
            h.tick(NOW)
            self.assertEqual(self.read(hub.OUTBOX), f"> {question}\n{answer}\n")
        self.assertEqual(self.read(hub.TASKS), "#1 접수 11:00 발주 브로콜리 2개\n#2 접수 11:00 HR 스케줄 확정\n")

    def test_remy_marks_a_task_done_without_replacing_pickles_answer(self):
        h = self.make()
        h.tick(NOW)
        append(self.drive / hub.INBOX, "브로콜리 발주 2개")
        h.tick(NOW)
        append(self.drive / hub.INBOX, "#1 완료")
        h.tick(NOW)
        self.assertEqual(self.read(hub.TASKS), "#1 완료 11:00 발주 브로콜리 2개\n")
        self.assertEqual(self.read(hub.OUTBOX), "> 브로콜리 발주 2개\n발주 접수 #1: 브로콜리 2개\n")

    def test_restart_does_not_repeat_actions(self):
        h = self.make()
        h.tick(NOW)
        append(self.drive / hub.INBOX, "브로콜리 발주 2개")
        h.tick(NOW)
        self.make().tick(NOW)
        self.assertEqual(self.read(hub.TASKS), "#1 접수 11:00 발주 브로콜리 2개\n")

    def test_free_question_gets_a_finished_three_line_answer_from_gpt_only(self):
        asked = []

        def claude(q, system):
            asked.append("Claude")
            yield "결론: 쓰이면 안 됨"

        def gpt(q, system):
            asked.append("GPT")
            yield from "결론: 비 오는 날은 매장 손님이 줄 수 있음\n근거: 배달 비중이 느는 경향\n확인 필요: 없음".splitlines()

        h = self.make({"Claude": claude, "GPT": gpt})
        h.tick(NOW)
        append(self.drive / hub.INBOX, "오늘 비 오면 손님 줄어?")
        h.tick(NOW)
        h.pool.shutdown(wait=True)
        self.assertEqual(asked, ["GPT"])
        self.assertEqual(self.read(hub.OUTBOX), "> 오늘 비 오면 손님 줄어?\n결론: 비 오는 날은 매장 손님이 줄 수 있음\n"
                                                "근거: 배달 비중이 느는 경향\n확인 필요: 없음\n")
        self.assertIn("→ GPT", self.read(hub.BOARD))

    def test_personal_information_never_reaches_pickle(self):
        def gpt(q, system):
            yield from "결론: 연락처 010-1234-5678\n근거: 직원 명부 (HR 11/13 09:00)\n확인 필요: 없음".splitlines()

        h = self.make({"GPT": gpt})
        h.tick(NOW)
        append(self.drive / hub.INBOX, "점장 연락처 알려줘")
        h.tick(NOW)
        h.pool.shutdown(wait=True)
        self.assertIn("결론: 연락처 [가림]", self.read(hub.OUTBOX))
        self.assertNotIn("010-1234-5678", self.read(hub.OUTBOX) + self.read(hub.BOARD))
        alerts = (self.state / "alerts.log").read_text(encoding="utf-8")
        self.assertIn("개인정보 가림 답.txt: 전화번호", alerts)
        self.assertIn("개인정보 가림", self.log.getvalue())

    def test_private_words_file_is_used(self):
        self.state.mkdir(parents=True)
        (self.state / "private_terms.txt").write_text("신우님 본가\n", encoding="utf-8")
        h = self.make()
        h.outbox.add("q", "결론: 신우님 본가 근처")
        self.assertEqual(self.read(hub.OUTBOX), "> q\n결론: [가림] 근처\n")

    def test_remy_answers_a_browser_question_through_the_inbox(self):
        h = self.make({"GPT": lambda q, s: iter(())})
        h.tick(NOW)
        append(self.drive / hub.INBOX, "세콤 출입 기록 확인해줘")
        h.tick(NOW)
        h.pool.shutdown(wait=True)
        h.pool = hub.ThreadPoolExecutor(max_workers=4)
        self.assertFalse((self.drive / hub.OUTBOX).exists())  # nothing yet: Pickle says 접수
        board = self.read(hub.BOARD)
        qid = board.split("## [대기] ")[1].split()[0]
        self.assertIn(f"{qid}", board)
        self.assertIn("→ 레미", board)
        append(self.drive / hub.INBOX, f"{qid} 답: 결론: 김민수 09:02 출입 / 근거: 출입 기록 (세콤 11/13 09:05) / 확인 필요: 없음")
        h.tick(NOW)
        self.assertEqual(self.read(hub.OUTBOX), "> 세콤 출입 기록 확인해줘\n결론: 김민수 09:02 출입\n"
                                                "근거: 출입 기록 (세콤 11/13 09:05)\n확인 필요: 없음\n")
        self.assertIn(f"[완료] {qid}", self.read(hub.BOARD))

    def test_without_ai_keys_free_questions_say_so(self):
        h = self.make()
        h.tick(NOW)
        append(self.drive / hub.INBOX, "오늘 비 오면 손님 줄어?")
        h.tick(NOW)
        h.pool.shutdown(wait=True)  # free questions are answered on a worker
        self.assertEqual(self.read(hub.OUTBOX), "> 오늘 비 오면 손님 줄어?\nAI 연결 안 됨\n")

    def test_answer_file_keeps_only_the_latest(self):
        h = self.make()
        h.tick(NOW)
        append(self.drive / hub.INBOX, *[f"양파 재고 {i}" for i in range(15)])
        h.tick(NOW)
        text = self.read(hub.OUTBOX)
        self.assertEqual(text.count("> "), hub.KEEP_ANSWERS)
        self.assertTrue(text.startswith(f"> 양파 재고 {15 - hub.KEEP_ANSWERS}\n양파: 예상 13.0개\n"))

    def test_console(self):
        out = io.StringIO()
        self.make().console(io.StringIO("매장에 감자튀김 재고 몇개야\n\n"), out)
        self.assertRegex(out.getvalue(), r"^감자튀김: 예상 \d+\.\d개\n$")  # real clock: the estimate moves

    def test_request_reaches_the_answer_file_within_milliseconds(self):
        h = self.make()
        h.tick()
        stop = threading.Event()

        def loop():
            while not stop.is_set():
                h.tick()
                time.sleep(0.01)

        worker = threading.Thread(target=loop)
        worker.start()
        try:
            start = time.perf_counter()
            append(self.drive / hub.INBOX, "지금 현재 그로스세일즈 얼마야")
            while not (self.drive / hub.OUTBOX).exists():
                time.sleep(0.001)
            elapsed = time.perf_counter() - start
        finally:
            stop.set()
            worker.join()
        self.assertLess(elapsed, 0.5)
        self.assertIn("매장 당일 그로스 세일즈", self.read(hub.OUTBOX))


if __name__ == "__main__":
    unittest.main()
