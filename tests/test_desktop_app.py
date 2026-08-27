import os
import subprocess
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.desktop_app import QtScheduler, restore_conversation_history


class FakeWindow:
    def __init__(self):
        self.messages = []

    def add_message(self, role, text):
        self.messages.append((role, text))


class FakePool:
    def __init__(self):
        self.started = []

    def start(self, task):
        self.started.append(task)


class QtSchedulerTest(unittest.TestCase):
    def setUp(self):
        self.scheduler = QtScheduler.__new__(QtScheduler)
        self.scheduler.pool = FakePool()
        self.scheduler._tasks = set()

    def test_retains_task_until_success_callback_finishes(self):
        results = []

        self.scheduler(
            lambda: "done",
            results.append,
            lambda error: None,
        )
        task = self.scheduler.pool.started[0]

        self.assertIn(task, self.scheduler._tasks)

        task.signals.success.emit("done")

        self.assertEqual(results, ["done"])
        self.assertNotIn(task, self.scheduler._tasks)

    def test_retains_task_until_error_callback_finishes(self):
        errors = []

        self.scheduler(
            lambda: None,
            lambda result: None,
            errors.append,
        )
        task = self.scheduler.pool.started[0]
        error = RuntimeError("boom")

        self.assertIn(task, self.scheduler._tasks)

        task.signals.error.emit(error)

        self.assertEqual(errors, [error])
        self.assertNotIn(task, self.scheduler._tasks)


class DesktopAppHistoryTest(unittest.TestCase):
    def test_desktop_app_defers_history_store_import_until_runtime_config(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "import app.desktop_app; "
                    "print('app.history_store' in sys.modules)"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout.strip(), "False")

    def test_restore_conversation_history_replays_displayable_messages(self):
        window = FakeWindow()

        restore_conversation_history(
            window,
            lambda session_id: [
                {"role": "system", "content": "语音模型尚未准备"},
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "BOSS，您好。"},
            ],
            "desktop",
        )

        self.assertEqual(
            window.messages,
            [
                ("system", "语音模型尚未准备"),
                ("user", "你好"),
                ("assistant", "BOSS，您好。"),
            ],
        )

    def test_restore_conversation_history_uses_desktop_session_id(self):
        seen_session_ids = []
        window = FakeWindow()

        restore_conversation_history(
            window,
            lambda session_id: seen_session_ids.append(session_id) or [],
            "desktop",
        )

        self.assertEqual(seen_session_ids, ["desktop"])

    def test_restore_conversation_history_skips_non_displayable_records(self):
        window = FakeWindow()

        restore_conversation_history(
            window,
            lambda session_id: [
                {"role": "assistant", "content": ""},
                {"role": "tool", "content": "raw tool output"},
                {"role": "assistant", "tool_calls": [{"id": "call_1"}]},
                {"role": "user", "content": "  "},
                {"role": "assistant", "content": "可以显示"},
            ],
            "desktop",
        )

        self.assertEqual(window.messages, [("assistant", "可以显示")])

    def test_restore_conversation_history_ignores_load_failures(self):
        window = FakeWindow()

        def fail(session_id):
            raise RuntimeError("database unavailable")

        restore_conversation_history(window, fail, "desktop")

        self.assertEqual(window.messages, [])


if __name__ == "__main__":
    unittest.main()
