# sayn — guide for agents and contributors

sayn (repo and workspace folder: `vibeapping`, internal prefix `vibe`) turns a one-paragraph description into a signed Android release APK or iOS app installed on the user's phone. A local dashboard sends the request to a FastAPI backend, the backend lets a coding agent (Codex CLI or Claude Code, the user picks per app) write an Expo app, builds it with Gradle or Xcode, and installs it with adb or Apple's device tools. Android builds run on Windows, macOS or Linux; iOS builds require macOS. The user's ChatGPT or Claude subscription powers the coding agent.

The file you are reading describes **this repository**. The file `template/AGENTS.md` is different: it is copied into every generated app and tells Codex how to behave inside that app. Do not merge the two.

## Layout

```
scripts/setup.ps1      one-shot, idempotent toolchain setup for Windows (run first on a new machine); setup.bat wraps it
scripts/setup.sh       the same for macOS / Linux; writes ~/vibeapping/env.sh (JAVA_HOME, ANDROID_HOME, PATH) that dev.sh sources
scripts/dev.ps1        starts backend (:8000) and dashboard (:5173) together; Ctrl+C stops both
scripts/dev.bat        same for CMD: opens each server in its own window
scripts/dev.sh         same for macOS / Linux
template/              Expo app that every generated app starts from
  app/                 one screen (index.tsx) + Stack layout
  plugins/withVibeSigning.js   config plugin: release build signs with the vibe keystore
  vibe.json            {id, name, request} — filled by the backend
  app.json             __VIBE_ID__ / __VIBE_NAME__ placeholders
  AGENTS.md            instructions for Codex inside a generated app
games/                 the game kit, added on top of the template for games only (games.add_kit)
  GAMES.md             instructions for the agent inside a game ({tester} is filled per app)
  metro.config.js      resolves `three` to its ES module build (its CommonJS build calls process.emitWarning, which Hermes lacks)
  plugins/withGlKeep.js   R8 keep rule for expo.modules.gl (release builds strip GLView's constructor otherwise)
  play.mjs             game tester: plays the web preview in headless Chromium and saves screenshots
  compare.mjs          puts a play screenshot next to a store screenshot in one image, for the agent's side-by-side check
backend/vibe/
  api.py               FastAPI routes (devices, apps, revise, answer, events SSE, deploy, permissions, screenshot)
  workspace.py         workspace paths, app creation from template, git commits, status/vibe files
  codex.py             the single `codex exec` command + the create/revise/fix prompts (shared by both agents)
  claude.py            the single `claude -p` command (same run() signature as codex.py)
  settings.py          Settings tab: agent sign-in checks (`codex login status`, `claude auth status`), API keys in keys.json (verified; no global on/off), the one key an app was allowed is written to its .env as EXPO_PUBLIC_* before the agent runs
  playstore.py         Play Store browsing (top charts, search, details) + the per-app inspiration/ folder (listing, screenshots, APK)
  games.py             game categories, "Turn on games" (skills download + game tester install), the game kit (pinned packages, app.json plugins, skills, GAMES.md); kit() says what is new on this computer
backend/playstore/     tiny Node CLI around google-play-scraper (playstore.mjs); playstore.py shells out to it
  build.py             tsc → expo prebuild → Gradle or Xcode, agent fix loop, revise, permissions
  ios.py               Xcode CLI device discovery, Apple team selection, setup checkpoints, devicectl / simctl install and launch
  devices.py           adbutils wrapper: list (+ phones.json history, + phones only the OS sees over USB = debugging off), install (+ XAPK splits), uninstall, launch, screenshot
  phone.py             standalone CLI the agent runs to see and drive the original app on the phone (look, tap, type, scroll, back, restart)
dashboard/             Vite + React + TypeScript single-page UI (src/App.tsx, src/index.css)
                       sidebar: My apps, Devices, Get inspired, Get inspired: games, New app, Settings
```

