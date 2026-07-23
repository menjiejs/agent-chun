# Basic Logging And Error Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add privacy-safe request logging and consistent HTTP/WebSocket errors to the existing FastAPI service.

**Architecture:** A small standard-library logging module owns console and rotating-file handlers. FastAPI middleware assigns request IDs and logs request metadata, while centralized exception handlers return safe JSON envelopes. WebSocket errors use fixed codes and messages so Python exception text never reaches clients.

**Tech Stack:** Python 3.14, FastAPI, Starlette, Python `logging`, `unittest`

## Global Constraints

- Do not log chat messages, request bodies, API tokens, API keys, or exception text.
- Log to both stderr and `logs/agent.log`.
- Rotate the file at 5 MB and retain 5 backups.
- Do not add third-party dependencies.
- Preserve all existing successful endpoint response bodies.

---

### Task 1: Logging Configuration

**Files:**
- Create: `app/logging_config.py`
- Create: `tests/test_logging_config.py`

**Interfaces:**
- Produces: `logger: logging.Logger` named `agent.server`
- Produces: `LOG_FILE: pathlib.Path` pointing to `logs/agent.log`

- [ ] **Step 1: Write the failing logger test**

```python
import unittest
from logging.handlers import RotatingFileHandler

from app.logging_config import LOG_FILE, logger


class LoggingConfigTest(unittest.TestCase):
    def test_logger_has_console_and_rotating_file_handlers(self):
        handler_types = {type(handler).__name__ for handler in logger.handlers}

        self.assertIn("StreamHandler", handler_types)
        self.assertTrue(
            any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers)
        )

    def test_logger_writes_to_expected_file(self):
        logger.info("logging_config_test")
        for handler in logger.handlers:
            handler.flush()

        self.assertTrue(LOG_FILE.exists())
```

- [ ] **Step 2: Run the test and verify RED**

Run: `venv/bin/python -m unittest tests.test_logging_config -v`

Expected: FAIL because `app.logging_config` does not exist.

- [ ] **Step 3: Add the minimal logger**

```python
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOGGER_NAME = "agent.server"
LOG_FILE = Path("logs/agent.log")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging():
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


logger = configure_logging()
```

- [ ] **Step 4: Run the logger test and verify GREEN**

Run: `venv/bin/python -m unittest tests.test_logging_config -v`

Expected: 2 tests pass.

- [ ] **Step 5: Commit the logger**

```bash
git add app/logging_config.py tests/test_logging_config.py
git commit -m "添加基础日志配置"
```

### Task 2: HTTP Request IDs And Safe Errors

**Files:**
- Modify: `app/server.py:1-122`
- Modify: `tests/test_server.py:13-76`

**Interfaces:**
- Produces: `error_response(request, status_code, code, message, headers=None)`
- Produces: response header `X-Request-ID`
- Produces: HTTP error body `{"error": {"code", "message", "request_id"}}`

- [ ] **Step 1: Add failing HTTP behavior tests**

Add tests that require:

```python
def test_health_response_has_request_id(self):
    response = self.client.get("/health")

    self.assertTrue(response.headers["X-Request-ID"])


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
```

Update the existing unauthorized assertion to expect:

```python
self.assertEqual(
    response.json()["error"],
    {
        "code": "AUTHENTICATION_FAILED",
        "message": "认证失败",
        "request_id": response.headers["X-Request-ID"],
    },
)
self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")
```

- [ ] **Step 2: Run the HTTP tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_server -v`

Expected: FAIL because request IDs, unified errors, and request logs are missing.

- [ ] **Step 3: Add middleware and centralized handlers**

In `app/server.py`, import `time`, `uuid`, `Request`, `RequestValidationError`, `JSONResponse`, and `logger`.

Add:

```python
def get_request_id(request):
    return getattr(request.state, "request_id", uuid.uuid4().hex)


def error_response(request, status_code, code, message, headers=None):
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": get_request_id(request),
            }
        },
    )


@app.middleware("http")
async def log_request(request, call_next):
    request.state.request_id = uuid.uuid4().hex
    started_at = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    logger.info(
        "request_complete request_id=%s method=%s path=%s status_code=%s "
        "duration_ms=%.2f session_id=%s",
        request.state.request_id,
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started_at) * 1000,
        getattr(request.state, "session_id", "-"),
    )
    return response
