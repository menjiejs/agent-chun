import os
import secrets
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from app.agent import (
    DEFAULT_SESSION_ID,
    get_current_info,
    list_skills,
    run_conversation,
    stream_conversation,
    switch_skill,
)


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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/skills")
def skills(session_id: Optional[str] = Query(default=None)):
    normalized_session_id = normalize_session_id(session_id)
    return {
        "session_id": normalized_session_id,
        "current_skill": get_current_info(normalized_session_id),
        "skills": list_skills(),
    }


@app.post("/switch_skill", dependencies=[Depends(require_api_token)])
def switch_skill_api(request: SwitchSkillRequest):
    session_id = normalize_session_id(request.session_id)
    skill_name = request.skill_name.strip()

    if not switch_skill(skill_name, session_id):
        raise HTTPException(status_code=404, detail=f"skill '{skill_name}' not found")

    return {
        "session_id": session_id,
        "current_skill": get_current_info(session_id),
    }


@app.post("/chat", dependencies=[Depends(require_api_token)])
async def chat(request: ChatRequest):
    session_id = normalize_session_id(request.session_id)

    try:
        reply = await run_in_threadpool(run_conversation, request.message, session_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "agent failed", "detail": str(exc)},
        ) from exc

    return {"session_id": session_id, "reply": reply}


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        authorization = websocket.headers.get("authorization", "")
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            token = value

    try:
        verify_token_value(token)
    except HTTPException as exc:
        await websocket.close(code=1008, reason=str(exc.detail))
        return

    await websocket.accept()

    try:
        while True:
            body = await websocket.receive_json()
            try:
                request = ChatRequest.model_validate(body)
            except Exception as exc:
                await websocket.send_json({"type": "error", "error": str(exc)})
                continue

            session_id = normalize_session_id(request.session_id)
            await websocket.send_json({"type": "start", "session_id": session_id})

            try:
                stream = stream_conversation(request.message, session_id)
                async for chunk in iterate_in_threadpool(stream):
                    await websocket.send_json({"type": "delta", "content": chunk})
                await websocket.send_json({"type": "done", "session_id": session_id})
            except Exception as exc:
                await websocket.send_json({"type": "error", "error": str(exc)})
    except WebSocketDisconnect:
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
