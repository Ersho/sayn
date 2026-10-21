#!/usr/bin/env bash
# sayn setup for macOS and Linux — idempotent, per-user, no sudo needed.
#   bash scripts/setup.sh
#   bash scripts/setup.sh --no-android     # macOS, iPhone/iPad apps only
# Installs: JDK 17, Android SDK (platform-tools, android-36, build-tools 36, cmake 4.1.2), uv + Python 3.12,
# npm dependencies, the release keystore and the JADX jar REA needs. Writes ~/vibeapping/env.sh with the env vars.
# On macOS it ends with the iPhone/iPad checklist (backend/vibe/ios.py); Xcode and CocoaPods are never installed here.
set -euo pipefail

# macOS ships Bash 3.2; keep this script compatible with it.
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS/$ARCH" in
    Linux/x86_64) JDK_PLATFORM='linux-x64'; SDK_PLATFORM='linux'; SDK_DEFAULT="$HOME/Android/Sdk" ;;
    Darwin/arm64) JDK_PLATFORM='macos-aarch64'; SDK_PLATFORM='mac_arm64'; SDK_DEFAULT="$HOME/Library/Android/sdk" ;;
    Darwin/x86_64) JDK_PLATFORM='macos-x64'; SDK_PLATFORM='mac_x86_64'; SDK_DEFAULT="$HOME/Library/Android/sdk" ;;
    *) echo "Unsupported platform: $OS/$ARCH (use macOS arm64/x64 or Linux x64)." >&2; exit 1 ;;
esac
ANDROID=1
case "${1:-}" in
    '') ;;
    --no-android)
        [ "$OS" = Darwin ] || { echo '--no-android is for macOS (iPhone/iPad only); on Linux sayn builds Android apps.' >&2; exit 1; }
        ANDROID=0 ;;
    *) echo "Unknown option: $1 (the only option is --no-android)" >&2; exit 1 ;;
esac
JDK_TAR="https://aka.ms/download-jdk/microsoft-jdk-17.0.20.1-$JDK_PLATFORM.tar.gz"
CMDLINE_TOOLS_ZIP="https://dl.google.com/android/repository/commandlinetools-$SDK_PLATFORM-15859902_latest.zip"
JADX_JAR_URL='https://github.com/1013503897/jadx-headless-mcp/releases/download/v0.7.1/jadx-headless-mcp-0.7.1-all.jar'
REA_VERSION='6.7.0'                                  # keep in sync with REA in backend/vibe/playstore.py
PACKAGES='platform-tools platforms;android-36 build-tools;36.0.0 cmake;4.1.2'

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="$HOME/vibeapping"
ANDROID_HOME="${ANDROID_HOME:-$SDK_DEFAULT}"
JDK_ROOT="$HOME/.local/share/vibeapping/jdk"
[ "$OS" != Darwin ] || JDK_ROOT="$JDK_ROOT/$JDK_PLATFORM"
ENV_FILE="$WORKSPACE/env.sh"

