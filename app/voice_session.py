from enum import Enum


class VoiceState(str, Enum):
    WAITING = "waiting"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    PAUSED = "paused"
    ERROR = "error"


class InvalidVoiceTransition(RuntimeError):
    pass


class VoiceSession:
    def __init__(self):
        self.state = VoiceState.WAITING
        self.voice_enabled = True
        self.error_message = None
        self._return_state = VoiceState.WAITING

    def _idle_state(self):
        return VoiceState.WAITING if self.voice_enabled else VoiceState.PAUSED

    def _require(self, expected):
        if self.state != expected:
            raise InvalidVoiceTransition(
                f"cannot transition from {self.state.value}; expected {expected.value}"
            )

    def wake(self):
        self._require(VoiceState.WAITING)
        self.state = VoiceState.LISTENING

    def submit_transcript(self, transcript):
        self._require(VoiceState.LISTENING)
        if not transcript.strip():
            self.state = self._idle_state()
            return "没有听清，请再说一次"
        self._return_state = self._idle_state()
        self.state = VoiceState.THINKING
        return None

    def submit_text(self, text):
        if self.state not in (
            VoiceState.WAITING,
            VoiceState.PAUSED,
            VoiceState.LISTENING,
        ):
            raise InvalidVoiceTransition(f"cannot submit text while {self.state.value}")
        if not text.strip():
            raise ValueError("text must not be blank")
        self._return_state = self._idle_state()
        self.state = VoiceState.THINKING

    def start_reply(self):
        self._require(VoiceState.THINKING)
        self.state = VoiceState.SPEAKING

    def finish_reply(self):
        self._require(VoiceState.SPEAKING)
        self.state = self._return_state

    def cancel_interaction(self):
        if self.state not in (VoiceState.THINKING, VoiceState.SPEAKING):
            raise InvalidVoiceTransition(f"cannot cancel while {self.state.value}")
        self.state = self._return_state

    def pause(self):
        self.set_voice_enabled(False)

    def resume(self):
        self._require(VoiceState.PAUSED)
        self.set_voice_enabled(True)

    def set_voice_enabled(self, enabled):
        self.voice_enabled = bool(enabled)
        target = self._idle_state()
        if self.state in (
            VoiceState.WAITING,
            VoiceState.PAUSED,
            VoiceState.LISTENING,
            VoiceState.ERROR,
        ):
            self.state = target
        else:
            self._return_state = target
        if enabled:
            self.error_message = None

    def cancel_listening(self):
        self._require(VoiceState.LISTENING)
        self.state = self._idle_state()

    def reset_error(self):
        self.error_message = None
        self.state = self._idle_state()

    def fail(self, message):
        self.error_message = message
        self.state = VoiceState.ERROR

    def recover(self):
        self._require(VoiceState.ERROR)
        self.reset_error()
