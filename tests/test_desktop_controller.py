import unittest

from app.desktop_controller import DesktopController
from app.desktop_service import ConversationResult
from app.voice_session import VoiceSession, VoiceState


class FakeWindow:
    def __init__(self):
        self.messages = []
        self.status = None
        self.busy = False

    def add_message(self, role, text):
        self.messages.append((role, text))

    def set_status(self, text):
        self.status = text

    def set_busy(self, busy):
        self.busy = busy


class FakeRouter:
    def __init__(self):
        self.paused = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


class DeferredScheduler:
    def __init__(self):
        self.pending = []

    def __call__(self, work, on_success, on_error):
        self.pending.append((work, on_success, on_error))

    def succeed_next(self):
        work, on_success, _ = self.pending.pop(0)
        on_success(work())


def run_now(work, on_success, on_error):
    try:
        on_success(work())
    except Exception as exc:
        on_error(exc)


class DesktopControllerTest(unittest.TestCase):
    def test_wake_does_not_play_a_system_beep(self):
        window = FakeWindow()
        router = FakeRouter()
        session = VoiceSession()
        beeps = []
        controller = DesktopController(
            window,
            session,
            router,
            service=None,
            play_audio=lambda audio: None,
            schedule=run_now,
            beep=lambda: beeps.append("beep"),
        )

        controller.handle_wake()

        self.assertEqual(beeps, [])
        self.assertEqual(session.state, VoiceState.LISTENING)
        self.assertEqual(window.status, "正在聆听…")

    def test_voice_conversation_resumes_keyword_detection_after_audio(self):
        window = FakeWindow()
        router = FakeRouter()
        session = VoiceSession()
        played = []
        controller = DesktopController(
            window,
            session,
            router,
            service=type(
                "Service",
                (),
                {"answer": lambda self, text: ConversationResult("你好", b"wav", None)},
            )(),
            play_audio=played.append,
            schedule=run_now,
            beep=lambda: None,
        )

        controller.handle_wake()
        controller.handle_transcript("你好")

        self.assertEqual(session.state, VoiceState.WAITING)
        self.assertFalse(router.paused)
        self.assertEqual(played, [b"wav"])
        self.assertEqual(window.status, "等待“芷春”")

    def test_typed_chat_keeps_voice_paused(self):
        window = FakeWindow()
        router = FakeRouter()
        session = VoiceSession()
        session.pause()
        router.pause()
        controller = DesktopController(
            window,
            session,
            router,
            service=type(
                "Service",
                (),
                {"answer": lambda self, text: ConversationResult("收到", None, None)},
            )(),
            play_audio=lambda audio: None,
            schedule=run_now,
            beep=lambda: None,
        )

        controller.send_text("文字消息")

        self.assertEqual(session.state, VoiceState.PAUSED)
        self.assertTrue(router.paused)
        self.assertEqual(window.status, "语音唤醒已暂停")

    def test_disabling_voice_during_request_keeps_it_paused_after_reply(self):
        window = FakeWindow()
        router = FakeRouter()
        session = VoiceSession()
        scheduler = DeferredScheduler()
        controller = DesktopController(
            window,
            session,
            router,
            service=type(
                "Service",
                (),
                {"answer": lambda self, text: ConversationResult("收到", None, None)},
            )(),
            play_audio=lambda audio: None,
            schedule=scheduler,
            beep=lambda: None,
        )
        controller.send_text("稍后继续")

        controller.set_voice_enabled(False)
        scheduler.succeed_next()

        self.assertEqual(session.state, VoiceState.PAUSED)
        self.assertTrue(router.paused)
        self.assertEqual(window.status, "语音唤醒已暂停")

    def test_no_speech_returns_to_keyword_waiting(self):
        window = FakeWindow()
        router = FakeRouter()
        session = VoiceSession()
        controller = DesktopController(
            window,
            session,
            router,
            service=None,
            play_audio=lambda audio: None,
            schedule=run_now,
            beep=lambda: None,
        )
        controller.handle_wake()

        controller.handle_no_speech()

        self.assertEqual(session.state, VoiceState.WAITING)
        self.assertFalse(router.paused)
        self.assertEqual(window.status, "等待“芷春”")


if __name__ == "__main__":
    unittest.main()
