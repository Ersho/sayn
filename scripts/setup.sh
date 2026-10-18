#!/usr/bin/env bash
# vibeApping setup for Linux — idempotent, per-user, no sudo needed (except for the udev rule, see the end).
#   bash scripts/setup.sh
# Installs: JDK 17, Android SDK (platform-tools, android-36, build-tools 36, cmake 4.1.2), uv + Python 3.12,
# npm dependencies, the release keystore and the JADX jar REA needs. Writes ~/vibeapping/env.sh with the env vars.
set -euo pipefail

JDK_TAR='https://aka.ms/download-jdk/microsoft-jdk-17.0.20.1-linux-x64.tar.gz'
CMDLINE_TOOLS_ZIP='https://dl.google.com/android/repository/commandlinetools-linux-15859902_latest.zip'
JADX_JAR_URL='https://github.com/1013503897/jadx-headless-mcp/releases/download/v0.7.1/jadx-headless-mcp-0.7.1-all.jar'
REA_VERSION='6.7.0'                                  # keep in sync with REA in backend/vibe/playstore.py
PACKAGES='platform-tools platforms;android-36 build-tools;36.0.0 cmake;4.1.2'

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="$HOME/vibeapping"
ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
JDK_ROOT="$HOME/.local/share/vibeapping/jdk"
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
[ "$(node -v | sed 's/^v\([0-9]*\).*/\1/')" -ge 20 ] || die "Node 20+ is required (found $(node -v)). https://nodejs.org or your package manager."
ok "node $(node -v), npm $(npm -v)"

step 'JDK 17'
JAVA_HOME="$(ls -d "$JDK_ROOT"/jdk-17* 2>/dev/null | head -1 || true)"
if [ -z "$JAVA_HOME" ]; then
    mkdir -p "$JDK_ROOT"
    echo "   downloading $JDK_TAR"
    curl -fsSL "$JDK_TAR" -o /tmp/jdk17.tar.gz
    tar -xzf /tmp/jdk17.tar.gz -C "$JDK_ROOT" && rm /tmp/jdk17.tar.gz
    JAVA_HOME="$(ls -d "$JDK_ROOT"/jdk-17* | head -1)"
    ok 'JDK 17 installed'
fi
export JAVA_HOME PATH="$JAVA_HOME/bin:$PATH"
ok "$(grep '^JAVA_VERSION=' "$JAVA_HOME/release")"

step 'Android SDK'
SDKMANAGER="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
if [ ! -x "$SDKMANAGER" ]; then
    mkdir -p "$ANDROID_HOME/cmdline-tools"
    echo "   downloading $CMDLINE_TOOLS_ZIP"
    curl -fsSL "$CMDLINE_TOOLS_ZIP" -o /tmp/cmdline-tools.zip
    rm -rf /tmp/cmdline-tools-extract && unzip -q /tmp/cmdline-tools.zip -d /tmp/cmdline-tools-extract
    mv /tmp/cmdline-tools-extract/cmdline-tools "$ANDROID_HOME/cmdline-tools/latest"
    rm -rf /tmp/cmdline-tools.zip /tmp/cmdline-tools-extract
    ok 'cmdline-tools installed'
fi
export ANDROID_HOME ANDROID_SDK_ROOT="$ANDROID_HOME" PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
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

step 'Python 3.12 (uv)'
if ! command -v uv >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
uv python install 3.12 >/dev/null
ok "$(uv python find 3.12)"

step 'npm dependencies (template, dashboard, Play Store scraper)'
(cd "$REPO/template"  && { [ -d node_modules/expo ] || npm ci --silent; })
(cd "$REPO/dashboard" && { [ -d node_modules/vite ] || npm install --silent; })
(cd "$REPO/backend/playstore" && { [ -d node_modules/google-play-scraper ] || npm install --silent; })
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
    pw="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
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
    echo "export JAVA_HOME=\"$JAVA_HOME\""
    echo "export ANDROID_HOME=\"$ANDROID_HOME\""
    echo "export ANDROID_SDK_ROOT=\"$ANDROID_HOME\""
    echo "export REA_JADX_MCP_JAR=\"$JADX_JAR\""
    echo 'export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$HOME/.local/bin:$PATH"'
} > "$ENV_FILE"
ok 'written'

step 'adb devices'
adb devices -l || true
echo
echo "Done. Start vibeApping with:  bash scripts/dev.sh"
echo "If your phone is missing or shows 'no permissions', install the udev rules once (Debian/Ubuntu):"
echo "  sudo apt install android-sdk-platform-tools-common && sudo usermod -aG plugdev \$USER"
echo "then log out and in, replug the phone and accept the USB debugging prompt on it."
