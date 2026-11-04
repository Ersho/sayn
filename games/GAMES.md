# Game instructions

This app is a game. Everything in AGENTS.md still applies, except its "Content and data" and "API keys" sections: a game runs fully offline, uses no AI key and no online service, and builds every model, texture, sound and level in code.

## The bar, and the order of work

The bar is premium: a polished game a player would keep, not a prototype. Primitive shapes, empty scenes and plain text labels are placeholders, not the result.

When the game is modelled on a Play Store game (store screenshots in `inspiration/`) or the user attached pictures (`references/`), those pictures are the target. Work in this order:
1. Look at every target picture and write down what defines it: the genre and core loop, the camera (angle, height, how much of the screen the action fills), the scale and density (how many units, how big on screen), the layout (lanes, gates, obstacles, pickups, bosses), the colour palette and lighting, the effects, and where the HUD sits.
2. Build one level that looks and plays like those pictures. Same type of game, same camera, same density and same mood, with your own characters, art and name.
3. Compare it side by side with the pictures (see Play-testing) and fix the differences. Repeat until a player would call it the same kind of game.
4. Only then add more: levels, upgrades, unlocks, menus. Breadth never comes before the core scene looks right.

Without target pictures, decide the look yourself first (genre, camera, palette, density) and hold every screen to it.

## Already installed

- 3D: `three` and `@react-three/fiber` (render with `<Canvas>` from `@react-three/fiber`) on `expo-gl`; `expo-asset` and `expo-file-system`.
- Sound and vibration: `expo-audio`, `expo-haptics`.
- `metro.config.js` and `plugins/withGlKeep.js`: they make three.js load on the phone. Never remove or change them.

2D games may skip three.js and use plain React Native views and `react-native-reanimated` instead. Add other packages only with `npx expo install` and only when the game really needs them.

## Skills

Game-development skills are in `.claude/skills/`. Read `.claude/skills/threejs-game-director/SKILL.md` first and follow it at the premium bar, loading the sibling skills it routes to (gameplay systems, AAA graphics, game UI, debug and profiling, QA) and their references. Score the result with the visual scorecard in `threejs-aaa-graphics-builder/references/visual-scorecard.md`: no category below 2, an average of at least 2.3.

The skills were written for Vite browser games. In this project:
- Do not create a Vite project, do not use the skills' scaffold, and do not run native builds.
- Skip the credential probe and the 3D, image and audio generators: no API keys exist. Build models, textures and effects procedurally.
- Do not use DOM or HTML overlays: HUD and menus are React Native views over the canvas. No WebGPU or TSL: the phone renders WebGL2 through expo-gl. One shadow-casting light at most, instancing for repeated objects, few draw calls, no heavy full-screen post-processing.
- Text in the 3D scene (gate values, counters, labels) must read correctly from the camera: never mirrored or upside down. Check it in the screenshots.

## The phone is not the browser

The game ships as an Android release build that runs on Hermes, a JavaScript engine without a JIT. It is much slower than a browser for per-pixel work:
- The game must be visible within 2 seconds of opening. Do not compute textures, text atlases or distance fields pixel by pixel in JavaScript at startup; keep generated textures small (256 px or less), draw shapes with geometry instead, or build them lazily after the first frame.
- Do not rely on browser APIs (`document`, `window`, `OffscreenCanvas`, `AudioContext`, `Image`); guard web-only code with `Platform.OS === "web"`.
- Pause the game loop when the app goes to the background (`AppState`).
- Save progress (level, best score, unlocks, settings) with AsyncStorage.

## Play-testing

{tester}
