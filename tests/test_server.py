import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ["API_TOKEN"] = "test-token"

from app.server import app


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

    def test_skills_endpoint_uses_default_session(self):
        response = self.client.get("/skills")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["session_id"], "default")
        self.assertEqual(body["current_skill"]["name"], "chun")
        self.assertEqual(body["skills"][0]["name"], "chun")

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


if __name__ == "__main__":
    unittest.main()
