# Desktop TTS Playback Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make desktop spoken replies play at 1.5x speed without changing generated TTS audio bytes or the `/tts` API.

**Architecture:** Keep WAV decoding unchanged. Apply the speed change only at the `sounddevice.play` boundary by multiplying the decoded WAV sample rate by a fixed desktop playback-rate constant.

**Tech Stack:** Python, `wave`, `numpy`, `sounddevice`, `unittest`.

## Global Constraints

- Make the desktop app speak at 1.5x playback speed while leaving generated TTS audio bytes and the `/tts` API unchanged.
- `decode_wav(audio)` continues to return the original samples and sample rate.
- `play_wav(audio)` plays those same samples with an effective sample rate of `sample_rate * 1.5`.
- Change desktop voice playback only.
- Keep the TTS client request payload unchanged.
- Keep `/tts` endpoint output unchanged.
- Do not add user-facing speed controls.
- Do not introduce new audio processing dependencies.
- Existing WAV decoding errors and `sounddevice` playback errors keep their current behavior.

---

## File Structure

- Modify `app/audio_output.py`: add `DESKTOP_TTS_PLAYBACK_RATE = 1.5`; use it when calling `sounddevice.play`.
- Modify `tests/test_audio_output.py`: import `play_wav`; patch `sounddevice` in `sys.modules`; verify a 16 kHz WAV is played at 24 kHz while decoded sample data stays intact.

### Task 1: Double Desktop TTS Playback Rate

**Files:**
- Modify: `app/audio_output.py`
- Modify: `tests/test_audio_output.py`

**Interfaces:**
- Consumes: `decode_wav(audio: bytes) -> tuple[numpy.ndarray, int]`
- Produces: `DESKTOP_TTS_PLAYBACK_RATE = 1.5`
- Produces: `play_wav(audio: bytes) -> None`, which calls `sounddevice.play(samples, int(sample_rate * DESKTOP_TTS_PLAYBACK_RATE))`

- [ ] **Step 1: Write the failing test**

Add `import types` and `from unittest.mock import patch` to `tests/test_audio_output.py`.

Change the import from:

```python
from app.audio_output import decode_wav
```

to:

```python
from app.audio_output import decode_wav, play_wav
```

Add this helper method inside `AudioOutputTest`:

```python
    def _pcm16_wav(self, sample_rate=16000):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(np.array([-32768, 0, 32767], dtype="<i2").tobytes())
        return buffer.getvalue()
```

Refactor `test_decodes_pcm16_wav_without_writing_a_file` to use the helper:

```python
    def test_decodes_pcm16_wav_without_writing_a_file(self):
        samples, sample_rate = decode_wav(self._pcm16_wav())

        self.assertEqual(sample_rate, 16000)
        np.testing.assert_allclose(samples, [-1.0, 0.0, 32767 / 32768])
```

Add this test:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m unittest tests.test_audio_output.AudioOutputTest.test_play_wav_uses_configured_playback_sample_rate -v`

Expected: FAIL with `AssertionError: 32000 != 24000` if the previous 2.0x implementation is still active, proving playback must be reduced to 1.5x.

- [ ] **Step 3: Write minimal implementation**

Change `app/audio_output.py` from:

```python
def play_wav(audio):
    import sounddevice as sd

    samples, sample_rate = decode_wav(audio)
    sd.play(samples, sample_rate)
    sd.wait()
```

to:

```python
DESKTOP_TTS_PLAYBACK_RATE = 1.5


def play_wav(audio):
    import sounddevice as sd

    samples, sample_rate = decode_wav(audio)
    sd.play(samples, int(sample_rate * DESKTOP_TTS_PLAYBACK_RATE))
    sd.wait()
```

- [ ] **Step 4: Run focused tests**

Run: `./venv/bin/python -m unittest tests.test_audio_output -v`

Expected: PASS with both audio-output tests passing.

- [ ] **Step 5: Run full test suite**

Run: `./venv/bin/python -m unittest discover -s tests -v`

Expected: PASS. Existing non-failing warnings may still appear, but there must be no failures or errors.

- [ ] **Step 6: Rebuild packaged app**

Run: `./venv/bin/pyinstaller --clean --noconfirm Zhichun.spec`

Expected: PASS and `dist/芷春.app` refreshed.

## Self-Review

- Spec coverage: The plan covers local desktop playback speed, keeps `decode_wav`, TTS request payload, and `/tts` output unchanged, and avoids new dependencies or user-facing controls.
- Placeholder scan: The plan contains no open placeholders.
- Type consistency: `DESKTOP_TTS_PLAYBACK_RATE` is a `float`, and `sounddevice.play` receives an integer effective sample rate.
