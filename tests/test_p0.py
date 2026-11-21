"""P0: sqlite ledger, retry queue, watchdog, schema is covered in test_pipeline, secrets, hub screen."""
import shutil
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import eventlog  # noqa: E402
import hub  # noqa: E402
import hub_page  # noqa: E402
import retryq  # noqa: E402
import hubkeys  # noqa: E402
import watchdog  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 13, 11, 0)
LINE = "Q-20261113-001 | 피클 | Claude | 대기 | 공지문 작성"


class LedgerStore(unittest.TestCase):
    def test_migration_is_idempotent_and_the_text_file_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = root / "대화.txt"
            text.write_text(LINE + "\n" + LINE.replace("대기", "완료") + "\n", encoding="utf-8")
            log = eventlog.EventLog(root / "ledger.sqlite", text)
            self.assertEqual(log.count(), 2)
            self.assertEqual(text.read_text(encoding="utf-8").count("\n"), 2)
            again = eventlog.EventLog(root / "ledger.sqlite", text)
            self.assertEqual(again.count(), 2)
            self.assertEqual(text.read_text(encoding="utf-8").count("\n"), 2)

    def test_the_same_line_is_stored_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = eventlog.EventLog(root / "ledger.sqlite", root / "대화.txt")
            fields = hub.parse_handoff(LINE)
            self.assertTrue(log.add(LINE, fields))
            self.assertFalse(log.add(LINE, fields))
            self.assertEqual(log.count(), 1)
            self.assertEqual((root / "대화.txt").read_text(encoding="utf-8").strip(), LINE)

    def test_two_writers_do_not_lose_a_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = eventlog.EventLog(root / "ledger.sqlite", root / "대화.txt")
            errors = []

            def write(i):
                try:
                    line = f"Q-20261113-{i:03d} | 피클 | GPT | 대기 | 질문 {i}"
                    log.add(line, hub.parse_handoff(line))
                except Exception as exc:  # noqa: BLE001 — the test records it
                    errors.append(exc)

            threads = [threading.Thread(target=write, args=(i,)) for i in range(1, 21)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            self.assertEqual(log.count(), 20)

    def test_a_line_appended_outside_is_picked_up_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = root / "대화.txt"
            log = eventlog.EventLog(root / "ledger.sqlite", text)
            with text.open("a", encoding="utf-8") as handle:
                handle.write(LINE + "\n")
            self.assertEqual(log.poll_new(), [LINE])
            self.assertEqual(log.poll_new(), [])


class Retry(unittest.TestCase):
    def test_backoff_has_jitter_and_ends_in_the_dead_letter_list(self):
        samples = [retryq.delay_seconds(0, rng=lambda: n / 9) for n in range(10)]
        self.assertTrue(all(0.8 <= sample <= 1.2 for sample in samples))
        self.assertLess(min(samples), 1)
        self.assertGreater(max(samples), 1)
        self.assertAlmostEqual(retryq.delay_seconds(3, rng=lambda: 0.5), 8)
        with tempfile.TemporaryDirectory() as tmp:
            queue = retryq.RetryQueue(Path(tmp) / "retry.sqlite", rng=lambda: 0.5, max_attempts=2)
            queue.note("k", {"request": "질문"}, "down", NOW)
            self.assertEqual(queue.claim(NOW), [])  # about a second early
            claimed = queue.claim(NOW + timedelta(seconds=1))
            self.assertEqual(len(claimed), 1)
            self.assertEqual(queue.fail("k", "down", NOW + timedelta(seconds=1)), "retry")
            self.assertEqual(queue.claim(NOW + timedelta(seconds=1)), [])
            self.assertEqual(queue.fail("k", "down", NOW + timedelta(seconds=4)), "dead")
            self.assertEqual(queue.dead()[0]["error"], "down")
            self.assertEqual(queue.open_count(), 0)


class Watch(unittest.TestCase):
    def test_three_minutes_is_the_line(self):
        fresh = "허브 정상 2026-11-13 11:00\nAI 오늘 $0.00 / $1.00\n"
        self.assertFalse(watchdog.should_restart(None, NOW))
        self.assertFalse(watchdog.should_restart(fresh, NOW + timedelta(minutes=3)))
        self.assertTrue(watchdog.should_restart(fresh, NOW + timedelta(minutes=3, seconds=1)))
        self.assertTrue(watchdog.should_restart("고장난 파일", NOW))


class Secrets(unittest.TestCase):
    def test_env_value_and_key_shapes_are_redacted_and_not_logged(self):
        env = {"OPENAI_API_KEY": "super-secret-value", "ANTHROPIC_API_KEY": ""}
        self.assertEqual(hubkeys.read_secret("OPENAI_API_KEY", env), "super-secret-value")
        self.assertIsNone(hubkeys.read_secret("ANTHROPIC_API_KEY", env))
        text = "key=super-secret-value sk-ant-api03-abcdefghijklmnopqrstuvwxyz password=hunter2"
        cleaned = hubkeys.redact(text, hubkeys.secret_values(env))
        self.assertNotIn("super-secret-value", cleaned)
        self.assertNotIn("sk-ant-api03", cleaned)
        self.assertNotIn("hunter2", cleaned)
        self.assertIn("[비밀]", cleaned)


class Screen(unittest.TestCase):
    def test_confirm_is_one_button_and_badges_are_named(self):
        page = hub_page.render({
            "confirms": [{"id": "3", "text": "발주 브로콜리 2개"}],
            "badges": [("Claude", "정상"), ("GPT", "지연"), ("레미", "끊김"), ("피클", "정상")],
            "timeline": [{"at": "2026-11-13T11:00:00", "id": "Q-1", "status": "완료",
                          "from": "Claude", "to": "피클", "body": "결론: 됨"}],
            "spend": "AI 오늘 $0.00 / $1.00",
        })
        self.assertIn("확인 #3", page)
        self.assertIn('data-state="지연"', page)
        self.assertIn("피클 허브", page)
        self.assertIn("--ground: #16130f", page)
        self.assertNotIn("sk-", page)
        self.assertIn("font-size: 1.5rem", page)


class HubP0(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.drive, self.state, self.cache = root / "drive", root / "state", root / "cache"
        shutil.copytree(FIX, self.cache)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_failed_call_is_retried_then_buried_without_the_key(self):
        def boom(message, system):
            raise ConnectionError("sk-ant-api03-abcdefghijklmnopqrstuvwxyz")

        h = hub.Hub(self.cache, self.drive, self.state, {"GPT": boom, "Claude": boom}, confirm=False, env={})
        h.retry.max_attempts = 1
        h.ledger.add("Q-9", "피클", "GPT", "대기", "sk-ant-api03-abcdefghijklmnopqrstuvwxyz")
        h.tick(NOW)
        with (self.drive / hub.INBOX).open("a", encoding="utf-8") as handle:
            handle.write("오늘 비 오면 손님 줄어?\n")
        h.tick(NOW)
        h.pool.shutdown(wait=True)
        self.assertEqual(h.retry.open_count(), 1)
        h.pool = hub.ThreadPoolExecutor(max_workers=4)
        h.tick(NOW + timedelta(seconds=2))
        h.pool.shutdown(wait=True)
        self.assertEqual(len(h.retry.dead()), 1)
        mirror = (self.drive / hub.LEDGER).read_text(encoding="utf-8")
        self.assertIn("반려", mirror)
        self.assertIn("[비밀]", mirror)
        self.assertNotIn("sk-ant", mirror)
        self.assertNotIn("sk-ant", h.retry.dead()[0]["error"])

    def test_confirm_button_writes_the_line_only_while_waiting(self):
        h = hub.Hub(self.cache, self.drive, self.state, confirm=True, env={})
        h.tick(NOW)
        with (self.drive / hub.INBOX).open("a", encoding="utf-8") as handle:
            handle.write("브로콜리 2개 발주\n")
        h.tick(NOW)
        self.assertTrue(h.request_confirm(1))
        self.assertIn("확인 #1", (self.drive / hub.INBOX).read_text(encoding="utf-8"))
        self.assertFalse(h.request_confirm(9))
        h.tick(NOW)
        self.assertFalse(h.request_confirm(1))
        self.assertIn("피클 허브", hub_page.render(h.screen()))


if __name__ == "__main__":
    unittest.main()
