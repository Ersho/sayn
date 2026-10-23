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
- Persist data locally (`@react-native-async-storage/async-storage` or `expo-sqlite`). The app works without internet, except for the AI keys and the online data service the task prompt names, and even then everything already saved stays usable offline.
- Keep the UI simple and usable: readable text, sensible padding, respects safe areas.
- The dashboard also runs the app in a browser (react-native-web) as a preview before install. Keep screens working there: guard native-only modules with `Platform.OS !== "web"` instead of crashing.
- No placeholder screens. Implement what was asked, end to end.

## Content and data

Before you build, work out where the app's content comes from. An app whose value is content (book summaries, lessons, exercises, recipes, workout plans, a food or product database) must not stop at a small fixed list you wrote in the code. Fill it from these sources, in this order:

1. **Facts that must be true** (nutrition values, barcodes, book titles and covers, places, prices): the online data service named in the task prompt, if there is one, or what the user enters.
2. **Written content** (summaries, explanations, lessons, exercises, plans, stories, feedback): the user's AI key, if the task prompt lists one. Write it when the user asks (for example "Add a book", "More exercises"), save it on the phone, reuse it instead of asking again, mark it as written by AI, and let the user regenerate it.
3. **The user's own input**: let them add and edit their own items.

Ship a small built-in starter set so the app is useful on first open and offline, but treat it as the floor, not the whole app: the user must be able to get new content inside the app, without a new build. Never let AI invent facts or numbers that must be true, such as nutrition values, prices, doses or dates. Never show made-up data as if it were real. When an online request fails, say so plainly and keep everything saved usable.

## API keys

If the task prompt lists API key variables, they are in `.env` (never commit or print it) and readable as `process.env.EXPO_PUBLIC_...`. Never write a key into source files.

## Before you finish

1. `npx tsc --noEmit` passes with zero errors.
2. Every file you created is imported or is a route.
3. Write one short paragraph summarizing what the app does. Nothing else.

## When given a build error

Fix the cause (not the symptom), run `npx tsc --noEmit` again, and finish. Do not ask for clarification.
