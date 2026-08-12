# Desktop Conversation History Design

## Goal

Make saved desktop conversations visible after the macOS app restarts without changing the current immersive layout. The history panel remains collapsed at startup, while the latest assistant reply is visible on the main stage.

## Current Behavior

The `desktop` session is persisted in SQLite, but `DesktopRuntime` never reads those messages when it creates `MainWindow`. The history panel therefore starts empty even when the database contains prior user and assistant messages.

## Selected Approach

Load the complete `desktop` session once during desktop startup and populate the existing message list in chronological order.

- Keep the history panel collapsed by default.
- Show the latest assistant message through the existing subtitle behavior.
- Show the full loaded conversation when the user expands the history panel.
- Ignore persisted entries that have no displayable text.
- If history loading fails, continue opening the desktop app with an empty history instead of preventing startup.

This uses the existing `history_store.load_messages` and `MainWindow.add_message` paths. It does not add a second history model, change the database schema, or alter chat, speech recognition, or text-to-speech behavior.

## Data Flow

1. `DesktopRuntime` creates `MainWindow`.
2. Startup reads messages for the existing `desktop` session.
3. Displayable user, assistant, and system text is passed to the window in stored order.
4. `MainWindow` adds each message to the hidden history panel.
5. Assistant messages update the main subtitle, leaving the newest assistant reply visible after loading completes.

New messages continue through `DesktopController` and are appended using the same `MainWindow.add_message` method.

## Error Handling

History is optional startup state. A database read failure must not block the application window, microphone setup, or new conversations. The runtime catches the history-loading error and leaves the history panel empty.

## Testing

Add focused regression coverage proving that:

- the history panel remains collapsed after startup population;
- persisted messages are rendered in chronological order when the panel is expanded;
- the latest assistant reply is shown on the main stage;
- non-displayable records are skipped;
- a history-loading failure does not prevent runtime initialization.

Run the complete `unittest` suite after the focused tests pass, then rebuild the macOS application and verify the packaged app against the existing persisted `desktop` conversation.

## Out of Scope

- Changing the default collapsed layout.
- Adding history deletion or session selection.
- Changing the SQLite schema.
- Modifying the agent response, wake-word, transcription, synthesis, or audio playback flows.
