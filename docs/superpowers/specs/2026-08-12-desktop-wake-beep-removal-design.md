# Desktop Wake Beep Removal Design

## Goal

Remove the short system beep that plays when the desktop app wakes and starts listening.

## Selected Approach

Stop calling the injected `beep` callback in `DesktopController.handle_wake()`.

The wake flow still transitions the voice session from waiting to listening and keeps the visible status text `正在聆听…`. Only the audible confirmation is removed.

## Scope

- Remove the wake-start beep only.
- Keep the visual listening status unchanged.
- Keep text chat, TTS playback, microphone routing, and speech recognition behavior unchanged.
- Do not add a user-facing sound setting.

## Components

- `app/desktop_controller.py`: remove the `self.beep()` call from `handle_wake()`.
- `tests/test_desktop_controller.py`: add a focused test proving wake does not call the injected beep callback while still entering listening state and showing `正在聆听…`.

## Testing

- Run the new focused desktop-controller test and verify it fails before the implementation change.
- Run `./venv/bin/python -m unittest tests.test_desktop_controller -v`.
- Run `./venv/bin/python -m unittest discover -s tests -v`.
- Rebuild `dist/芷春.app`.

## Acceptance Criteria

- Saying the wake phrase no longer plays a system beep.
- The app still shows `正在聆听…` after waking.
- Voice conversation flow still works.
