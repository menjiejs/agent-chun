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

    def test_switch_skill_requires_authorization(self):
        response = self.client.post("/switch_skill", json={"skill_name": "chun"})

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
