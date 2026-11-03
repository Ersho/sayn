# Game instructions

This app is a game. Everything in AGENTS.md still applies, except its "Content and data" and "API keys" sections: a game runs fully offline, uses no AI key and no online service, and builds every model, texture, sound and level in code.

## Already installed

- 3D: `three` and `@react-three/fiber` (render with `<Canvas>` from `@react-three/fiber`) on `expo-gl`; `expo-asset` and `expo-file-system`.
- Sound and vibration: `expo-audio`, `expo-haptics`.
- `metro.config.js` and `plugins/withGlKeep.js`: they make three.js load on the phone. Never remove or change them.

2D games may skip three.js and use plain React Native views and `react-native-reanimated` instead. Add other packages only with `npx expo install` and only when the game really needs them.

## Skills

Game-development skills are in `.claude/skills/`. Read `.claude/skills/threejs-game-director/SKILL.md` first and follow it, loading the sibling skills it routes to (gameplay systems, AAA graphics, game UI, debug and profiling, QA) and their references. The bar is a polished game a player would keep: an authored look, game feel (feedback on every action, camera motion, effects), clear HUD and menus, and a satisfying difficulty curve.

The skills were written for Vite browser games. In this project:
- Do not create a Vite project, do not use the skills' scaffold, and do not run native builds.
- Skip the credential probe and the 3D, image and audio generators: no API keys exist. Build models, textures and effects procedurally.
- Do not use DOM or HTML overlays: HUD and menus are React Native views over the canvas. No WebGPU or TSL: the phone renders WebGL2 through expo-gl. One shadow-casting light at most, instancing for repeated objects, few draw calls, no heavy full-screen post-processing.

## The phone is not the browser

The game ships as an Android release build that runs on Hermes, a JavaScript engine without a JIT. It is much slower than a browser for per-pixel work:
- The game must be visible within 2 seconds of opening. Do not compute textures, text atlases or distance fields pixel by pixel in JavaScript at startup; keep generated textures small (256 px or less), draw shapes with geometry instead, or build them lazily after the first frame.
- Do not rely on browser APIs (`document`, `window`, `OffscreenCanvas`, `AudioContext`, `Image`); guard web-only code with `Platform.OS === "web"`.
- Pause the game loop when the app goes to the background (`AppState`).
- Save progress (level, best score, unlocks, settings) with AsyncStorage.

## Play-testing

{tester}
