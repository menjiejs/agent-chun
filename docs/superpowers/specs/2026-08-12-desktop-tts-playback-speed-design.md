# Desktop TTS Playback Speed Design

## Goal

Make the desktop app speak at 1.5x playback speed while leaving generated TTS audio bytes and the `/tts` API unchanged.

## Selected Approach

Use local playback-rate adjustment in `app/audio_output.py`.

`decode_wav(audio)` continues to return the original samples and sample rate. `play_wav(audio)` plays those same samples with an effective sample rate of `sample_rate * 1.5`, so the desktop app speaks faster without changing the TTS request, the returned WAV file, or server API behavior.

## Scope

- Change desktop voice playback only.
- Keep the TTS client request payload unchanged.
- Keep `/tts` endpoint output unchanged.
- Do not add user-facing speed controls.
- Do not introduce new audio processing dependencies.

## Components

- `app/audio_output.py`: define `DESKTOP_TTS_PLAYBACK_RATE = 1.5`; use it when calling `sounddevice.play`.
- `tests/test_audio_output.py`: add a test that patches `sounddevice`, calls `play_wav`, and verifies the playback sample rate is multiplied by 1.5.

## Error Handling

No new error path is needed. Existing WAV decoding errors and `sounddevice` playback errors keep their current behavior.

## Testing

- Add a focused unit test for `play_wav` that verifies a 16 kHz WAV is played at 32 kHz.
- Run `./venv/bin/python -m unittest tests.test_audio_output -v`.
- Run `./venv/bin/python -m unittest discover -s tests -v`.

## Acceptance Criteria

- Desktop spoken replies play at 1.5x speed.
- `/tts` still returns the original generated WAV bytes.
- Existing audio decoding behavior is unchanged.
- Full test suite passes.
