# UI Instructions

## Applies To

All files below `src/ui/`.

## Required Practices

- Treat UI as a view: request game-state changes with commands or events.
- Route every user-facing string through the localization system.
- Support keyboard/mouse and gamepad input for every interactive element.
- Make animations skippable and respect motion/accessibility preferences.
- Trigger UI sounds through the audio event system.
- Keep UI work off the game thread when it can block.
- Provide scalable text and colorblind modes.

## Forbidden Practices

- Do not let UI own or directly modify game state.
- Do not hardcode user-facing text or trigger audio implementations directly.
- Do not block the game thread or make accessibility support optional.

## Verification

Test every screen with keyboard/mouse and gamepad, localization, motion reduction, scalable text, colorblind modes, and minimum and maximum supported resolutions.
