import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ["API_TOKEN"] = "test-token"
os.environ.setdefault("ZHIPU_API_KEY", "test-key")

from app.server import app, get_host, run_server
from app.tts_client import TTSConfigurationError, TTSUpstreamError


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token"}

    def test_app_is_fastapi_instance(self):
        self.assertIsInstance(app, FastAPI)

    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_response_has_request_id(self):
        response = self.client.get("/health")

        self.assertTrue(response.headers["X-Request-ID"])

    def test_unknown_route_uses_error_envelope(self):
        response = self.client.get("/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")
        self.assertEqual(
            response.json()["error"]["request_id"],
            response.headers["X-Request-ID"],
        )

    def test_method_not_allowed_uses_error_envelope(self):
        response = self.client.post("/health")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"]["code"], "HTTP_ERROR")
        self.assertEqual(
            response.json()["error"]["request_id"],
            response.headers["X-Request-ID"],
        )

    def test_skills_endpoint_uses_default_session(self):
        response = self.client.get("/skills")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["session_id"], "default")
        self.assertEqual(body["current_skill"]["name"], "chun")
        self.assertEqual(body["skills"][0]["name"], "chun")

    def test_skills_rejects_unsafe_session_id_without_logging_it(self):
        unsafe_session_id = "safe\nforged-log-entry"
        with self.assertLogs("agent.server", level="INFO") as captured:
            response = self.client.get(
                "/skills",
                params={"session_id": unsafe_session_id},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertNotIn("forged-log-entry", "\n".join(captured.output))

    def test_chat_rejects_blank_message(self):
        response = self.client.post(
            "/chat",
            headers=self.headers,
            json={"message": "   "},
        )

        self.assertEqual(response.status_code, 422)

    def test_chat_requires_authorization(self):
        response = self.client.post("/chat", json={"message": "你好"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"],
            {
                "code": "AUTHENTICATION_FAILED",
                "message": "认证失败",
                "request_id": response.headers["X-Request-ID"],
            },
        )
        self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")

    def test_chat_rejects_wrong_authorization(self):
        response = self.client.post(
            "/chat",
            headers={"Authorization": "Bearer wrong-token"},
            json={"message": "你好"},
        )

        self.assertEqual(response.status_code, 401)

    def test_chat_returns_agent_reply(self):
        with patch("app.server.run_conversation", return_value="收到，BOSS。"):
            response = self.client.post(
                "/chat",
                headers=self.headers,
                json={"session_id": "user-1", "message": "你好"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"session_id": "user-1", "reply": "收到，BOSS。"},
        )

    def test_chat_internal_error_is_safe(self):
        secret = "private-provider-error"
        with patch("app.server.run_conversation", side_effect=RuntimeError(secret)):
            response = self.client.post(
                "/chat",
                headers=self.headers,
                json={"session_id": "user-1", "message": "你好"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "INTERNAL_ERROR")
        self.assertEqual(response.json()["error"]["message"], "服务暂时不可用")
        self.assertEqual(
            response.json()["error"]["request_id"],
            response.headers["X-Request-ID"],
        )
        self.assertNotIn(secret, response.text)

    def test_request_log_excludes_message_and_token(self):
        private_message = "不得写入日志的聊天内容"
        with self.assertLogs("agent.server", level="INFO") as captured:
            with patch("app.server.run_conversation", return_value="收到"):
                self.client.post(
                    "/chat",
                    headers=self.headers,
                    json={"session_id": "user-1", "message": private_message},
                )

        output = "\n".join(captured.output)
        self.assertNotIn(private_message, output)
        self.assertNotIn("test-token", output)
        self.assertIn("session_id=user-1", output)

    def test_switch_skill_requires_authorization(self):
        response = self.client.post("/switch_skill", json={"skill_name": "chun"})

        self.assertEqual(response.status_code, 401)

    def test_tts_requires_authorization(self):
        response = self.client.post("/tts", json={"text": "你好"})

        self.assertEqual(response.status_code, 401)

    def test_tts_rejects_blank_text(self):
        response = self.client.post(
            "/tts",
            headers=self.headers,
            json={"text": "   "},
        )

        self.assertEqual(response.status_code, 422)

    def test_tts_rejects_text_over_1024_characters(self):
        response = self.client.post(
            "/tts",
            headers=self.headers,
            json={"text": "春" * 1025},
        )

        self.assertEqual(response.status_code, 422)

    def test_tts_returns_wav(self):
        wav = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"\x00" * 36
        with patch("app.server.synthesize_speech", return_value=wav):
            response = self.client.post(
                "/tts",
                headers=self.headers,
                json={"text": " 你好 "},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertEqual(int(response.headers["content-length"]), len(wav))
        self.assertEqual(response.content, wav)

    def test_tts_configuration_error_is_safe(self):
        with patch(
            "app.server.synthesize_speech",
            side_effect=TTSConfigurationError("private detail"),
        ):
            response = self.client.post(
                "/tts",
                headers=self.headers,
                json={"text": "你好"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private detail", response.text)

    def test_tts_upstream_error_is_safe(self):
        with patch(
            "app.server.synthesize_speech",
            side_effect=TTSUpstreamError("private detail"),
        ):
            response = self.client.post(
                "/tts",
                headers=self.headers,
                json={"text": "你好"},
            )

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private detail", response.text)

    def test_tts_log_excludes_text_and_token(self):
        private_text = "不得写入日志的语音文本"
        wav = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"\x00" * 36
        with self.assertLogs("agent.server", level="INFO") as captured:
            with patch("app.server.synthesize_speech", return_value=wav):
                self.client.post(
                    "/tts",
                    headers=self.headers,
                    json={"text": private_text},
                )

        output = "\n".join(captured.output)
        self.assertNotIn(private_text, output)
        self.assertNotIn("test-token", output)

    def test_get_host_defaults_to_loopback(self):
        with patch.dict(os.environ, {"HOST": ""}):
            self.assertEqual(get_host(), "127.0.0.1")

    def test_get_host_accepts_lan_binding(self):
        with patch.dict(os.environ, {"HOST": "0.0.0.0"}):
            self.assertEqual(get_host(), "0.0.0.0")

    def test_websocket_validation_error_is_safe(self):
        with self.client.websocket_connect(
            "/ws/chat?token=test-token"
        ) as websocket:
            websocket.send_json({"message": "   "})
            response = websocket.receive_json()

        self.assertEqual(
            response,
            {
                "type": "error",
                "code": "VALIDATION_ERROR",
                "message": "消息格式不正确",
            },
        )

    def test_websocket_malformed_json_is_safe(self):
        with self.client.websocket_connect(
            "/ws/chat?token=test-token"
        ) as websocket:
            websocket.send_text("{")
            response = websocket.receive_json()

        self.assertEqual(
            response,
            {
                "type": "error",
                "code": "VALIDATION_ERROR",
                "message": "消息格式不正确",
            },
        )

    def test_websocket_internal_error_is_safe(self):
        with patch(
            "app.server.stream_conversation",
            side_effect=RuntimeError("private-provider-error"),
        ):
            with self.client.websocket_connect(
                "/ws/chat?token=test-token"
            ) as websocket:
                websocket.send_json({"session_id": "user-1", "message": "你好"})
                websocket.receive_json()
                response = websocket.receive_json()

        self.assertEqual(
            response,
            {
                "type": "error",
                "code": "INTERNAL_ERROR",
                "message": "服务暂时不可用",
            },
        )
        self.assertNotIn("private-provider-error", str(response))

    def test_run_server_disables_unsafe_uvicorn_request_logs(self):
        with (
            patch("app.server.get_host", return_value="127.0.0.1"),
            patch("app.server.uvicorn.run") as uvicorn_run,
        ):
            run_server()

        uvicorn_run.assert_called_once_with(
            app,
            host="127.0.0.1",
            port=8000,
            access_log=False,
            log_level="warning",
        )


if __name__ == "__main__":
    unittest.main()
