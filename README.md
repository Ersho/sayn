<h1 align="center">sayn</h1>
<p align="center"><b>Subscriptions Are All You Need.</b><br>

See an app you like, click <b>Make my own</b>, and five minutes later your own version is on your phone. No ads, no paywall, no app store. Free, open source, runs on your laptop.</p>

<p align="center"><img src="docs/how-it-works.svg" alt="1. Pick a Play Store app and click Make my own. 2. Your coding agent writes, builds and installs it from your laptop. 3. Your own version, without ads or subscription, opens on your phone." width="960"></p>

Found a habit tracker that wants $6.99 a month? A flashlight with three ad banners? A to-do app
that almost fits but not quite? Pick it in sayn, write one line about what you want different,
and your coding agent builds your own version and installs it on the phone plugged into your
laptop. Don't need a template? Just describe the app in a sentence.

---

sayn costs nothing and has no sayn account. iOS device installs additionally need an Apple account for signing. It uses the coding agent you already have, Claude Code or
Codex CLI, billed to the Claude or ChatGPT plan you already pay for. sayn is the factory around it:

- **Describe it.** One paragraph in a local dashboard. Codex CLI or Claude Code writes a real Expo /
  React Native app, your laptop builds it, and sayn installs and launches it on the phone on your desk.
  Android uses a signed release APK; iOS uses Xcode and Apple development signing.
