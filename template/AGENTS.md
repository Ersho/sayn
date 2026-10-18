# Agent instructions

You are building an Android app inside a fixed Expo project. Work autonomously and finish without asking questions.

## Project

- Expo (SDK version pinned in `package.json`) + TypeScript + expo-router. File-based routes live in `app/`.
- The project is built from this directory by an external pipeline: `tsc --noEmit` → `expo prebuild` → `gradlew assembleRelease`. You never run those.
- `vibe.json` holds the app id, name and the user's request. Read it; never change it.

## Do not touch

- `android/` — generated, wiped on every build.
- `plugins/`, the `plugins` and `android.package` entries in `app.json`, and anything about signing.
- `vibe.json`, `package-lock.json` by hand, `tsconfig.json`.
- Do not eject, do not add `ios/`, do not add EAS config, do not switch package manager.

## Do edit

- `app/` (screens, layouts) and `src/` (components, hooks, storage, logic).
- `app.json`: Android permissions and Expo config plugins only.
- `package.json`: only through `npx expo install <pkg>`. Expo SDK packages and well-known React Native libraries that `expo install` resolves are allowed. Nothing requiring custom native code outside config plugins.

## Requirements

- Declare every Android permission in `app.json` (`android.permissions` and plugin options) and request it at runtime before use.
- The app must work fully offline unless the request is explicitly an AI or online app. Persist data locally (`@react-native-async-storage/async-storage` or `expo-sqlite`).
- Keep the UI simple and usable: readable text, sensible padding, respects safe areas.
- The dashboard also runs the app in a browser (react-native-web) as a preview before install. Keep screens working there: guard native-only modules with `Platform.OS !== "web"` instead of crashing.
- No placeholder screens. Implement what was asked, end to end.

## API keys

If the task prompt lists API key variables, they are in `.env` (never commit or print it) and readable as `process.env.EXPO_PUBLIC_...`. Use them only for requests that need that provider. Never write a key into source files.

## Before you finish

1. `npx tsc --noEmit` passes with zero errors.
2. Every file you created is imported or is a route.
3. Write one short paragraph summarizing what the app does. Nothing else.

## When given a build error

Fix the cause (not the symptom), run `npx tsc --noEmit` again, and finish. Do not ask for clarification.
