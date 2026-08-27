import unittest

from app.desktop_service import ConversationResult, ConversationService


class DesktopServiceTest(unittest.TestCase):
    def test_returns_reply_and_synthesized_audio(self):
        service = ConversationService(
            chat=lambda text, session_id: f"回答：{text}",
            synthesize=lambda text, request_id: b"wav:" + text.encode(),
        )

        result = service.answer("你好")

        self.assertEqual(result, ConversationResult("回答：你好", b"wav:\xe5\x9b\x9e\xe7\xad\x94\xef\xbc\x9a\xe4\xbd\xa0\xe5\xa5\xbd", None))

    def test_keeps_text_reply_when_voice_synthesis_fails(self):
        def fail_synthesis(text, request_id):
            raise RuntimeError("offline")

        service = ConversationService(
            chat=lambda text, session_id: "文字回答",
            synthesize=fail_synthesis,
        )

        result = service.answer("你好")

        self.assertEqual(result.reply, "文字回答")
        self.assertIsNone(result.audio)
        self.assertEqual(result.audio_error, "语音回答暂时不可用")


if __name__ == "__main__":
    unittest.main()