```

Register handlers:

```python
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    if exc.status_code == 401:
        code, message = "AUTHENTICATION_FAILED", "认证失败"
    elif exc.status_code == 404:
        code, message = "NOT_FOUND", str(exc.detail)
    elif exc.status_code >= 500:
        code, message = "INTERNAL_ERROR", "服务暂时不可用"
    else:
        code, message = "HTTP_ERROR", str(exc.detail)
    return error_response(request, exc.status_code, code, message, exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return error_response(
        request, 422, "VALIDATION_ERROR", "请求参数不正确"
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request, exc):
    logger.error(
        "request_error request_id=%s method=%s path=%s error_type=%s",
        get_request_id(request),
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    return error_response(
        request, 500, "INTERNAL_ERROR", "服务暂时不可用"
    )
```

Accept the Starlette request as `http_request: Request` and set the normalized session ID without reading the request body in middleware:

```python
def skills(
    http_request: Request,
    session_id: Optional[str] = Query(default=None),
):
    normalized_session_id = normalize_session_id(session_id)
    http_request.state.session_id = normalized_session_id


def switch_skill_api(request: SwitchSkillRequest, http_request: Request):
    session_id = normalize_session_id(request.session_id)
    http_request.state.session_id = session_id


async def chat(request: ChatRequest, http_request: Request):
    session_id = normalize_session_id(request.session_id)
    http_request.state.session_id = session_id
```

Remove the endpoint-local `try/except` in `chat` so the global handler owns unknown errors.

- [ ] **Step 4: Run the HTTP tests and verify GREEN**

Run: `venv/bin/python -m unittest tests.test_server -v`

Expected: all HTTP tests pass and no response contains provider exception text.

- [ ] **Step 5: Commit HTTP logging and errors**

```bash
git add app/server.py tests/test_server.py
git commit -m "统一请求日志和错误响应"
```

### Task 3: Safe WebSocket Errors And Documentation

**Files:**
- Modify: `app/server.py:125-162`
- Modify: `tests/test_server.py`
- Modify: `README.md:139-166`
- Modify: `docs/superpowers/specs/2026-07-23-basic-logging-errors-design.md`

**Interfaces:**
- Produces: WebSocket error message `{"type": "error", "code", "message"}`
- Produces: connection metadata logs without query strings or message bodies

- [ ] **Step 1: Write failing WebSocket tests**

```python
def test_websocket_validation_error_is_safe(self):
    with self.client.websocket_connect("/ws/chat?token=test-token") as websocket:
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
```

- [ ] **Step 2: Run the WebSocket tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_server.ServerTest.test_websocket_validation_error_is_safe tests.test_server.ServerTest.test_websocket_internal_error_is_safe -v`

Expected: FAIL because current messages expose Pydantic and runtime exception text.

- [ ] **Step 3: Replace WebSocket exception text with fixed errors**

Assign a `connection_id = uuid.uuid4().hex`, log connect/disconnect using `websocket.url.path`, and replace the two unsafe messages with:

```python
await websocket.send_json(
    {
        "type": "error",
        "code": "VALIDATION_ERROR",
        "message": "消息格式不正确",
    }
)
```

and:

```python
logger.error(
    "websocket_error connection_id=%s path=%s session_id=%s error_type=%s",
    connection_id,
    websocket.url.path,
    session_id,
    type(exc).__name__,
)
await websocket.send_json(
    {
        "type": "error",
        "code": "INTERNAL_ERROR",
        "message": "服务暂时不可用",
    }
)
```

Do not log `websocket.url` because its query string contains the API token.

- [ ] **Step 4: Document operation**

Add a short `日志与错误` README section:

```markdown
## 日志与错误

服务日志同时显示在终端并写入 `logs/agent.log`。日志文件达到 5 MB 后自动轮换，保留最近 5 个文件。

日志不会记录聊天原文、请求正文、API Token 或 API Key。HTTP 响应头中的 `X-Request-ID` 可用于在日志中定位对应请求。
```

Keep the design document aligned with the privacy decision that exception text is not logged.

- [ ] **Step 5: Run all verification**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m py_compile app/logging_config.py app/server.py tests/test_logging_config.py tests/test_server.py
git diff --check
```

Expected: all tests pass, compilation exits 0, and `git diff --check` produces no output.

- [ ] **Step 6: Commit WebSocket safety and documentation**

```bash
git add app/server.py tests/test_server.py README.md docs/superpowers/specs/2026-07-23-basic-logging-errors-design.md docs/superpowers/plans/2026-07-23-basic-logging-errors.md
git commit -m "完成基础日志和错误处理"
```
