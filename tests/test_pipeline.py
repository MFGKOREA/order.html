import json
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import pipeline as pl  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 13, 11, 0)
GOOD = "결론: 양파 20kg 추가 발주\n근거: 재고 13.0개, 모레 2.5kg 입고 (매장 11/13 09:00)\n확인 필요: 없음"


class FakeAI:
    """Stand-in AI: answers in order (the last one repeats), records every envelope it gets."""

    def __init__(self, *answers, delay=0.0):
        self.answers, self.delay, self.calls = list(answers), delay, []

    def __call__(self, message, system):
        self.calls.append((json.loads(message), system))
        if self.delay:
            time.sleep(self.delay)
        answer = self.answers[min(len(self.calls), len(self.answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        yield from answer.splitlines()


class Routing(unittest.TestCase):
    def test_each_kind_goes_to_its_owner(self):
        cases = {
            "공지문 작성해줘": ("build", False, ["Claude"], "GPT"),
            "엑셀 수식 만들어줘": ("build", False, ["Claude"], "GPT"),
            "다음 주 화요일 양파 발주량?": ("analysis", False, ["Claude"], None),
            "이 계산 맞는지 검증해줘": ("verify", False, ["GPT"], None),
            "세콤 출입 기록 확인해줘": ("browser", False, ["레미"], None),
            "오늘 비 오면 손님 줄어?": ("general", False, ["GPT"], None),
            "[중요] 다음 주 화요일 양파 발주량?": ("analysis", True, ["Claude", "GPT"], None),
        }
        for question, (kind, important, answerers, checker) in cases.items():
            with self.subTest(question=question):
                self.assertEqual(pl.classify(question), (kind, important))
                self.assertEqual(pl.plan(kind, important), (answerers, checker))


class Data(unittest.TestCase):
    def test_gather_tags_each_line_with_source_and_time(self):
        lines = pl.gather("다음 주 화요일 양파 발주량?", FIX, NOW)
        self.assertEqual(lines[0], "양파: 예상 13.0개 (매장 11/13 09:00)")
        self.assertRegex(lines[1], r"^양파: 모레\(11/15\) 입고 2\.5kg \(매장 \d+/\d+ \d\d:\d\d\)$")
        self.assertEqual(len(lines), 2)
        sales = pl.gather("그로스 얼마야", FIX, NOW)
        self.assertRegex(sales[0], r"^2026-11-13 매장 당일 그로스 세일즈: .* \(POS \d+/\d+ \d\d:\d\d\)$")
        self.assertEqual(pl.gather("근무 몇 명", FIX, NOW), ["BOH: 근무 중 5명, 퇴근 완료 2명 (HR 11/13 14:05)"])
        self.assertEqual(pl.gather("오늘 비 오면 손님 줄어?", FIX, NOW), [])

    def test_envelope_has_the_designed_fields(self):
        env = pl.envelope("Q-20261113-001", "양파 발주량?", ["Claude"], ["양파: 예상 13.0개 (매장 11/13 09:00)"], NOW)
        self.assertEqual(list(env), ["id", "날짜", "요청자", "대상", "질문", "원하는형식", "출처", "시각", "상태", "자료", "검토할답"])
        self.assertEqual((env["날짜"], env["시각"], env["출처"], env["상태"]), ("2026-11-13", "11:00", ["매장"], "처리중"))


class Answers(unittest.TestCase):
    def test_parse_tolerates_markdown_and_keeps_code_apart(self):
        text = "**결론**: 수식 수정\n- 근거: B열 합계 (POS 11/13 14:00)\n  이어지는 설명\n확인필요: 없음\n```\n=SUM(B2:B9)\n```"
        self.assertEqual(pl.parse_answer(text), {"결론": "수식 수정", "근거": "B열 합계 (POS 11/13 14:00) 이어지는 설명",
                                                 "확인 필요": "없음", "code": "```\n=SUM(B2:B9)\n```"})
        self.assertIsNone(pl.parse_answer("양파 20kg 발주하세요"))

    def test_problems(self):
        ok = pl.parse_answer(GOOD)
        self.assertIsNone(pl.problem(ok))
        self.assertIsNone(pl.problem(pl.parse_answer("결론: 모름\n근거: 자료 없음\n확인 필요: 신우님 확인")))
        self.assertIn("형식", pl.problem(None))
        self.assertIn("금지어 관제", pl.problem(pl.parse_answer("결론: 관제 완료\n근거: x\n확인 필요: 없음")))
        self.assertIn("출처", pl.problem(pl.parse_answer("결론: 20kg 발주\n근거: 최근 소진량\n확인 필요: 없음")))
        self.assertIn("출처", pl.problem(pl.parse_answer("결론: 20kg 발주\n근거: 소진 (매장)\n확인 필요: 없음")))
        self.assertIn("출처", pl.problem(pl.parse_answer("결론: 김민수 퇴근\n근거: 기록\n확인 필요: 없음"), {"김민수"}))

    def test_compose(self):
        a = ("Claude", pl.parse_answer(GOOD))
        b = ("GPT", pl.parse_answer("결론: 양파 15kg 추가 발주\n근거: 재고 13.0개 (매장 11/13 09:00)\n확인 필요: 없음"))
        same = ("GPT", pl.parse_answer("결론: 양파 20kg 발주 권장\n근거: 재고 (매장 11/13 09:00)\n확인 필요: 없음"))
        self.assertEqual(pl.compose([a], {"양파"}), GOOD)
        self.assertEqual(pl.compose([a, same], {"양파"}), GOOD)
        self.assertEqual(pl.compose([a, b], {"양파"}).splitlines()[2],
                         "확인 필요: Claude: 양파 20kg 추가 발주 (매장 11/13 09:00) / GPT: 양파 15kg 추가 발주 (매장 11/13 09:00)")
        self.assertEqual(pl.compose([a], set(), ["GPT 검증 못 함"]).splitlines()[2], "확인 필요: GPT 검증 못 함")
        self.assertEqual(pl.compose([], set()), pl.UNKNOWN)


class PipelineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board_path = Path(self.tmp.name) / "게시판.txt"
        self.replies = []

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, deadline=2.0, **askers):
        return pl.Pipeline(FIX, askers, systems={"Claude": "C-PROMPT", "GPT": "G-PROMPT"},
                           board=pl.Board(self.board_path), deadline=deadline, clock=lambda: NOW)

    def board(self):
        return self.board_path.read_text(encoding="utf-8")


class Run(PipelineCase):
    def test_general_question_asks_gpt_only(self):
        gpt, claude = FakeAI(GOOD), FakeAI(GOOD)
        record = self.make(GPT=gpt, Claude=claude).run("오늘 비 오면 손님 줄어?", self.replies.append)
        self.assertEqual(self.replies, [GOOD])
        self.assertEqual(claude.calls, [])
        env, system = gpt.calls[0]
        self.assertEqual((system, env["id"], env["대상"], env["상태"]), ("G-PROMPT", "Q-20261113-001", ["GPT"], "처리중"))
        self.assertEqual((record["kind"], record["status"]), ("general", "완료"))
        self.assertIn("## [대기] Q-20261113-001 11:00 오늘 비 오면 손님 줄어? → GPT", self.board())
        self.assertIn("[처리중] Q-20261113-001", self.board())
        self.assertIn("[완료] Q-20261113-001", self.board())

    def test_build_is_written_by_claude_and_checked_by_gpt(self):
        claude = FakeAI("결론: 합계 수식\n근거: B열 (POS 11/13 14:00)\n확인 필요: 없음\n```\n=SUM(B2:B9)\n```")
        gpt = FakeAI("결론: 불일치: 범위가 B10까지여야 함\n근거: 마지막 행 (POS 11/13 14:00)\n확인 필요: 없음")
        self.make(Claude=claude, GPT=gpt).run("엑셀 합계 수식 만들어줘", self.replies.append)
        env, _ = gpt.calls[0]
        self.assertEqual(env["상태"], "검증중")
        self.assertEqual(env["검토할답"], "결론: 합계 수식\n근거: B열 (POS 11/13 14:00)\n확인 필요: 없음")
        self.assertEqual(self.replies[0].splitlines()[2], "확인 필요: GPT 검증: 불일치: 범위가 B10까지여야 함")
        self.assertNotIn("SUM", self.replies[0])  # code stays on the board
        self.assertIn("=SUM(B2:B9)", self.board())
        self.assertIn("[검증중] Q-20261113-001", self.board())

    def test_important_asks_both_and_lists_a_disagreement(self):
        claude = FakeAI(GOOD)
        gpt = FakeAI("결론: 양파 15kg 추가 발주\n근거: 재고 13.0개 (매장 11/13 09:00)\n확인 필요: 없음")
        self.make(Claude=claude, GPT=gpt).run("[중요] 다음 주 화요일 양파 발주량?", self.replies.append)
        self.assertEqual(len(claude.calls) + len(gpt.calls), 2)
        self.assertTrue(self.replies[0].startswith("결론: 양파 20kg 추가 발주"))
        self.assertIn("GPT: 양파 15kg 추가 발주", self.replies[0])

    def test_bad_answer_is_sent_back_once(self):
        gpt = FakeAI("양파 20kg 발주하세요", GOOD)
        self.make(GPT=gpt).run("오늘 비 오면 손님 줄어?", self.replies.append)
        self.assertEqual(self.replies, [GOOD])
        retry, _ = gpt.calls[1]
        self.assertEqual(retry["상태"], "반려")
        self.assertIn("(반려: 3줄 형식", retry["질문"])

    def test_answer_still_bad_after_one_retry_is_dropped(self):
        gpt = FakeAI("결론: 20kg 발주\n근거: 감\n확인 필요: 없음")
        self.make(GPT=gpt).run("오늘 비 오면 손님 줄어?", self.replies.append)
        self.assertEqual(self.replies, [pl.UNKNOWN])
        self.assertEqual(len(gpt.calls), 2)
        self.assertIn("[GPT] 반려 Q-20261113-001: 숫자·이름의 출처와 시각이 근거에 없음", self.board())

    def test_missing_ai_is_noted_and_a_late_disagreement_redoes_the_answer(self):
        late = "결론: 양파 15kg 추가 발주\n근거: 재고 13.0개 (매장 11/13 09:00)\n확인 필요: 없음"
        claude, gpt = FakeAI(late, delay=0.5), FakeAI(GOOD)
        p = self.make(deadline=0.2, Claude=claude, GPT=gpt)
        start = time.perf_counter()
        p.run("[중요] 다음 주 화요일 양파 발주량?", self.replies.append)
        self.assertLess(time.perf_counter() - start, 0.45)  # did not wait for the slow AI
        self.assertEqual(self.replies, [GOOD])
        self.assertIn("[Claude] 응답 없음 Q-20261113-001: 0.2초 마감", self.board())
        until = time.time() + 2
        while len(self.replies) < 2 and time.time() < until:
            time.sleep(0.02)
        self.assertEqual(len(self.replies), 2)  # redone because the late answer disagrees
        self.assertIn("Claude: 양파 15kg 추가 발주", self.replies[1])
        self.assertIn("[Claude] 늦은 답 Q-20261113-001", self.board())

    def test_ai_error_is_noted_and_the_other_carries_on(self):
        self.make(Claude=FakeAI(ConnectionError("down")), GPT=FakeAI(GOOD)).run(
            "[중요] 다음 주 화요일 양파 발주량?", self.replies.append)
        self.assertEqual(self.replies, [GOOD])
        self.assertIn("[Claude] 응답 없음 Q-20261113-001: ConnectionError", self.board())

    def test_no_ai_connected(self):
        self.make().run("오늘 비 오면 손님 줄어?", self.replies.append)
        self.assertEqual(self.replies, [pl.NO_AI])

    def test_ids_count_up_per_day(self):
        p = self.make(GPT=FakeAI(GOOD))
        self.assertEqual([p.run("q", self.replies.append)["id"] for _ in range(2)], ["Q-20261113-001", "Q-20261113-002"])


class LogAndCache(PipelineCase):
    def make_logged(self, clock=lambda: NOW, cache=FIX, **askers):
        self.log = pl.Log(Path(self.tmp.name) / "envelopes.jsonl")
        return pl.Pipeline(cache, askers, systems={}, board=pl.Board(self.board_path), clock=clock, log=self.log,
                           reply_for=lambda request: (lambda answer: self.replies.append((request, answer))))

    def states(self, qid):
        return [r["상태"] for r in self.log.read() if r["id"] == qid]

    def test_status_changes_are_logged_in_order(self):
        p = self.make_logged(Claude=FakeAI("결론: 합계 수식\n근거: B열 (POS 11/13 14:00)\n확인 필요: 없음"),
                             GPT=FakeAI("결론: 일치\n근거: 확인함 (POS 11/13 14:00)\n확인 필요: 없음"))
        qid = p.run("엑셀 합계 수식 만들어줘", self.replies.append)["id"]
        self.assertEqual(self.states(qid), ["대기", "처리중", "검증중", "완료"])
        done = self.log.read()[-1]
        self.assertEqual((done["kind"], done["answered"], done["missing"], done["rejected"]),
                         ("build", ["Claude"], [], []))
        self.assertGreaterEqual(done["seconds"], 0)

    def test_same_question_same_day_reuses_the_answer(self):
        gpt = FakeAI(GOOD)
        p = self.make_logged(GPT=gpt)
        first = p.run("오늘 비 오면 손님 줄어?", self.replies.append)["id"]
        second = p.run("오늘 비 오면  손님 줄어", self.replies.append)
        self.assertEqual(len(gpt.calls), 1)
        self.assertEqual(self.replies, [GOOD, GOOD])
        self.assertTrue(second["cached"])
        self.assertIn(f"→ 캐시 ({first} 답 재사용)", self.board())
        self.assertTrue(self.log.read()[-1]["cached"])

    def test_cache_is_dropped_when_the_data_changes(self):
        with tempfile.TemporaryDirectory() as d:
            import shutil
            shutil.copytree(FIX, Path(d) / "c")
            gpt = FakeAI(GOOD)
            p = self.make_logged(cache=Path(d) / "c", Claude=gpt)
            p.run("다음 주 화요일 양파 발주량?", self.replies.append)
            inv = Path(d) / "c" / "live_inventory_cache.json"
            inv.write_text(inv.read_text(encoding="utf-8").replace('"on_hand": 20', '"on_hand": 30'), encoding="utf-8")
            p.run("다음 주 화요일 양파 발주량?", self.replies.append)
            self.assertEqual(len(gpt.calls), 2)  # 양파 stock moved: asked again

    def test_important_and_unknown_answers_skip_the_cache(self):
        gpt = FakeAI("결론: 20kg\n근거: 감\n확인 필요: 없음")  # never acceptable: answer is 모름
        p = self.make_logged(GPT=gpt)
        p.run("오늘 비 오면 손님 줄어?", self.replies.append)
        p.run("오늘 비 오면 손님 줄어?", self.replies.append)
        self.assertEqual(len(gpt.calls), 4)  # 2 questions x (ask + one send-back), nothing cached
        claude, gpt2 = FakeAI(GOOD), FakeAI(GOOD)
        p2 = self.make_logged(Claude=claude, GPT=gpt2)
        p2.run("다음 주 화요일 양파 발주량?", self.replies.append)
        p2.run("[중요] 다음 주 화요일 양파 발주량?", self.replies.append)
        self.assertEqual((len(claude.calls), len(gpt2.calls)), (2, 1))

    def test_next_day_asks_again(self):
        gpt, day = FakeAI(GOOD), [NOW]
        p = self.make_logged(clock=lambda: day[0], GPT=gpt)
        p.run("오늘 비 오면 손님 줄어?", self.replies.append)
        day[0] = NOW.replace(day=14)
        p.run("오늘 비 오면 손님 줄어?", self.replies.append)
        self.assertEqual(len(gpt.calls), 2)

    def test_restart_keeps_numbers_cache_and_remys_open_questions(self):
        gpt = FakeAI(GOOD)
        p = self.make_logged(GPT=gpt)
        p.run("오늘 비 오면 손님 줄어?", self.replies.append)
        remy_q = p.run("세콤 출입 기록 확인해줘", self.replies.append)["id"]
        again = self.make_logged(GPT=gpt)  # a new process reading the same log
        self.assertEqual(again.run("오늘 비 오면 손님 줄어?", self.replies.append)["id"], "Q-20261113-003")
        self.assertEqual(len(gpt.calls), 1)  # answered from the restored cache
        self.assertEqual(again.accept_remy(remy_q, "결론: 이상 없음 / 근거: 출입 기록 / 확인 필요: 없음"),
                         f"{remy_q} 완료")
        self.assertEqual(self.replies[-1], ("세콤 출입 기록 확인해줘", "결론: 이상 없음\n근거: 출입 기록\n확인 필요: 없음"))
        self.assertEqual(self.states(remy_q), ["대기", "완료"])


class Remy(PipelineCase):
    def test_browser_question_waits_for_remys_answer(self):
        p = self.make(GPT=FakeAI(GOOD))
        qid = p.run("세콤 출입 기록 확인해줘", self.replies.append)["id"]
        self.assertEqual(self.replies, [])  # Pickle says 접수 until 레미 answers
        self.assertIn(f"## [대기] {qid} 11:00 세콤 출입 기록 확인해줘 → 레미", self.board())
        self.assertEqual(p.accept_remy(qid, "결론: 김민수 09:02 출입 / 근거: 출입 기록 / 확인 필요: 없음"),
                         f"{qid} 반려: 숫자·이름의 출처와 시각이 근거에 없음")
        self.assertEqual(self.replies, [])
        self.assertEqual(p.accept_remy(qid, "결론: 김민수 09:02 출입 / 근거: 출입 기록 (세콤 11/13 09:05) / 확인 필요: 없음"),
                         f"{qid} 완료")
        self.assertEqual(self.replies, ["결론: 김민수 09:02 출입\n근거: 출입 기록 (세콤 11/13 09:05)\n확인 필요: 없음"])
        self.assertEqual(p.accept_remy(qid, "결론: x / 근거: y / 확인 필요: 없음"), f"{qid} 대기 질문 없음")


class BoardFile(unittest.TestCase):
    def test_board_masks_personal_data_and_alerts(self):
        import privacy
        with tempfile.TemporaryDirectory() as d:
            alerts = []
            b = pl.Board(Path(d) / "게시판.txt", scrub=privacy.Filter().scrub, alert=alerts.append)
            threads = [threading.Thread(target=b.note, args=(f"줄 {i}",)) for i in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            b.note("연락처 010-1234-5678")
            lines = (Path(d) / "게시판.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 21)
            self.assertEqual(lines[-1], "연락처 [가림]")
            self.assertEqual(alerts, ["게시판.txt: 전화번호"])


if __name__ == "__main__":
    unittest.main()