- **Or search the Play Store and make your own.** Browse the top charts or search any app, pick it,
  add your notes. The agent builds your version from the store listing, screenshots and reviews. Tick
  one box and [REA](https://github.com/morluto/rea) analyses the real APK into a feature spec
  (screens, flows, data) that the agent builds from. It never copies the original's code. No ads, no in-app purchases, no
  subscription, and it is yours. Names, branding, assets and code are never copied.
- **Change it any time.** Every app has a text box for the next change. The agent edits the code, the
  version bumps, the app rebuilds and reinstalls. Each run is a git commit inside the app folder.

Everything runs on your machine. No cloud sandbox, no account, no API key, no per-app cost. The only
thing that leaves your laptop is the conversation your agent already has with its provider.

## Quick start

You need a Mac (Apple silicon or Intel), Windows x64 or Linux x64 machine, [Node 22.13+, 24.3+, or 26+](https://nodejs.org),
an Android phone with USB debugging on or an iPhone/iPad for macOS, and at least one coding agent signed in:

```bash
npm i -g @openai/codex && codex login                      # Codex CLI (ChatGPT plan)
npm i -g @anthropic-ai/claude-code && claude auth login     # and/or Claude Code (Claude plan)
```

The setup script installs the rest per-user, without admin rights: JDK 17, the Android SDK, `uv` +
Python 3.12, npm dependencies, a release keystore and the JADX jar REA uses. Re-run it any time.

**Windows**

```powershell
git clone https://github.com/Ersho/sayn.git
cd sayn
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # or double-click scripts\setup.bat
scripts\dev.ps1                                               # in a new terminal; or scripts\dev.bat
```

Windows needs long paths enabled once; the script prints the exact admin command if they are not.

**macOS / Linux**

```bash
git clone https://github.com/Ersho/sayn.git
cd sayn
bash scripts/setup.sh
bash scripts/dev.sh
```

On Apple silicon, install Rosetta 2 once for the Android native build tools:
`softwareupdate --install-rosetta --agree-to-license`. Without Rosetta, setup skips Android and finishes
for iPhone/iPad. On a Mac that only builds iPhone/iPad apps, run `bash scripts/setup.sh --no-android`
to skip the Android SDK entirely. Setup uses a native JDK 17 and defaults to
`~/Library/Android/sdk` on macOS (`~/Android/Sdk` on Linux); set `ANDROID_HOME` before setup to use
an existing SDK. Homebrew and Android Studio are not required.

For Android, unlock the phone and accept its USB debugging prompt. macOS needs no USB driver. On Linux, if
`adb devices` does not list your phone, install the udev rules (`android-sdk-platform-tools-common`
on Debian/Ubuntu) and replug it.

Then open <http://localhost:5173> and create your first app. For iPhone/iPad, complete the setup below first.
The very first Android build downloads Gradle and compiles the native code (about
10 minutes); after that an app takes 5 to 7 minutes end to end, most of it in Gradle.

## iPhone and iPad (macOS)

Optional: skip this section if you only build Android apps. Windows and Linux never need any of it.
The dashboard and coding agent run on your Mac, just like the Android workflow. iOS builds use
local Xcode release builds and Apple development signing; no cloud build service is needed.

You don't need to remember the steps. `setup.sh` ends with this checklist on a Mac, and the dashboard
shows the same list under **Settings → iPhone and iPad** with a **Check again** button. Each step
shows `ok` or the exact next step. Do them in this order:

| # | Checkpoint | What to do |
|---|---|---|
| 1 | Xcode installed and set up | Install Xcode from the App Store, open it once to finish setup, then select it in Xcode → Settings → Locations → Command Line Tools. |
| 2 | CocoaPods installed | `brew install cocoapods` (or `sudo gem install cocoapods`), then restart sayn. |
| 3 | Apple account added to Xcode | Xcode → Settings → Accounts → + → sign in with your Apple ID. A free account works. |
| 4 | Signing team chosen in sayn | In sayn's Settings, pick the team Xcode found (or type its 10-character ID, or set `VIBE_IOS_TEAM`). |
| 5 | iPhone or iPad connected | Plug it in with a cable and unlock it. |
| 6 | It trusts this Mac | Tap **Trust** on the phone and enter its passcode. |
| 7 | Developer Mode on | On the phone: Settings → Privacy & Security → Developer Mode, then restart. If it's missing, open Xcode → Window → Devices and Simulators with the phone plugged in, then look again. |

Steps 1 and 2 are enough for the iOS Simulator. After that, choose **iPhone / iPad** in New app or Make my own version, select the device, then generate and install the app.
Certificates and provisioning profiles are created automatically during the first device build.

If iOS blocks the first launch, trust your developer profile in Settings → General → VPN & Device Management, then install again.

A free Personal Team can sign local test installs, which expire after seven days and need rebuilding.
Apple also limits free provisioning; see [Apple's account overview](https://developer.apple.com/help/account/basics/about-your-developer-account).
For a Simulator build, start a Simulator in Xcode, choose **iOS Simulator**, and select it. It requires no signing team.
Device and Simulator builds are different targets: install each on the matching device type.

The current CLI can capture Android and Simulator screenshots. For a physical iPhone/iPad, use
Xcode to capture its screen; successful installation does not depend on a screenshot. Native hardware
features such as Bluetooth need testing on a real device. Browser previews remain available for compatible screens.

Node is a prerequisite on every host. Setup installs the dashboard's local Vite dependency,
including development dependencies even when `NODE_ENV=production`; a global Vite install is not needed.

## How it works

```
 dashboard (Vite + React)  ──HTTP/SSE──▶  backend (FastAPI)
                                              │
            1. copy template/ → ~/vibeapping/apps/<id>   (Expo SDK 58, expo-router, TypeScript)
            2. codex exec  |  claude -p      with the create / revise / fix prompt
            3. tsc → expo prebuild → gradlew assembleRelease (Android) or pod install → xcodebuild (iOS)
            4. adb (Android) or devicectl / simctl (iOS) → install → launch
```

Android release builds are signed with a keystore generated once on your machine, so apps stay
installed, update in place and look like any other app. They all get the launcher label `my:<name>`,
so typing `my:` in the phone's app search lists everything sayn made. Each app is a normal Expo
project and a normal git repository: open it in any editor or keep iterating from the dashboard.

## Configuration

| What | Where |
|---|---|
| Generated apps, keystore, config, caches | `~/vibeapping/` (`%USERPROFILE%\vibeapping` on Windows) |
| Codex model | `VIBE_CODEX_MODEL` (default `gpt-5.6-sol`; the Codex config default is not available on ChatGPT plans) |
| iOS signing team | Settings → iPhone and iPad signing, or `VIBE_IOS_TEAM` |
| Claude model | `VIBE_CLAUDE_MODEL` (default: the CLI's own default) |
| API keys for generated apps | Settings tab, stored in `~/vibeapping/keys.json`; an app that needs AI asks first, then gets one key as `EXPO_PUBLIC_*` |

Prompts live in `backend/vibe/codex.py` and are shared by both agents. `template/AGENTS.md` is what
the agent reads inside every generated app. [AGENTS.md](AGENTS.md) is the detailed guide to this code
base: request flow, exact agent invocations, pinned versions and the Windows pitfalls.

## Built on

[Expo](https://expo.dev) · [Codex CLI](https://github.com/openai/codex) · [Claude Code](https://github.com/anthropics/claude-code) ·
[REA](https://github.com/morluto/rea) + [jadx-headless-mcp](https://github.com/1013503897/jadx-headless-mcp) ·
[google-play-scraper](https://github.com/facundoolano/google-play-scraper) · [adbutils](https://github.com/openatx/adbutils) · FastAPI · Vite

## License

MIT, see [LICENSE](LICENSE).
