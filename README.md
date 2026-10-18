# vibeApping

**Describe an app in a paragraph. Get it installed on your Android phone a few minutes later.**

vibeApping is a local app factory. You type what you want into a small dashboard, a coding agent
(Codex CLI or Claude Code, your pick) writes a real Expo / React Native app, the machine compiles a
signed release APK, and adb installs and launches it on the phone plugged into your USB port.
Everything runs on your own laptop. The only cloud piece is the ChatGPT or Claude subscription the
agent already uses, so there is nothing to deploy, no accounts to create and no per-app cost.

It is built for people who do not want to touch an IDE: statuses are in plain language, every app
keeps its own history, and "change the button to green" is a text box, not a pull request.

## What you can do

- **New app**: describe it, optionally name it, pick the agent, press Create. Watch the agent think and
  the build run (technical logs stay behind a toggle). When the APK is ready, press Install.
- **Revise**: every app has a text box for the next change. The agent edits the existing code, the
  version bumps, the app rebuilds and reinstalls. Each run is a git commit inside the app folder.
- **Get inspired**: browse the Play Store top charts or search it, pick an app, add your notes, and the
  agent builds your own take on it from the store listing, screenshots and (optionally) user reviews.
  Tick "Also study the original app" and the agent gets the APK too, decompiled and searchable through
  [REA](https://github.com/morluto/rea) running as an MCP server, so it can learn how the original
  actually works before writing its own version. Names, branding, assets and code are never copied.
- **Devices**: see the phones you have plugged in (and the ones you had before), rename them, and see
  which apps are installed where. After each install the dashboard shows a screenshot from the phone.
- **Settings**: check that Codex / Claude are signed in, and store API keys (OpenAI, Anthropic, ...) that
  get passed into generated apps as `EXPO_PUBLIC_*` variables, so the agent can build apps that call an AI.

Every build is a release build signed with a keystore generated once on your machine, so the apps
stay installed, update in place and look like any other app. All of them get the launcher label
`my:<name>`, so typing `my:` in the phone's app search lists everything vibeApping made.

## How it works

```
 dashboard (Vite + React)  ──HTTP/SSE──▶  backend (FastAPI)
                                              │
            1. copy template/ → ~/vibeapping/apps/<id>   (Expo SDK 58, expo-router, TypeScript)
            2. codex exec  |  claude -p      with the create / revise / fix prompt
            3. tsc → expo prebuild → gradlew assembleRelease   (agent fixes build errors, up to 5 rounds)
            4. adb install -r → launch → screenshot
```

Each generated app is a normal Expo project and a normal git repository. You can open it in any
editor, run it with `npx expo start`, or keep iterating through the dashboard.

## Quick start

You need: a Windows 11 or Linux x64 machine, [Node 20+](https://nodejs.org), an Android phone with
USB debugging on, and at least one coding agent signed in:

```bash
npm i -g @openai/codex && codex login            # Codex CLI (ChatGPT plan)
npm i -g @anthropic-ai/claude-code && claude auth login   # and/or Claude Code (Claude plan)
```

The setup script installs everything else per-user and without admin rights: JDK 17, the Android SDK
(platform-tools, API 36, build-tools 36, CMake 4.1.2), `uv` + Python 3.12, the npm dependencies, a
release keystore, and the JADX jar REA uses for APK analysis. It is idempotent: re-run it any time.

### Windows

```powershell
git clone https://github.com/<you>/vibeapping.git
cd vibeapping
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # or double-click scripts\setup.bat
```

Windows needs long paths enabled once (the script tells you the exact admin command if they are not).
Then, in a new terminal:

```powershell
scripts\dev.ps1        # or scripts\dev.bat to get one window per server
```

### Linux

```bash
git clone https://github.com/<you>/vibeapping.git
cd vibeapping
bash scripts/setup.sh
bash scripts/dev.sh
```

If `adb devices` does not show your phone, install the udev rules (`android-sdk-platform-tools-common`
on Debian/Ubuntu) and replug it.

### Then

Open <http://localhost:5173>, plug in the phone, accept the USB debugging prompt on it, and create your
first app. The first build downloads Gradle and compiles the native code, so expect around 10 minutes;
after that an app takes 5 to 7 minutes end to end on a laptop, most of it in Gradle.

## Configuration

| What | Where |
|---|---|
| Generated apps, keystore, config, Play Store cache | `~/vibeapping/` (`%USERPROFILE%\vibeapping` on Windows) |
| Codex model | `VIBE_CODEX_MODEL` (default `gpt-5.6-sol`; the Codex config default is not available on ChatGPT plans) |
| Claude model | `VIBE_CLAUDE_MODEL` (default: the CLI's own default) |
| JADX jar for REA | `REA_JADX_MCP_JAR` (set by setup) |
| API keys for generated apps | Settings tab → stored in `~/vibeapping/keys.json`, verified before they are enabled |

The agents run sandboxed inside the app folder with network access, so they can `npx expo install`
extra packages. Prompts live in `backend/vibe/codex.py` and are shared by both agents; the file
`template/AGENTS.md` is what the agent reads inside every generated app.

## Project layout

```
scripts/        setup.ps1 / setup.sh (toolchain), dev.ps1 / dev.bat / dev.sh (run both servers)
template/       the Expo app every generated app starts from (+ AGENTS.md for the agent)
backend/vibe/   FastAPI: api, workspace, codex, claude, build, devices, playstore, settings
backend/playstore/   tiny Node CLI around google-play-scraper
dashboard/      Vite + React single-page UI
```

[AGENTS.md](AGENTS.md) is the detailed guide to the code base: the request flow, exact agent
invocations, pinned versions and the Windows pitfalls we hit along the way.

## Built on

- [Expo](https://expo.dev) and React Native for the generated apps
- [Codex CLI](https://github.com/openai/codex) and [Claude Code](https://github.com/anthropics/claude-code) as the coding agents
- [REA](https://github.com/morluto/rea) for reverse engineering APKs through MCP, with [jadx-headless-mcp](https://github.com/1013503897/jadx-headless-mcp)
- [google-play-scraper](https://github.com/facundoolano/google-play-scraper) for the Play Store browser
- [adbutils](https://github.com/openatx/adbutils), FastAPI and Vite

## Status and caveats

This is a working prototype that builds and installs apps every day on one laptop. It is not a product:

- Only Android, only one phone at a time over USB, only arm64 release builds.
- The Play Store browser uses an unofficial scraper and APK mirror; both break when the upstream changes.
- Screenshots after install are black when the phone is locked with a PIN.
- Generated apps are the agent's work. Read them before you ship them anywhere.

## License

MIT, see [LICENSE](LICENSE).