Runtime data lives outside the repo in `%USERPROFILE%\vibeapping\`:

```
apps/<id>/             one generated app = one git repo (template commit, then one commit per Codex run)
  vibe.json ({id, name, request, agent, ai?, online?, inspiration?, features?, ideas?}; ai = provider id or false, online = data service name), status.json, events.jsonl, codex-last.md / claude-last.md, screenshot.png
  inspiration/         only for "Get inspired" apps, git-excluded: listing.md/.json, screenshot-N.png, app.apk + splits/ (optional), spec.md (agent-written), screens/screen-NN.png (seen on the phone), phone.json (while exploring)
  references/          git-excluded: ref-N.png|jpg|webp|gif, the pictures attached to the latest create/revise request ("make it look like this"); replaced on every revise
  android/             generated by prebuild; app/build/outputs/apk/release/app-release.apk
  ios/                 generated by prebuild; build/Build/Products/Release-{iphoneos,iphonesimulator}/*.app
config.json            {keystore, alias, password, ios_team?} written by setup; team selected in Settings
phones.json            {serial: {model, first_seen, last_seen}}: every phone ever seen; GET /devices merges it in as state "offline"
vibe.jks               release keystore (alias "vibe", 10000-day validity)
tools/jadx-headless-mcp-0.7.1-all.jar   downloaded by setup.ps1; REA needs it for APK analysis (env REA_JADX_MCP_JAR)
tools/game-skills/     threejs-game-skills (MIT) at the commit pinned in games.py, downloaded from GitHub by "Turn on games" (.commit marks the version) → each game's .claude/skills/
tools/game-tester/     Playwright + headless Chromium (browsers/) + play.mjs and compare.mjs, installed by "Turn on games"
tools/game-kit.json    the game packages npm has downloaded once (so the dashboard stops calling them new)
cache/images/          Play Store icons and screenshots, fetched once via GET /inspire/image?u=&w= (Google rate-limits direct hotlinking)
```

## Stack and pinned versions

| Piece | Choice | Notes |
|---|---|---|
| Generated apps | Expo SDK 58 (`expo ~58.0.13`), React Native 0.88, React 19.3, TypeScript 6, expo-router 58 | `@react-native-async-storage/async-storage` is pre-installed so most apps never need `expo install` |
| Android | compileSdk/targetSdk 36, build-tools 36.0.0, Gradle 9.4.1 (wrapper), JDK 17 (Microsoft OpenJDK, per-user zip) | release builds only, `reactNativeArchitectures=arm64-v8a` |
| Native build | CMake **4.1.2** from the SDK, pointed to via `cmake.dir` in `android/local.properties` | the default 3.22.1 ships a ninja that ignores Windows long paths; react-native-worklets then fails |
| Coding agents | Codex CLI 0.145 (`codex exec`), model `gpt-5.6-sol`; Claude Code 2.1 (`claude -p`), CLI default model | config.toml's default Codex model is not available on ChatGPT plans; override with `VIBE_CODEX_MODEL` / `VIBE_CLAUDE_MODEL` |
| Backend | Python 3.12 via `uv`, FastAPI, uvicorn, adbutils 2.12, sse-starlette | `cd backend && uv run uvicorn vibe.api:app --port 8000` |
| Dashboard | Vite 8, React 19, TypeScript, no UI library | `cd dashboard && npm run dev` → http://localhost:5173 (CORS is limited to this origin) |
| Device | adb from the SDK platform-tools (37.x); the phone is a Pixel 11 Pro | adbutils for list/launch/screenshot, the `adb` binary for `install -r` (faster for 30 MB APKs) |
| Play Store | google-play-scraper 10.1.4 (npm, unofficial; breaks when Google changes markup) | `list` (top free per category), `search`, `app` (+ 40 helpful reviews); 24 h in-memory cache |
| Games | three 0.187.0, @react-three/fiber 9.8.2, expo-gl / expo-asset / expo-file-system / expo-audio / expo-haptics (SDK 58 ranges), @types/three; Playwright 1.64.1 | pinned in `games.py`; three and fiber were tested on Hermes, change them only with a phone test |
| APK analysis | REA (`rea-agents@6.7.0`, MCP server via `npx`) + jadx-headless-mcp 0.7.1 jar | APK comes from `d.apkpure.net/b/APK/<pkg>?version=latest` (plain APK or XAPK, the base APK is extracted) |

## How a request flows

1. `POST /apps {request, name?, agent, platform?, ios_target?, ios_device?, images?}` (`agent` is `codex` or `claude`; platform defaults to Android) → `workspace.create_app()` copies `template/` (without node_modules/android/ios), fills placeholders, writes `vibe.json` and `status.json`, `git init` + commit. The id is a slug of the name, else `app` + 6 hex. Responds immediately; the rest runs in a daemon thread.
   - `images`: up to 4 reference pictures as data URLs (PNG, JPEG, WebP or GIF, 8 MB each), from the dashboard's "Add a picture" control (choose, drop or paste). `api._save_references()` writes them to `references/ref-N.<ext>` and adds `references/` to `.git/info/exclude`. The **create** and **revise** prompts then get `codex.references_block()`: open the pictures, match their layout, colours and mood, never copy logos, brand names or text. The block is also logged as `prompt: ...` in the technical log. Codex gets the files attached with `-i` (its own image tool fails under the Windows sandbox), and Claude Code opens them with Read.
2. `build.pipeline()`:
   - `preparing`: copy `template/node_modules` into the app (seconds, instead of `npm ci`).
   - `checking`: where does the app's content come from? The agent answers `codex.AI_CHECK` (`AI: yes|no`, `PROVIDER`, `WHY`, `ONLINE: <free keyless data service>|none`) without editing files. AI counts as needed both for AI features and for writing the app's content on request (the "content gap": what the original keeps on its servers or behind premium). `ONLINE` is stored as `online` in `vibe.json` (a revision keeps it) and `codex.online_block()` allows only that service in the coding prompt. An app with `ai` already set in `vibe.json` (or whose code already reads a key) keeps that key. No AI: `ai: false`, and the prompt says no keys exist. Yes: status `waiting` with `question {why, provider}`, the job thread waits until `POST /apps/{id}/answer {use_ai}` (Use AI / Build without AI; Cancel works as usual). Then `settings.write_env()` writes that one key, or none.
   - Feature understanding (create only, same call): `codex.plan_ask()` adds `NAME` (a plain descriptive name like "Book Ideas", skipped when the user gave one), 5–8 `FEATURE` and 3–5 `EXTRA` lines; `codex.parse_plan()` reads them. The build does not wait for them. "Stop and review features" (`POST /apps/{id}/hold`, allowed until the code is written) pauses it in `reviewing` with `plan {name, features, extras}` in `status.json`; during `coding` it kills the agent and rolls back to the template commit first. `POST /apps/{id}/plan {name, features, extras}` resumes. The confirmed list goes into the create prompt (`codex.features_block()`) and into `vibe.json` as `features` (unpicked ones as `ideas`).
   - `coding`: the chosen agent's `run()` with the **create** prompt (the plan's name or a given name is passed in, otherwise the agent picks a plain one). The agent must end with `NAME: <name>`; the backend writes that name into `vibe.json` and `app.json`. Commit.
   - `building`: `build.build()` = `npx tsc --noEmit` → `npx expo prebuild --platform android --no-install` → write `local.properties` (sdk.dir, cmake.dir) and append `VIBE_KEYSTORE/ALIAS/PASSWORD` + `reactNativeArchitectures` to `gradle.properties` → `gradlew.bat assembleRelease`.
   - After prebuild, `build()` rewrites `app_name` in `android/.../res/values/strings.xml` to `my:<name>` so all generated apps are found by typing `my:` in the phone's app search. `app.json`, `vibe.json` and the dashboard keep the plain name.
   - For iOS, typecheck → `expo prebuild --platform ios --no-install` → set `CFBundleDisplayName` → `pod install` → `xcodebuild`. Physical builds use the configured Apple team; Simulator builds disable signing.
   - On failure: `fixing`, the agent gets the last 200 lines with the **fix** prompt, commit, rebuild. Up to 5 rounds.
   - `ready` (with `fix_rounds` and the summary paragraph) or `failed` (with the error tail).
3. Every line of Codex and Gradle output is appended to `events.jsonl`; `GET /apps/{id}/events` streams it as SSE and closes with an `end` event when the status is terminal.
4. `POST /apps/{id}/deploy {serial}` validates the build's platform and device type, then installs and launches through adb (Android), devicectl (iPhone/iPad), or simctl (Simulator). Android and Simulator deployments save `screenshot.png`; physical iOS deployment succeeds without a screenshot.
5. **Get inspired**: `GET /inspire` (categories, `apk_ready`), `/inspire/top/{category}`, `/inspire/search?q=`, `/inspire/app/{package}`. `POST /apps {request: notes, agent, inspiration: {app_id, apk, reviews}}` composes the request from the listing, then the pipeline adds an `inspiring` step after `preparing`: `playstore.save_inspiration()` writes `inspiration/` (listing + up to 6 screenshots, plus 40 reviews when `reviews` is true and the APK when `apk` is true), stores `{appId, title, icon, apk, reviews, installs, price, ads, iap}` in `vibe.json` (the last four are what the original charges; the inspire dialog and the app card show them as what the user saves), and the **create** prompt gets `codex.inspiration_block()` appended: build your own version, read the listing and screenshots, never copy name/branding/code. With the APK the coding agent also gets REA's MCP server (`run(..., mcp=True)`) and is told to write `inspiration/spec.md` first (API only; the dashboard keeps the first build quick and does not offer it). An APK download failure is logged and the job continues with the listing only.
   - **Make it closer to the original**: `POST /apps/{id}/closer` (inspired apps only; the dashboard link on a built app opens a warning that it takes a while and may need the user to sign in on the phone) runs `build.closer()`: `_job(..., study=True)` downloads the APK once (`playstore.ensure_apk()`), then `build._study()` runs before `checking`: **`studying`**, an agent run with REA (`mcp=True`) and web search (`web=True`) and the **study** prompt (`codex.STUDY`: listing, store screenshots, the user's reference pictures, the APK, Reddit/X/YouTube/help pages), writes `inspiration/spec.md` and ends with `MISSING:` lines. When something is missing and an Android phone is connected, status `waiting` with `question {kind: "explore", missing, device, installed, title}`. On yes: **`exploring`**, the original is installed (unless it already is; with the XAPK's splits, `adb install-multiple`) and launched, `inspiration/phone.json` names the phone, and the agent drives it with `phone.py` (`codex.EXPLORE`), saving `inspiration/screens/` and a "Seen on the phone" section in the spec. `phone.py` captures and taps only while the original's own window has focus (no Play billing dialogs, other apps or the lock screen) and refuses to type into password fields; the prompt forbids signing in, personal data, purchases and ads. An agent that hits a sign-in wall ends with `LOGIN: <what>`: `question {kind: "login", what}`, the user signs in on the phone themselves and continues (up to 2 times) or skips. Afterwards the app is uninstalled again if this step installed it. Every part is optional: a failure is logged and the build goes on. The check then also reads the spec, and the revision prompt `codex.closer_prompt()` builds from the spec and screens (`INSPIRE_SPEC`), or from the listing when the study failed. Version bump and commit `<agent>: closer to the original`. Mirroring the phone on the laptop (scrcpy) is a possible later addition, not part of this.
   - `POST /apps/{id}/answer {yes}` answers every question kind (`ai`, `explore`, `login`).
6. `POST /apps/{id}/revise {request, images?}` → same pipeline (`references/` is replaced by this request's pictures, or removed when there are none) with the **revise** prompt and the agent stored in `vibe.json`, patch version bump in `app.json`, commit `<agent>: revise: <request>`. The check runs on the change request too; an app that already uses AI keeps its key without asking, and a known data service is kept. Refused with 409 while the app is busy.
7. **Games** are opt-in. The dashboard's "Get inspired: games" page reads `GET /inspire/games` (`games.CATEGORIES`, `kit` = what games need, each part `ready` or new on this computer, `active`, `activation {running, step, error}`). While `active` is false the page shows only "Turn on games": the kit list and a button for `POST /games/activate`, which runs `games.turn_on()` in a thread (`ensure_skills()` downloads the pinned skills zip from codeload.github.com into `tools/game-skills`; `ensure_tester()` installs Playwright and the headless Chromium into `tools/game-tester`, about 300 MB); the page polls for progress. Nothing game-related is in the repo or downloaded before that. A game (`vibe.json` `game: true`, `POST /apps {..., game: true}`) gets **`equipping`** after `preparing` (status extra `installing` = the parts downloaded for the first time, shown under the step): it repeats `ensure_skills()` / `ensure_tester()` for anything missing (a tester failure is logged and the agent works without it), then `games.add_kit()` installs the pinned packages into the app (`npm install`), copies `metro.config.js`, `plugins/withGlKeep.js`, `tools/game-skills` (as `.claude/skills/`) and `GAMES.md`, adds the plugins (`expo-audio` without microphone, RECORD_AUDIO blocked) and git-excludes `artifacts/`; commit `sayn: game kit`, which a hold or cancel keeps. The check is `codex.GAME_CHECK` (name and 3 or 4 core features only, `codex.GAME_FEATURES`; games never get an AI key or data service, a revision of a game skips the check), the inspiration block is `INSPIRE_GAME` (same core loop and feel, own characters and art, no ads or paid currency), and the create, revise, closer and fix prompts get `codex.GAME` (read GAMES.md). GAMES.md sets the premium bar and the order of work (the target pictures, store screenshots or `references/`, define the type of game, camera, density, layout and palette; one level must look and play like them, checked side by side with `compare.mjs` for at least two rounds, before levels, upgrades or menus are added), tells the agent to follow the skills' director, adapt them to Expo (React Native HUD, WebGL2 only, no generators), keep startup under 2 s on Hermes, and play-test with `node <tester>/play.mjs http://localhost:<port> artifacts/play` against `npx expo start --web` (one port per app). Games take 30 to 60 minutes; the dialog says so.
8. `GET /apps` adds `ai_used` (provider labels whose `EXPO_PUBLIC_*_API_KEY` the app's code reads), shown as "Uses AI" on the card; `online` from `vibe.json` is shown as "Uses internet".

## Agent invocation (keep it in one place per agent: `backend/vibe/codex.py`, `backend/vibe/claude.py`)

```
codex exec -m gpt-5.6-sol -s workspace-write
  -c approval_policy=never -c sandbox_workspace_write.network_access=true
  --add-dir %USERPROFILE%\.expo --add-dir %LOCALAPPDATA%\npm-cache --add-dir %APPDATA%\npm
  --skip-git-repo-check --color never --json -o <app>/codex-last.md -C <app> -
```

- Prompt goes in on stdin. Output is JSONL (`thread.started`, `item.completed` with `command_execution` / `file_change` / `agent_message` / `reasoning`, `turn.completed` / `turn.failed`); `_summarize()` turns it into readable lines.
- The sandbox stays on. `--dangerously-bypass-approvals-and-sandbox` is not used. The three `--add-dir` entries exist because `npx expo install` writes to those caches and fails without them.
- Codex runs PowerShell commands on Windows; expect `powershell.exe -Command ...` in the logs.

Claude Code:

```
claude.cmd -p --output-format stream-json --verbose --permission-mode acceptEdits
  --allowedTools Bash PowerShell Edit Write Read Glob Grep [WebSearch WebFetch] [--model $VIBE_CLAUDE_MODEL]
```

- `web=True` (studying and exploring only) adds web search: Codex `-c web_search="live"` (what `codex --search` sets; `exec` has no flag), Claude `WebSearch WebFetch` in `--allowedTools`.
- Reference pictures go to Codex as `-i <file>` per image (only on the coding run, not the check or fix runs); `claude.run()` accepts the same `images` argument and ignores it, because the prompt names the files.
- With `mcp=True` (APK inspiration) both runners add REA: Codex via `-c mcp_servers.rea.command="cmd"` / `args=["/c","npx","-y","rea-agents@6.7.0","mcp"]` / `env={REA_JADX_MCP_JAR=...}`; Claude via `--mcp-config inspiration/mcp.json` plus `mcp__rea` in `--allowedTools`. The jar path is also exported in the subprocess environment.
- Prompt on stdin, output is stream-json (`system`, `assistant` with `text`/`tool_use` blocks, `user` with `tool_result`, final `result`). On Windows Claude Code's shell tool is called `PowerShell`, hence both names in `--allowedTools`. Both runners emit their lines under the SSE event name `codex`.

## Windows specifics that will bite you again

- `LongPathsEnabled=1` is required (HKLM registry, admin, one-time). `setup.ps1` checks it and tells the user the exact command; do not change system settings from code.
- Even with long paths on, CMake 3.22.1 fails. Always install `cmake;4.1.2` and write `cmake.dir`.
- PowerShell 5.1: `Tee-Object -FilePath` writes UTF-16; `Set-Content -Encoding utf8` adds a BOM (read JSON with `utf-8-sig`); native stderr under `$ErrorActionPreference='Stop'` throws, so `setup.ps1` routes such commands through `cmd /c`.
- The JDK is installed from the zip into `%LOCALAPPDATA%\Programs\Java` because the winget MSI needs a UAC prompt, which blocks unattended setup.
- sdkmanager licence prompts cannot be answered by piping `y` from PowerShell; `setup.ps1` writes the licence hash files instead and verifies packages by directory presence (sdkmanager exits 0 even when it skips).
- Phone screenshots are black when the phone is locked with a PIN. `wm dismiss-keyguard` only works without a secure lock.

## Build times on this laptop

| Build | Time |
|---|---|
| Template, first ever (4 ABIs, Gradle download) | 10 min 20 s |
| Template, warm | 58 s |
| Generated app, arm64 only, warm Gradle cache | 5 to 6.5 min |
| APK size, arm64 only | ~31 MB |

## Conventions

- Minimal, readable code. No abstraction for things that exist once. No tests beyond "it builds and installs", no CI, no Docker.
- The dashboard is for non-technical users: plain-language status labels, descriptions, versions, install state. Technical logs stay behind a toggle.
- Don't add features from the broader design that are outside the prototype (runtime AI keys, wireless pairing, modules, multi-device UI beyond a dropdown).
- Anything that changes how an agent is called belongs in `codex.py` / `claude.py`; prompts live in `codex.py` and are shared. Anything that changes the build belongs in `build.py` and, if it affects generated projects, in `template/`.
- Re-run `scripts/setup.ps1` / `scripts/setup.sh` after changing toolchain requirements; both must stay idempotent and in sync.
- Platform switches (`npx.cmd`, `claude.cmd`, `gradlew.bat`, `adb.exe`, `cmd /c npx` for MCP configs) hang off `os.name == "nt"` in the module that uses them; keep Linux working when touching them.

## macOS specifics

- `setup.sh` and `dev.sh` must work with the bundled Bash 3.2 (no `wait -n`).
- Microsoft JDK tarballs on macOS use `jdk-17*/Contents/Home`; use the native arm64 or x64 archive. The SDK defaults to `~/Library/Android/sdk`.
- Android native build tools need Rosetta 2 on Apple silicon; setup checks for it and prints the install command. No Homebrew or Android Studio dependency.

## iOS and host portability

- App metadata defaults to `platform="android"` for old apps. New iOS apps also record `ios_target` (`device` or `simulator`) and an optional build destination identifier. Device and Simulator artifacts must not be mixed.
- iOS builds require macOS, full Xcode selected with xcode-select, and CocoaPods on PATH. `VIBE_IOS_TEAM` or `config.json`'s `ios_team` provides a user-selected team; never hardcode a contributor's team or device IDs.
- `ios.checks()` is the single list of iPhone setup checkpoints (Xcode, CocoaPods, Apple account, team, connected, trusted, Developer Mode). `setup.sh` prints it with `python -m vibe.ios`, and the dashboard shows it through `GET /settings/ios/checks`. Add or reword steps there only. Read Xcode accounts and teams through macOS `defaults export`, so a launcher's overridden HOME does not hide them. A manually supplied signing team is not evidence of an Xcode account. The user still saves a team; `ios.ready()` (Xcode + CocoaPods) gates the iPhone option.
- On macOS, Android is optional: `setup.sh --no-android`, or a missing Rosetta on Apple silicon, skips the Android SDK. `/settings` reports `android` and the dashboard disables that option.
- Build optimized local `.app` bundles using Apple development signing for physical devices, and unsigned Simulator bundles. The pipeline uses `devicectl` JSON files and `simctl` for deployment. Physical screenshots are not provided by devicectl.
- Keep Node requirements in `scripts/check-node.mjs`, README, and package metadata consistent with the pinned Expo / React Native versions. Explicitly install development dependencies: Vite and TypeScript are required at runtime by this build tool.
- Resolve symlinked npm / Expo cache paths before passing them as writable directories to Codex. Keep its workspace sandbox enabled.
