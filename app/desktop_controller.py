from app.voice_session import VoiceState


class DesktopController:
    def __init__(
        self,
        window,
        session,
        speech_router,
        service,
        play_audio,
        schedule,
        beep,
    ):
        self.window = window
        self.session = session
        self.speech_router = speech_router
        self.service = service
        self.play_audio = play_audio
        self.schedule = schedule
        self.beep = beep

    def handle_wake(self):
        if self.session.state != VoiceState.WAITING:
            return
        self.session.wake()
        self.window.set_status("正在聆听…")

    def handle_transcript(self, text):
        if self.session.state != VoiceState.LISTENING:
            return
        self.session.submit_transcript(text)
        self._request_answer(text)

    def handle_no_speech(self):
        if self.session.state != VoiceState.LISTENING:
            return
        self.session.cancel_listening()
        self._restore_idle_state()

    def send_text(self, text):
        self.session.submit_text(text)
        self._request_answer(text)

    def _request_answer(self, text):
        self.speech_router.pause()
        self.window.add_message("user", text)
        self.window.set_status("正在思考…")
        self.window.set_busy(True)
        self.schedule(
            lambda: self.service.answer(text),
            self._answer_ready,
            self._answer_failed,
        )

    def _answer_ready(self, result):
        self.window.add_message("assistant", result.reply)
        self.session.start_reply()
        if result.audio_error:
            self.window.add_message("system", result.audio_error)
        if not result.audio:
            self._playback_complete(None)
            return
        self.window.set_status("正在回答…")
        self.schedule(
            lambda: self.play_audio(result.audio),
            self._playback_complete,
            self._playback_failed,
        )

    def _answer_failed(self, error):
        del error
        self.window.add_message("system", "网络暂时不可用，请稍后再试")
        self.session.cancel_interaction()
        self._restore_idle_state()

    def _playback_failed(self, error):
        del error
        self.window.add_message("system", "语音播放失败，已保留文字回答")
        self._playback_complete(None)

    def _playback_complete(self, result):
        del result
        self.session.finish_reply()
        self._restore_idle_state()

    def _restore_idle_state(self):
        self.window.set_busy(False)
        if self.session.state == VoiceState.WAITING:
            self.speech_router.resume()
            self.window.set_status("等待“芷春”")
        else:
            self.speech_router.pause()
            self.window.set_status("语音唤醒已暂停")

    def set_voice_enabled(self, enabled):
        self.session.set_voice_enabled(enabled)
        if not enabled:
            self.speech_router.pause()
            if self.session.state == VoiceState.PAUSED:
                self.window.set_status("语音唤醒已暂停")
        elif self.session.state == VoiceState.WAITING:
            self.speech_router.resume()
            self.window.set_status("等待“芷春”")
