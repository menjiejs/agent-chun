import io
import wave

import numpy as np


DESKTOP_TTS_PLAYBACK_RATE = 1.5


def decode_wav(audio):
    with wave.open(io.BytesIO(audio), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise ValueError("only 16-bit PCM WAV audio is supported")
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())

    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels)
    return samples, sample_rate


def play_wav(audio):
    import sounddevice as sd

    samples, sample_rate = decode_wav(audio)
    sd.play(samples, int(sample_rate * DESKTOP_TTS_PLAYBACK_RATE))
    sd.wait()
