# Desktop Qt Task Lifetime Design

## Goal

Prevent the desktop app from crashing after background work completes.

## Root Cause

`QtScheduler.__call__()` creates a `Task(QRunnable)` and starts it through `QThreadPool`, but no Python owner keeps the task alive after `__call__()` returns. The Qt thread pool and queued PySide signals can still reference that object after the Python wrapper becomes collectable, which can produce native `EXC_BAD_ACCESS` crashes in Shiboken/PySide event handling.

Crash reports show repeated `SIGSEGV` failures on the main thread in `QObjectWrapper::event`, `Sbk_QObject_getattro`, and `Shiboken::Conversions::cppPointer`, immediately after TTS work completes.

## Selected Approach

Have `QtScheduler` retain every scheduled `Task` in a private set until the task emits either `success` or `error`. Remove the task from the set only after the corresponding callback has run.

## Scope

- Keep the existing `QtScheduler(work, on_success, on_error)` interface.
- Keep task execution on `QThreadPool`.
- Keep success and error callback behavior unchanged.
- Do not change TTS, audio playback, microphone routing, or UI behavior.

## Testing

- Add unit tests that use a fake pool which captures the `Task` instead of running it.
- Verify the scheduler retains the task immediately after scheduling.
- Verify the scheduler releases the task after `success` emits.
- Verify the scheduler releases the task after `error` emits.

## Acceptance Criteria

- Background tasks stay alive until completion callbacks run.
- Completion callbacks still receive the original result or error.
- Full test suite passes.
