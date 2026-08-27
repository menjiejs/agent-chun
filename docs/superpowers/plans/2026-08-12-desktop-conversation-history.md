# Desktop Conversation History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore saved `desktop` session messages when the macOS desktop app starts, while keeping the chat history panel collapsed by default.

**Architecture:** Add a small runtime-level history restoration helper in `app/desktop_app.py` that reads stored messages for the `ConversationService.session_id` and replays displayable messages through the existing `MainWindow.add_message(role, text)` interface. Keep `MainWindow` responsible for rendering and preserving its collapsed-history default; use existing `add_message` behavior to update the subtitle to the latest assistant reply.

**Tech Stack:** Python, PySide6, SQLite-backed `app.history_store.load_messages`, `unittest`.

## Global Constraints

- Load the full persisted `desktop` session once during startup.
- Keep the history panel collapsed on launch; users see the full history after pressing the existing expand button.
- Show the latest assistant message on the main stage subtitle after startup history restoration.
- Skip records without displayable text, including tool calls or empty content.
- History loading failure must not block the app from opening.
- Do not add session selection, deletion, database schema changes, or voice-flow changes.
- Use `./venv/bin/python -m unittest ...`; `pytest` is not installed in this project.

---

## File Structure

- Modify `app/desktop_app.py`: import `load_messages`, create a narrow `restore_conversation_history(window, loader, session_id)` helper, and call it from `DesktopRuntime.__init__` after the `ConversationService` is created.
- Modify `tests/test_desktop_ui.py`: add UI assertions that preloaded messages do not expand the history panel and that the latest assistant message becomes the subtitle.
- Create `tests/test_desktop_app.py`: unit-test the runtime helper without launching the tray, microphone, or real OpenAI/TTS dependencies.

### Task 1: Lock UI Rendering Expectations

**Files:**
- Modify: `tests/test_desktop_ui.py`

**Interfaces:**
- Consumes: `MainWindow.add_message(role: str, text: str) -> None`
- Produces: Test coverage proving existing UI behavior supports hidden startup history and subtitle restoration.

- [ ] **Step 1: Write the failing UI expectations**

Add these helper and tests inside `DesktopUiTest` in `tests/test_desktop_ui.py`:

```python
    def _message_bubbles(self):
        return [
            (label.property("role"), label.text())
            for label in self.window.messages.findChildren(QLabel)
            if label.property("role")
        ]

    def test_preloaded_messages_keep_history_collapsed(self):
        self.window.add_message("user", "你好")
        self.window.add_message("assistant", "BOSS，您好。")

        self.assertTrue(self.window.history_panel.isHidden())
        self.assertEqual(
            self._message_bubbles(),
            [("user", "你好"), ("assistant", "BOSS，您好。")],
        )

    def test_latest_preloaded_assistant_message_is_stage_subtitle(self):
        self.window.add_message("assistant", "第一条回复")
        self.window.add_message("user", "继续")
        self.window.add_message("assistant", "最近的回复")

        self.assertEqual(self.window.subtitle_label.text(), "最近的回复")
```

- [ ] **Step 2: Run the focused UI tests**

Run: `./venv/bin/python -m unittest tests.test_desktop_ui.DesktopUiTest -v`

Expected: PASS, because `MainWindow.add_message` already inserts bubbles while keeping `history_panel` hidden and updates `subtitle_label` for assistant messages.

- [ ] **Step 3: Commit the UI expectation tests**

Run:

```bash
git add tests/test_desktop_ui.py
git commit -m "test: lock desktop history rendering behavior"
```

### Task 2: Restore Persisted History at Startup

**Files:**
- Modify: `app/desktop_app.py`
- Create: `tests/test_desktop_app.py`

**Interfaces:**
- Consumes: `app.history_store.load_messages(session_id: str) -> list[dict]`
- Consumes: `ConversationService.session_id: str`
- Produces: `restore_conversation_history(window, loader, session_id) -> None`

- [ ] **Step 1: Write failing tests for startup restoration**

Create `tests/test_desktop_app.py` with this content:

```python
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.desktop_app import restore_conversation_history


class FakeWindow:
    def __init__(self):
        self.messages = []

    def add_message(self, role, text):
        self.messages.append((role, text))


class DesktopAppHistoryTest(unittest.TestCase):
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
```

