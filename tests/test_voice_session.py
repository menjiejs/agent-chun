import unittest

from app.voice_session import InvalidVoiceTransition, VoiceSession, VoiceState


class VoiceSessionTest(unittest.TestCase):
    def test_complete_conversation_returns_to_waiting(self):
        session = VoiceSession()

        session.wake()
        self.assertEqual(session.state, VoiceState.LISTENING)

        session.submit_transcript("今天天气怎么样")
        self.assertEqual(session.state, VoiceState.THINKING)

        session.start_reply()
        self.assertEqual(session.state, VoiceState.SPEAKING)

        session.finish_reply()
        self.assertEqual(session.state, VoiceState.WAITING)

    def test_pause_stops_wake_detection_until_resumed(self):
        session = VoiceSession()

        session.pause()
        self.assertEqual(session.state, VoiceState.PAUSED)

        with self.assertRaises(InvalidVoiceTransition):
            session.wake()

        session.resume()
        self.assertEqual(session.state, VoiceState.WAITING)

    def test_empty_transcript_returns_to_waiting_with_message(self):
        session = VoiceSession()
        session.wake()

        message = session.submit_transcript("   ")

        self.assertEqual(message, "没有听清，请再说一次")
        self.assertEqual(session.state, VoiceState.WAITING)

    def test_failure_can_recover_to_waiting(self):
        session = VoiceSession()

        session.fail("麦克风不可用")
        self.assertEqual(session.state, VoiceState.ERROR)
        self.assertEqual(session.error_message, "麦克风不可用")

        session.recover()
        self.assertEqual(session.state, VoiceState.WAITING)
        self.assertIsNone(session.error_message)

    def test_typed_chat_returns_to_paused_voice_state(self):
        session = VoiceSession()
        session.pause()

        session.submit_text("用文字聊天")
        session.start_reply()
        session.finish_reply()

        self.assertEqual(session.state, VoiceState.PAUSED)

    def test_failed_request_returns_to_previous_voice_state(self):
        session = VoiceSession()
        session.pause()
        session.submit_text("测试断网")

        session.cancel_interaction()

        self.assertEqual(session.state, VoiceState.PAUSED)

    def test_disabling_voice_while_listening_cancels_to_paused(self):
        session = VoiceSession()
        session.wake()

        session.set_voice_enabled(False)

        self.assertEqual(session.state, VoiceState.PAUSED)
        self.assertFalse(session.voice_enabled)

    def test_disabling_voice_during_reply_returns_to_paused(self):
        session = VoiceSession()
        session.submit_text("继续处理")

        session.set_voice_enabled(False)
        session.start_reply()
        session.finish_reply()

        self.assertEqual(session.state, VoiceState.PAUSED)

    def test_typed_message_overrides_active_listening(self):
        session = VoiceSession()
        session.wake()

        session.submit_text("改用文字")

        self.assertEqual(session.state, VoiceState.THINKING)


if __name__ == "__main__":
    unittest.main()
