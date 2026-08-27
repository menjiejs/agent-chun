from dataclasses import dataclass
from typing import Optional
from uuid import uuid4


@dataclass(frozen=True)
class ConversationResult:
    reply: str
    audio: Optional[bytes]
    audio_error: Optional[str]


class ConversationService:
    def __init__(self, chat, synthesize, session_id="desktop"):
        self.chat = chat
        self.synthesize = synthesize
        self.session_id = session_id

    def answer(self, text):
        reply = self.chat(text, self.session_id)
        try:
            audio = self.synthesize(reply, uuid4().hex)
        except Exception:
            return ConversationResult(reply, None, "语音回答暂时不可用")
        return ConversationResult(reply, audio, None)