step() { printf '\n\033[36m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m  %s\n' "$*"; }
die()  { printf '   \033[31m%s\033[0m\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 is required. Install it with your package manager and re-run."; }

mkdir -p "$WORKSPACE/apps" "$WORKSPACE/tools"
export PATH="$HOME/.local/bin:$PATH"

step 'Basics'
for t in curl unzip tar git; do need "$t"; done
need node
need npm
node "$REPO/scripts/check-node.mjs"
ok "node $(node -v), npm $(npm -v)"
NO_ROSETTA=0
if [ $ANDROID -eq 1 ] && [ "$OS/$ARCH" = Darwin/arm64 ] && ! /usr/bin/arch -x86_64 /usr/bin/true 2>/dev/null; then
    # Only the Android native build tools need Rosetta; skip Android so iPhone-only users can finish.
    ANDROID=0; NO_ROSETTA=1
    echo '   Rosetta 2 is missing, so Android is skipped. iPhone/iPad builds do not need it.'
fi
# Unique temporary downloads, cleaned up on both success and failure.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

step 'JDK 17'
jdk_home() {
    local root
    root="$(ls -d "$JDK_ROOT"/jdk-17* 2>/dev/null | head -1 || true)"
    if [ -n "$root" ]; then
        if [ "$OS" = Darwin ]; then root="$root/Contents/Home"; fi
        [ ! -x "$root/bin/java" ] || printf '%s\n' "$root"
    fi
}
JAVA_HOME="$(jdk_home)"
if [ -z "$JAVA_HOME" ]; then
    mkdir -p "$JDK_ROOT"
    echo "   downloading $JDK_TAR"
    curl -fsSL "$JDK_TAR" -o "$TMP/jdk17.tar.gz"
    tar -xzf "$TMP/jdk17.tar.gz" -C "$JDK_ROOT"
    JAVA_HOME="$(jdk_home)"
    [ -n "$JAVA_HOME" ] || die "Could not find JDK 17 in $JDK_ROOT"
    ok 'JDK 17 installed'
fi
export JAVA_HOME PATH="$JAVA_HOME/bin:$PATH"
ok "$(grep '^JAVA_VERSION=' "$JAVA_HOME/release")"

step 'Android SDK'
export ANDROID_HOME ANDROID_SDK_ROOT="$ANDROID_HOME" PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
if [ $ANDROID -eq 1 ]; then
    SDKMANAGER="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
    if [ ! -x "$SDKMANAGER" ]; then
        mkdir -p "$ANDROID_HOME/cmdline-tools"
        echo "   downloading $CMDLINE_TOOLS_ZIP"
        curl -fsSL "$CMDLINE_TOOLS_ZIP" -o "$TMP/cmdline-tools.zip"
        unzip -q "$TMP/cmdline-tools.zip" -d "$TMP/cmdline-tools"
        mv "$TMP/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
        ok 'cmdline-tools installed'
    fi
    # Accept the SDK licences by writing the hash files sdkmanager looks for.
    mkdir -p "$ANDROID_HOME/licenses"
    printf '\n24333f8a63b6825ea9c5514f83c2829b004d1fee\nd56f5187479451eabf01fb78af6dfcb131a6481e' > "$ANDROID_HOME/licenses/android-sdk-license"
    printf '\n84831b9409646a918e30573bab4c9c91346d8abd' > "$ANDROID_HOME/licenses/android-sdk-preview-license"
    missing=()
    for p in $PACKAGES; do [ -d "$ANDROID_HOME/${p//;//}" ] || missing+=("$p"); done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "   installing: ${missing[*]}"
        "$SDKMANAGER" "--sdk_root=$ANDROID_HOME" "${missing[@]}"
        for p in "${missing[@]}"; do [ -d "$ANDROID_HOME/${p//;//}" ] || die "sdkmanager did not install $p"; done
    fi
    for p in $PACKAGES; do ok "$p"; done
else
    echo '   skipped: no Android apps on this Mac. Re-run without --no-android to add them later.'
fi

step 'Python 3.12 (uv)'
if ! command -v uv >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
uv python install 3.12 >/dev/null
ok "$(uv python find 3.12)"

step 'npm dependencies (template, dashboard, Play Store scraper)'
(cd "$REPO/template"  && { { [ -d node_modules/expo ] && [ -f node_modules/typescript/bin/tsc ]; } || npm ci --include=dev --silent; })
(cd "$REPO/dashboard" && { [ -f node_modules/vite/bin/vite.js ] || npm install --include=dev --silent; })
(cd "$REPO/backend/playstore" && { [ -d node_modules/google-play-scraper ] || npm install --include=dev --silent; })
ok 'installed'

step 'Coding agents'
agents=0
if command -v codex >/dev/null 2>&1; then
    if codex login status 2>&1 | grep -qi 'logged in'; then ok "codex: signed in"; agents=1
    else echo "   codex is installed but not signed in. Run: codex login"; fi
else echo "   codex not found (optional): npm i -g @openai/codex && codex login"; fi
if command -v claude >/dev/null 2>&1; then
    if claude auth status 2>/dev/null | grep -q '"loggedIn": *true'; then ok "claude: signed in"; agents=1
    else echo "   claude is installed but not signed in. Run: claude auth login"; fi
else echo "   claude not found (optional): npm i -g @anthropic-ai/claude-code && claude auth login"; fi
[ $agents -eq 1 ] || echo "   WARNING: no signed-in agent. Install Codex CLI or Claude Code and sign in before creating apps."

step "Workspace $WORKSPACE"
CONFIG="$WORKSPACE/config.json"; JKS="$WORKSPACE/vibe.jks"
if [ ! -f "$CONFIG" ]; then
    # Avoid a tr | head pipeline: pipefail treats its expected SIGPIPE as a setup failure.
    pw="$(node -e 'process.stdout.write(require("node:crypto").randomBytes(18).toString("hex"))')"
    printf '{\n  "keystore": "%s",\n  "alias": "vibe",\n  "password": "%s"\n}\n' "$JKS" "$pw" > "$CONFIG"
    ok 'wrote config.json'
fi
if [ ! -f "$JKS" ]; then
    pw="$(sed -n 's/.*"password": *"\([^"]*\)".*/\1/p' "$CONFIG")"
    "$JAVA_HOME/bin/keytool" -genkeypair -v -keystore "$JKS" -alias vibe -keyalg RSA -keysize 2048 -validity 10000 \
        -storepass "$pw" -keypass "$pw" -dname 'CN=vibeApping, OU=dev, O=vibeApping, L=Local, S=Local, C=US' >/dev/null 2>&1
    ok 'generated vibe.jks'
fi
ok 'config.json + vibe.jks (alias vibe)'

step 'APK analysis (REA + JADX)'
JADX_JAR="$WORKSPACE/tools/jadx-headless-mcp-0.7.1-all.jar"
if [ ! -f "$JADX_JAR" ]; then
    echo "   downloading $JADX_JAR_URL"
    curl -fsSL "$JADX_JAR_URL" -o "$JADX_JAR"
    ok 'jadx-headless-mcp jar installed'
fi
npx -y "rea-agents@$REA_VERSION" --help >/dev/null 2>&1 || true   # warm the npx cache
ok "rea-agents@$REA_VERSION + $JADX_JAR"

step "Environment file $ENV_FILE"
{
    echo "# Generated by scripts/setup.sh. Sourced by scripts/dev.sh; add 'source $ENV_FILE' to your shell rc to use the tools directly."
    printf 'export JAVA_HOME=%q\n' "$JAVA_HOME"
    printf 'export ANDROID_HOME=%q\n' "$ANDROID_HOME"
    printf 'export ANDROID_SDK_ROOT=%q\n' "$ANDROID_HOME"
    printf 'export REA_JADX_MCP_JAR=%q\n' "$JADX_JAR"
    echo 'export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$HOME/.local/bin:$PATH"'
} > "$ENV_FILE"
ok 'written'

if [ $ANDROID -eq 1 ]; then
    step 'adb devices'
    adb devices -l || true
fi
if [ "$OS" = Darwin ]; then
    # Same checks as the dashboard's Settings → iPhone and iPad; re-run setup to tick off more.
    step 'iPhone / iPad (optional, skip if you only build Android apps)'
    (cd "$REPO/backend" && uv run --quiet python -m vibe.ios) || echo '   could not run the iPhone checks'
fi
echo
echo "Done. Start sayn with:  bash scripts/dev.sh"
if [ "$OS" = Linux ]; then
    echo "If your phone is missing or shows 'no permissions', install the udev rules once (Debian/Ubuntu):"
    echo "  sudo apt install android-sdk-platform-tools-common && sudo usermod -aG plugdev \$USER"
    echo "then log out and in, replug the phone and accept the USB debugging prompt on it."
elif [ $ANDROID -eq 1 ]; then
    echo "Android: unlock your phone and accept the USB debugging prompt. macOS needs no USB driver."
elif [ $NO_ROSETTA -eq 1 ]; then
    echo "Android was skipped. To add it: softwareupdate --install-rosetta --agree-to-license, then re-run setup."
fi
if [ "$OS" = Darwin ]; then
    echo "iPhone: finish the steps marked -- above (they also show in sayn's Settings), then pick iPhone / iPad in New app."
fi
