import tempfile
import threading
import unittest
from pathlib import Path

import numpy as np

from app.offline_speech import (
    ModelFiles,
    SpeechFrameRouter,
    SpeechWorker,
    WakePhraseDetector,
)


class FakeKeywordDetector:
    def __init__(self, results):
        self.results = iter(results)

    def accept(self, samples):
        return next(self.results, None)

    def reset(self):
        pass


class FakeRecognizer:
    def __init__(self, results):
        self.results = iter(results)

    def accept(self, samples):
        return next(self.results, None)

    def reset(self):
        pass


class OfflineSpeechTest(unittest.TestCase):
    def test_model_files_reports_missing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            model_files = ModelFiles.from_root(Path(directory))

            missing = model_files.missing()

        self.assertIn("中文识别模型", missing)

    def test_wake_phrase_accepts_common_homophone_transcription(self):
        detector = WakePhraseDetector(FakeRecognizer(["我是指春", "普通聊天"]))

        result = detector.accept(np.zeros(1600, dtype=np.float32))

        self.assertEqual(result, "芷春")

    def test_router_ignores_audio_while_paused(self):
        events = []
        router = SpeechFrameRouter(
            FakeKeywordDetector(["芷春"]),
            FakeRecognizer(["你好"]),
            on_wake=lambda: events.append("wake"),
            on_transcript=lambda text: events.append(text),
        )
        router.pause()

        router.accept(np.zeros(1600, dtype=np.float32))

        self.assertEqual(events, [])

    def test_router_switches_from_keyword_to_transcription(self):
        events = []
        router = SpeechFrameRouter(
            FakeKeywordDetector(["芷春"]),
            FakeRecognizer([None, "你好，芷春"]),
            on_wake=lambda: events.append("wake"),
            on_transcript=lambda text: events.append(text),
        )
        samples = np.zeros(1600, dtype=np.float32)

        router.accept(samples)
        router.accept(samples)
        router.accept(samples)

        self.assertEqual(events, ["wake", "你好，芷春"])
        self.assertTrue(router.paused)

    def test_empty_endpoint_returns_to_keyword_waiting(self):
        events = []
        router = SpeechFrameRouter(
            FakeKeywordDetector(["芷春"]),
            FakeRecognizer([""]),
            on_wake=lambda: events.append("wake"),
            on_transcript=lambda text: events.append(text),
            on_no_speech=lambda: events.append("no-speech"),
        )
        samples = np.zeros(1600, dtype=np.float32)

        router.accept(samples)
        router.accept(samples)

        self.assertEqual(events, ["wake", "no-speech"])
        self.assertFalse(router.listening)
        self.assertFalse(router.paused)

    def test_listening_timeout_requires_a_new_wake_phrase(self):
        events = []
        router = SpeechFrameRouter(
            FakeKeywordDetector(["芷春"]),
            FakeRecognizer([None]),
            on_wake=lambda: events.append("wake"),
            on_transcript=lambda text: events.append(text),
            on_no_speech=lambda: events.append("timeout"),
            max_listening_seconds=0.05,
        )
        samples = np.zeros(1600, dtype=np.float32)

        router.accept(samples)
        router.accept(samples)

        self.assertEqual(events, ["wake", "timeout"])
        self.assertFalse(router.listening)

    def test_speech_worker_runs_decoder_off_caller_thread(self):
        caller_thread = threading.get_ident()
        decoded_on = []
        decoded = threading.Event()

        class RecordingRouter:
            def accept(self, samples):
                decoded_on.append(threading.get_ident())
                decoded.set()

            def pause(self):
                pass

            def resume(self):
                pass

        worker = SpeechWorker(RecordingRouter())
        worker.start()
        try:
            worker.accept(np.zeros(1600, dtype=np.float32))
            self.assertTrue(decoded.wait(1))
        finally:
            worker.stop()

        self.assertNotEqual(decoded_on, [caller_thread])


if __name__ == "__main__":
    unittest.main()
