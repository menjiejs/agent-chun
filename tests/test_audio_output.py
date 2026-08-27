import io
import types
import unittest
import wave
from unittest.mock import patch

import numpy as np

from app.audio_output import decode_wav, play_wav


class AudioOutputTest(unittest.TestCase):
    def _pcm16_wav(self, sample_rate=16000):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(np.array([-32768, 0, 32767], dtype="<i2").tobytes())
        return buffer.getvalue()

    def test_decodes_pcm16_wav_without_writing_a_file(self):
        samples, sample_rate = decode_wav(self._pcm16_wav())

        self.assertEqual(sample_rate, 16000)
        np.testing.assert_allclose(samples, [-1.0, 0.0, 32767 / 32768])

    def test_play_wav_uses_configured_playback_sample_rate(self):
        calls = []
        fake_sounddevice = types.SimpleNamespace(
            play=lambda samples, sample_rate: calls.append((samples, sample_rate)),
            wait=lambda: calls.append("wait"),
        )

        with patch.dict("sys.modules", {"sounddevice": fake_sounddevice}):
            play_wav(self._pcm16_wav(sample_rate=16000))

        played_samples, played_sample_rate = calls[0]
        np.testing.assert_allclose(played_samples, [-1.0, 0.0, 32767 / 32768])
        self.assertEqual(played_sample_rate, 24000)
        self.assertEqual(calls[1], "wait")


if __name__ == "__main__":
    unittest.main()