- [ ] **Step 2: Run the new tests and verify failure**

Run: `./venv/bin/python -m unittest tests.test_desktop_app -v`

Expected: FAIL with an import error or attribute error because `restore_conversation_history` does not exist yet.

- [ ] **Step 3: Add the minimal restoration helper and startup call**

Change `app/desktop_app.py` as follows.

Add this import near the other app imports:

```python
from app.history_store import load_messages
```

Add this module constant and helper above `DesktopRuntime`:

```python
DISPLAYABLE_HISTORY_ROLES = {"assistant", "system", "user"}


def restore_conversation_history(window, loader, session_id):
    try:
        messages = loader(session_id)
    except Exception:
        return

    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role not in DISPLAYABLE_HISTORY_ROLES:
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        window.add_message(role, content)
```

In `DesktopRuntime.__init__`, replace the inline `ConversationService(...)` argument with a stored service and call the helper immediately after constructing the controller:

```python
        self.conversation_service = ConversationService(run_conversation, synthesize_speech)
        self.controller = DesktopController(
            self.window,
            VoiceSession(),
            self.speech_router,
            self.conversation_service,
            play_wav,
            self.scheduler,
            QApplication.beep,
        )
        restore_conversation_history(
            self.window,
            load_messages,
            self.conversation_service.session_id,
        )
```

- [ ] **Step 4: Run the restoration tests and focused UI tests**

Run: `./venv/bin/python -m unittest tests.test_desktop_app tests.test_desktop_ui -v`

Expected: PASS. `tests.test_desktop_app` proves the loader behavior, and `tests.test_desktop_ui` proves hidden panel and subtitle behavior.

- [ ] **Step 5: Commit the startup restoration**

Run:

```bash
git add app/desktop_app.py tests/test_desktop_app.py
git commit -m "fix: restore desktop conversation history on launch"
```

### Task 3: Verify Packaged Desktop Behavior

**Files:**
- Modify: none expected
- Build artifact: `dist/芷春.app`

**Interfaces:**
- Consumes: persisted SQLite data at `~/Library/Application Support/Zhichun/data/agent.db`
- Produces: rebuilt macOS app bundle whose startup UI restores existing chat history.

- [ ] **Step 1: Run the full test suite**

Run: `./venv/bin/python -m unittest discover -s tests -v`

Expected: PASS. Existing unrelated warnings about `datetime.utcnow()` or Starlette/httpx may appear, but no test failures or errors should appear.

- [ ] **Step 2: Rebuild the app bundle**

Run: `./venv/bin/pyinstaller --clean --noconfirm Zhichun.spec`

Expected: PASS and `dist/芷春.app` is refreshed.

- [ ] **Step 3: Launch the rebuilt app**

Run: `open /Users/yyz/agent/dist/芷春.app`

Expected: The app opens with the history panel collapsed and the main subtitle showing the latest assistant reply from the persisted `desktop` session.

- [ ] **Step 4: Expand the history panel for visual verification**

Use the existing history toggle button in the app.

Expected: Previously saved `desktop` messages appear in chronological order, including the recent user message `你好` and assistant reply `BOSS，您好。请问有什么我可以协助您的？`.

- [ ] **Step 5: Commit the rebuilt bundle if tracked changes require it**

Run:

```bash
git status --short dist/芷春.app
git add dist/芷春.app
git commit -m "build: refresh desktop app bundle"
```

Expected: If `dist/芷春.app` is untracked or ignored, skip this commit and report that the local bundle was rebuilt for manual use.

## Self-Review

- Spec coverage: Task 1 covers collapsed history and subtitle rendering. Task 2 covers loading the persisted `desktop` session, chronological replay through the window, skipping non-displayable records, and ignoring load failures. Task 3 covers full tests, rebuild, launch, collapsed state, and manual expand verification with existing persisted history.
- Placeholder scan: The plan contains no `TBD`, no `TODO`, no open-ended validation instructions, and no references to undefined functions.
- Type consistency: `restore_conversation_history(window, loader, session_id)` consumes a callable matching `load_messages(session_id)` and calls the existing `window.add_message(role, text)` interface. `ConversationService.session_id` is already a string and defaults to `"desktop"`.
