from dataclasses import dataclass
from pathlib import Path
import queue
import re
import threading
from typing import Callable, Optional

import numpy as np


SAMPLE_RATE = 16000


def _pick(directory, preferred_patterns):
    for pattern in preferred_patterns:
        matches = sorted(directory.rglob(pattern)) if directory.exists() else []
        if matches:
            return matches[0]
    return None


@dataclass(frozen=True)
class ModelFiles:
    asr_tokens: Optional[Path]
    asr_encoder: Optional[Path]
    asr_decoder: Optional[Path]

    @classmethod
    def from_root(cls, root):
        root = Path(root)
        asr_dir = root / "asr"
        return cls(
            asr_tokens=_pick(asr_dir, ("tokens.txt",)),
            asr_encoder=_pick(asr_dir, ("*encoder*.int8.onnx", "*encoder*.onnx")),
            asr_decoder=_pick(asr_dir, ("*decoder*.int8.onnx", "*decoder*.onnx")),
        )

    def missing(self):
        missing = []
        if not all(
            path and path.is_file()
            for path in (self.asr_tokens, self.asr_encoder, self.asr_decoder)
        ):
            missing.append("中文识别模型")
        return missing


class SherpaRecognizer:
    def __init__(self, recognizer):
        self.recognizer = recognizer
        self.stream = recognizer.create_stream()

    def accept(self, samples):
        self.stream.accept_waveform(SAMPLE_RATE, samples)
        while self.recognizer.is_ready(self.stream):
            self.recognizer.decode_stream(self.stream)
        if not self.recognizer.is_endpoint(self.stream):
            return None
        result = self.recognizer.get_result(self.stream).strip()
        self.reset()
        return result

    def reset(self):
        self.recognizer.reset(self.stream)


class WakePhraseDetector:
    def __init__(self, recognizer, aliases=None):
        self.recognizer = recognizer
        self.aliases = aliases or ("芷春", "指春", "知春", "智春", "之春")

    def accept(self, samples):
        transcript = self.recognizer.accept(samples)
        if transcript is None:
            return None
        normalized = re.sub(r"[^\w\u4e00-\u9fff]", "", transcript).lower()
        if any(alias.lower() in normalized for alias in self.aliases):
            return "芷春"
        return None

    def reset(self):
        self.recognizer.reset()


class SpeechFrameRouter:
    def __init__(
        self,
        keyword_detector,
        recognizer,
        on_wake: Callable[[], None],
        on_transcript: Callable[[str], None],
        on_no_speech: Callable[[], None] = lambda: None,
        max_listening_seconds=12.0,
    ):
        self.keyword_detector = keyword_detector
        self.recognizer = recognizer
        self.on_wake = on_wake
        self.on_transcript = on_transcript
        self.on_no_speech = on_no_speech
        self.max_listening_samples = int(max_listening_seconds * SAMPLE_RATE)
        self.paused = False
        self.listening = False
        self.listening_samples = 0

    def accept(self, samples):
        if self.paused:
            return
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        if not self.listening:
            if self.keyword_detector.accept(samples):
                self.recognizer.reset()
                self.listening = True
                self.listening_samples = 0
                self.on_wake()
            return

        self.listening_samples += len(samples)
        transcript = self.recognizer.accept(samples)
        if transcript is None and self.listening_samples < self.max_listening_samples:
            return
        if not transcript:
            self._cancel_listening()
            return
        if transcript:
            self.pause()
            self.on_transcript(transcript)

    def _cancel_listening(self):
        self.keyword_detector.reset()
        self.recognizer.reset()
        self.listening = False
        self.listening_samples = 0
        self.on_no_speech()

    def pause(self):
        self.paused = True

    def resume(self):
        self.keyword_detector.reset()
        self.recognizer.reset()
        self.listening = False
        self.listening_samples = 0
        self.paused = False


def create_sherpa_router(model_files, on_wake, on_transcript, on_no_speech=lambda: None):
    missing = model_files.missing()
    if missing:
        raise FileNotFoundError("、".join(missing))

    import sherpa_onnx

    recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
        tokens=str(model_files.asr_tokens),
        encoder=str(model_files.asr_encoder),
        decoder=str(model_files.asr_decoder),
        num_threads=2,
        enable_endpoint_detection=True,
        rule1_min_trailing_silence=1.8,
        rule2_min_trailing_silence=0.9,
        rule3_min_utterance_length=15.0,
        provider="cpu",
    )
    return SpeechFrameRouter(
        WakePhraseDetector(SherpaRecognizer(recognizer)),
        SherpaRecognizer(recognizer),
        on_wake,
        on_transcript,
        on_no_speech,
    )


class SpeechWorker:
    def __init__(self, router, max_queue=32):
        self.router = router
        self.queue = queue.Queue(maxsize=max_queue)
        self.thread = None
        self.accepting_audio = False
        self.dropped_frames = 0

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.accepting_audio = True
        self.thread = threading.Thread(
            target=self._run,
            name="zhichun-speech",
            daemon=True,
        )
        self.thread.start()

    def accept(self, samples):
        if not self.accepting_audio:
            return
        try:
            self.queue.put_nowait(("audio", np.asarray(samples).copy()))
        except queue.Full:
            self.dropped_frames += 1

    def pause(self):
        self.accepting_audio = False
        self._enqueue_command("pause")

    def resume(self):
        self._enqueue_command("resume")

    def _enqueue_command(self, command):
        while True:
            try:
                self.queue.put_nowait((command, None))
                return
            except queue.Full:
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except queue.Empty:
                    pass

    def _run(self):
        while True:
            command, payload = self.queue.get()
            try:
                if command == "stop":
                    return
                if command == "audio":
                    self.router.accept(payload)
                elif command == "pause":
                    self.router.pause()
                elif command == "resume":
                    self.router.resume()
                    self.accepting_audio = True
            finally:
                self.queue.task_done()

    def stop(self):
        self.accepting_audio = False
        if self.thread is None:
            return
        self._enqueue_command("stop")
        self.thread.join(timeout=2)
        self.thread = None


class MicrophoneStream:
    def __init__(self, speech_worker, block_size=1600, on_error=lambda message: None):
        self.speech_worker = speech_worker
        self.block_size = block_size
        self.on_error = on_error
        self.stream = None

    def start(self):
        import sounddevice as sd

        self.speech_worker.start()
        try:
            self.stream = sd.InputStream(
                channels=1,
                samplerate=SAMPLE_RATE,
                dtype="float32",
                blocksize=self.block_size,
                callback=self._callback,
            )
            self.stream.start()
        except Exception:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            self.speech_worker.stop()
            raise

    def _callback(self, indata, frames, time_info, status):
        del frames, time_info
        if status:
            self.on_error(str(status))
            return
        self.speech_worker.accept(indata)

    def stop(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.speech_worker.stop()
