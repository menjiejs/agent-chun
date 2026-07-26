import os
import unittest
from unittest.mock import Mock, patch

import requests

from app.tts_client import (
    TTSConfigurationError,
    TTSUnavailableError,
    TTSUpstreamError,
    synthesize_speech,
)


WAV_BYTES = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"\x00" * 36


class TTSClientTest(unittest.TestCase):
    def test_requires_api_key(self):
        with patch.dict(os.environ, {"ZHIPU_API_KEY": ""}):
            with self.assertRaises(TTSConfigurationError):
                synthesize_speech("你好", "request-1")

    @patch("app.tts_client.requests.post")
    def test_returns_valid_wav(self, post):
        response = Mock(status_code=200, content=WAV_BYTES)
        post.return_value = response

        with patch.dict(os.environ, {"ZHIPU_API_KEY": "secret-key"}):
            result = synthesize_speech("你好", "request-1")

        self.assertEqual(result, WAV_BYTES)
        post.assert_called_once_with(
            "https://open.bigmodel.cn/api/paas/v4/audio/speech",
            headers={
                "Authorization": "Bearer secret-key",
                "Content-Type": "application/json",
                "X-Request-ID": "request-1",
            },
            json={
                "model": "glm-tts",
                "input": "你好",
                "voice": "tongtong",
                "response_format": "wav",
            },
            timeout=(5, 120),
        )

    @patch("app.tts_client.requests.post")
    def test_rejects_non_wav_success(self, post):
        post.return_value = Mock(status_code=200, content=b'{"error":"bad"}')

        with patch.dict(os.environ, {"ZHIPU_API_KEY": "secret-key"}):
            with self.assertRaises(TTSUpstreamError):
                synthesize_speech("你好", "request-1")

    @patch("app.tts_client.requests.post")
    def test_maps_rate_limit_to_unavailable(self, post):
        post.return_value = Mock(status_code=429, content=b"rate limited")

        with patch.dict(os.environ, {"ZHIPU_API_KEY": "secret-key"}):
            with self.assertRaises(TTSUnavailableError):
                synthesize_speech("你好", "request-1")

    @patch("app.tts_client.requests.post")
    def test_maps_timeout_to_unavailable(self, post):
        post.side_effect = requests.Timeout("private upstream detail")

        with patch.dict(os.environ, {"ZHIPU_API_KEY": "secret-key"}):
            with self.assertRaises(TTSUnavailableError):
                synthesize_speech("你好", "request-1")

    @patch("app.tts_client.requests.post")
    def test_log_excludes_text_and_key(self, post):
        private_text = "不得写入日志的语音文本"
        post.return_value = Mock(status_code=200, content=WAV_BYTES)

        with self.assertLogs("agent.server", level="INFO") as captured:
            with patch.dict(os.environ, {"ZHIPU_API_KEY": "secret-key"}):
                synthesize_speech(private_text, "request-1")

        output = "\n".join(captured.output)
        self.assertNotIn(private_text, output)
        self.assertNotIn("secret-key", output)
        self.assertIn("text_length=11", output)


if __name__ == "__main__":
    unittest.main()
