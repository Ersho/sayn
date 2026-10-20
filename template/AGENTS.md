# Agent instructions

You are building a mobile app for the platform in vibe.json inside a fixed Expo project. Work autonomously and finish without asking questions.

## Project

- Expo (SDK version pinned in `package.json`) + TypeScript + expo-router. File-based routes live in `app/`.
- The project is built from this directory by an external pipeline: `tsc --noEmit` → `expo prebuild` → Gradle (Android) or Xcode (iOS). Never run native builds yourself; run the type check before finishing.
- `vibe.json` holds the app id, name and the user's request. Read it; never change it.

## Do not touch

- `android/` and `ios/` — generated, recreated by prebuild.
- `plugins/withVibeSigning.js`, existing plugin entries, `android.package`, `ios.bundleIdentifier`, and anything about signing. New app-specific config plugins may be added.
- `vibe.json`, `package-lock.json` by hand, `tsconfig.json`.
- Do not eject, do not add EAS config, do not switch package manager.

## Do edit

- `app/` (screens, layouts) and `src/` (components, hooks, storage, logic).
- `app.json`: platform permissions, iOS usage descriptions, display name, and Expo config plugins. Preserve package and bundle identifiers.
- `package.json`: only through `npx expo install <pkg>`. Expo SDK packages and well-known React Native libraries that `expo install` resolves are allowed. For native capabilities unavailable in existing libraries, local Expo modules under `modules/` and app-specific config plugins are allowed. Keep generated native projects disposable.

## Requirements

- For Android, declare every Android permission in `app.json` (`android.permissions` and plugin options) and request it at runtime before use.
- For iOS, declare privacy usage descriptions in `ios.infoPlist` and request the relevant permission before use. Native modules must support the chosen platform.
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
