import os
import secrets
import time
import uuid
from typing import Optional

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.responses import JSONResponse

from app.agent import (
    DEFAULT_SESSION_ID,
    get_current_info,
    list_skills,
    run_conversation,
    stream_conversation,
    switch_skill,
)
from app.logging_config import logger


HOST = "127.0.0.1"
HTTP_PORT = 8000

app = FastAPI(title="芷春 Agent", version="1.0.0")
bearer_scheme = HTTPBearer(auto_error=False)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value):
        if not value.strip():
            raise ValueError("message must be a non-empty string")
        return value


class SwitchSkillRequest(BaseModel):
    skill_name: str
    session_id: Optional[str] = None

    @field_validator("skill_name")
    @classmethod
    def skill_name_must_not_be_blank(cls, value):
        if not value.strip():
            raise ValueError("skill_name must be a non-empty string")
        return value


def normalize_session_id(session_id=None):
    if isinstance(session_id, str) and session_id.strip():
        return session_id.strip()
    return DEFAULT_SESSION_ID


def get_api_token():
    return os.getenv("API_TOKEN", "").strip()


def verify_token_value(token):
    expected_token = get_api_token()
    if not expected_token:
        raise HTTPException(status_code=500, detail="API_TOKEN is not configured")
    if not token or not secrets.compare_digest(token, expected_token):
        raise HTTPException(
            status_code=401,
            detail="invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_api_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    token = credentials.credentials if credentials else None
    verify_token_value(token)


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
    return error_response(request, 422, "VALIDATION_ERROR", "请求参数不正确")


@app.middleware("http")
async def log_request(request, call_next):
    request.state.request_id = uuid.uuid4().hex
    started_at = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "request_error request_id=%s method=%s path=%s error_type=%s",
            request.state.request_id,
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        response = error_response(
            request,
            500,
            "INTERNAL_ERROR",
            "服务暂时不可用",
        )

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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/skills")
def skills(
    http_request: Request,
    session_id: Optional[str] = Query(default=None),
):
    normalized_session_id = normalize_session_id(session_id)
    http_request.state.session_id = normalized_session_id
    return {
        "session_id": normalized_session_id,
        "current_skill": get_current_info(normalized_session_id),
        "skills": list_skills(),
    }


@app.post("/switch_skill", dependencies=[Depends(require_api_token)])
def switch_skill_api(request: SwitchSkillRequest, http_request: Request):
    session_id = normalize_session_id(request.session_id)
    http_request.state.session_id = session_id
    skill_name = request.skill_name.strip()

    if not switch_skill(skill_name, session_id):
        raise HTTPException(status_code=404, detail=f"skill '{skill_name}' not found")

    return {
        "session_id": session_id,
        "current_skill": get_current_info(session_id),
    }


@app.post("/chat", dependencies=[Depends(require_api_token)])
async def chat(request: ChatRequest, http_request: Request):
    session_id = normalize_session_id(request.session_id)
    http_request.state.session_id = session_id
    reply = await run_in_threadpool(run_conversation, request.message, session_id)

    return {"session_id": session_id, "reply": reply}


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    connection_id = uuid.uuid4().hex
    session_id = "-"
    token = websocket.query_params.get("token")
    if not token:
        authorization = websocket.headers.get("authorization", "")
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            token = value

    try:
        verify_token_value(token)
    except HTTPException:
        logger.info(
            "websocket_rejected connection_id=%s path=%s",
            connection_id,
            websocket.url.path,
        )
        await websocket.close(code=1008, reason="authentication failed")
        return

    await websocket.accept()
    logger.info(
        "websocket_connected connection_id=%s path=%s",
        connection_id,
        websocket.url.path,
    )

    try:
        while True:
            body = await websocket.receive_json()
            try:
                request = ChatRequest.model_validate(body)
            except Exception as exc:
                logger.info(
                    "websocket_validation_error connection_id=%s path=%s "
                    "error_type=%s",
                    connection_id,
                    websocket.url.path,
                    type(exc).__name__,
                )
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "VALIDATION_ERROR",
                        "message": "消息格式不正确",
                    }
                )
                continue

            session_id = normalize_session_id(request.session_id)
            await websocket.send_json({"type": "start", "session_id": session_id})

            try:
                stream = stream_conversation(request.message, session_id)
                async for chunk in iterate_in_threadpool(stream):
                    await websocket.send_json({"type": "delta", "content": chunk})
                await websocket.send_json({"type": "done", "session_id": session_id})
            except Exception as exc:
                logger.error(
                    "websocket_error connection_id=%s path=%s session_id=%s "
                    "error_type=%s",
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
    except WebSocketDisconnect:
        logger.info(
            "websocket_disconnected connection_id=%s path=%s session_id=%s",
            connection_id,
            websocket.url.path,
            session_id,
        )
        return


def run_server():
    print(f"HTTP 服务已启动: http://{HOST}:{HTTP_PORT}")
    print(f"接口文档: http://{HOST}:{HTTP_PORT}/docs")
    print(f"健康检查: http://{HOST}:{HTTP_PORT}/health")
    print(f"技能列表: http://{HOST}:{HTTP_PORT}/skills")
    print(f"聊天接口: http://{HOST}:{HTTP_PORT}/chat")
    print(f"WebSocket 流式聊天: ws://{HOST}:{HTTP_PORT}/ws/chat")
    uvicorn.run(app, host=HOST, port=HTTP_PORT)


if __name__ == "__main__":
    run_server()
