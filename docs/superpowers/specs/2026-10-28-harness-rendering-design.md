# Harness rendering design - 28 October 2026

## Intent

Make the existing composer smoother during typing, command-menu movement and terminal resizing.
Keep the current layout, commands, tools and safety boundaries.

## Goals

- Read Windows console key and resize events without 50-millisecond polling.
- Wrap each frame in synchronized-output markers where the terminal supports them.
- Redraw only changed rows when the terminal width and frame height stay stable.
- Retain the full reflow-safe redraw after a resize or frame-height change.
- Keep scripted input and existing editor key behavior unchanged.

## Non-goals

- Do not add a terminal library or rewrite the harness in Rust.
- Do not change model selection, engine runs, sessions, tools or permissions.
- Do not claim smooth physical rendering from unit tests alone.

## Approaches

1. Use native Windows console events and targeted ANSI updates.
   This keeps the standard-library implementation and changes one existing module.
   It needs careful tests for key mappings, resize events and cursor restoration.
2. Adopt a terminal user-interface library.
   This supplies rendering primitives but adds a dependency and replaces working input code.
   It is too broad for this repair.

Use approach 1. It addresses the measured causes without changing the harness architecture.

## Implementation boundaries

Add a small Windows input adapter in `src/compertum/harness/editor.py`.
Return the existing key strings to `LineEditor`. Return an empty string for resize and ignored events.
Keep the current polling function as a fallback if native console events are unavailable.

Batch each frame in one output write. Use synchronized-output mode 2026 around each update.
For a stable frame, move to changed logical rows, erase those rows and write their replacements.
Always restore the input cursor. Clear removed menu rows when the frame shrinks.

Add regression tests in `tests/test_harness_editor.py` for event translation, atomic output, partial redraws and full resize redraws.
Run the complete product-environment harness lane and the native AppContainer lane.
The owner then checks typing, menu movement and rapid resizing in Windows Terminal.
