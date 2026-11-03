"""Games: the Play Store game categories, and the game kit (repo games/) every game app gets on top of the template.

The kit is installed when a game is built, not by the setup scripts, so apps that are not games stay as they are.
kit() says which parts are already on this computer; the dashboard shows the rest as "new" before a game is built."""
import json
import os
import shutil
import subprocess
import zlib
from pathlib import Path
from typing import Callable

from . import workspace

KIT = workspace.REPO / "games"
TESTER = workspace.ROOT / "tools" / "game-tester"  # Playwright + headless Chromium, shared by all games
MARKER = workspace.ROOT / "tools" / "game-kit.json"  # the pinned packages once npm has downloaded them
PLAYWRIGHT = "playwright@1.64.1"

CATEGORIES = ["GAME_ACTION", "GAME_ARCADE", "GAME_CASUAL", "GAME_PUZZLE", "GAME_STRATEGY", "GAME_SIMULATION",
              "GAME_RACING", "GAME_SPORTS", "GAME_ADVENTURE", "GAME_ROLE_PLAYING", "GAME_BOARD", "GAME_CARD",
              "GAME_WORD", "GAME_TRIVIA"]

# Pinned: three 0.187 and fiber 9.8 are what was tested on Hermes; the expo-* ranges follow the Expo SDK.
PACKAGES = ["three@0.187.0", "@react-three/fiber@9.8.2", "expo-gl@~58.0.4", "expo-asset@~58.0.19",
            "expo-file-system@~58.0.13", "expo-audio@~58.0.11", "expo-haptics@~58.0.7"]
DEV_PACKAGES = ["@types/three@0.187.0"]
PLUGINS = ["./plugins/withGlKeep.js", "expo-asset",
           ["expo-audio", {"microphonePermission": False, "recordAudioAndroid": False, "enableBackgroundPlayback": False}]]

TESTER_READY = """Play the game in a browser and look at it before you finish. Start `npx expo start --web --port {port}` in the background, wait until http://localhost:{port} answers, then run from this folder:

    node "{play}" http://localhost:{port} artifacts/play

It opens the game in a phone-sized browser, taps, holds and drags left and right like a player, and saves screenshots to artifacts/play/. Open and look at every screenshot, fix what looks wrong, empty or broken, and run it again. Stop the web server when you are done. The browser renders in software, so its frame rate says nothing about the phone. Do not install Playwright into this project."""
TESTER_MISSING = """No browser tester is installed on this computer. Check your work by reading the code carefully: the scene setup, the camera, the game loop and every game state."""


def _packages_ready() -> bool:
    try:
        return json.loads(MARKER.read_text("utf-8")) == PACKAGES + DEV_PACKAGES
    except (OSError, ValueError):
        return False


def tester_ready() -> bool:
    return (TESTER / "node_modules" / "playwright").is_dir() and any((TESTER / "browsers").glob("chromium_headless_shell-*"))


def kit() -> list[dict]:
    """What a game gets beyond a normal app, for the dashboard. ready = already on this computer (nothing to download)."""
    return [
        {"id": "engine", "label": "3D game engine", "ready": _packages_ready(), "size": "about 30 MB, downloaded once",
         "detail": "three.js and React Three Fiber draw the game; expo-gl runs them on the phone. Added to every game (about 3 MB in the app)."},
        {"id": "sound", "label": "Sound and vibration", "ready": _packages_ready(), "size": "comes with the engine download",
         "detail": "expo-audio and expo-haptics, so hits, wins and taps can be heard and felt."},
        {"id": "skills", "label": "Game-making skills for your assistant", "ready": True, "size": "included with sayn",
         "detail": "threejs-game-skills (MIT): how to design gameplay, graphics, menus and tests for a polished game."},
        {"id": "tester", "label": "Game tester", "ready": tester_ready(), "size": "about 300 MB, installed once on this computer",
         "detail": "A hidden browser (Playwright with Chromium) where your assistant plays the game and looks at screenshots before it finishes."},
    ]


def add_kit(app: Path, run: Callable[[list[str], Path], tuple[int, list[str]]], emit: Callable[[str, str], None],
            tester: bool) -> None:
    """Copy games/ into the app and install the packages; safe to repeat (a revision of a game runs it again)."""
    pkg = json.loads((app / "package.json").read_text("utf-8-sig"))
    if "three" not in pkg.get("dependencies", {}):
        emit("build", "adding the 3D game engine, sound and vibration" + ("" if _packages_ready() else " (first game: downloading them)"))
        npm = "npm.cmd" if os.name == "nt" else "npm"
        for args in ([npm, "install", "--no-audit", "--no-fund", *PACKAGES],
                     [npm, "install", "--no-audit", "--no-fund", "--save-dev", *DEV_PACKAGES]):
            code, out = run(args, app)
            if code:
                raise RuntimeError("Installing the game engine failed:\n" + "\n".join(out[-30:]))
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text(json.dumps(PACKAGES + DEV_PACKAGES), "utf-8")

    shutil.copy2(KIT / "metro.config.js", app / "metro.config.js")
    shutil.copy2(KIT / "plugins" / "withGlKeep.js", app / "plugins" / "withGlKeep.js")
    shutil.copytree(KIT / "skills", app / ".claude" / "skills", dirs_exist_ok=True)
    port = 19100 + zlib.crc32(app.name.encode()) % 800  # one per app, so two games can be tested at once
    testing = TESTER_READY.format(port=port, play=(TESTER / "play.mjs").as_posix()) if tester else TESTER_MISSING
    (app / "GAMES.md").write_text((KIT / "GAMES.md").read_text("utf-8").replace("{tester}", testing), "utf-8")

    app_json = app / "app.json"
    data = json.loads(app_json.read_text("utf-8-sig"))
    plugins = data["expo"].setdefault("plugins", [])
    for p in PLUGINS:
        if not any(q == p or (isinstance(q, list) and isinstance(p, list) and q[0] == p[0]) for q in plugins):
            plugins.append(p)
    android = data["expo"].setdefault("android", {})
    blocked = android.setdefault("blockedPermissions", [])
    if "android.permission.RECORD_AUDIO" not in blocked:  # expo-audio would add the microphone otherwise
        blocked.append("android.permission.RECORD_AUDIO")
    app_json.write_text(json.dumps(data, indent=2) + "\n", "utf-8")

    exclude = app / ".git" / "info" / "exclude"
    if "artifacts/" not in exclude.read_text("utf-8"):  # play-test screenshots and the skills' evidence files
        exclude.open("a", encoding="utf-8").write("\nartifacts/\n")


def ensure_tester(run: Callable[[list[str], Path], tuple[int, list[str]]], emit: Callable[[str, str], None]) -> bool:
    """Install the game tester once (Playwright and its headless Chromium in TESTER); False when that fails."""
    TESTER.mkdir(parents=True, exist_ok=True)
    shutil.copy2(KIT / "play.mjs", TESTER / "play.mjs")
    if tester_ready():
        return True
    emit("build", "installing the game tester (once on this computer, about 300 MB)")
    if not (TESTER / "package.json").exists():
        (TESTER / "package.json").write_text('{"name": "game-tester", "private": true, "type": "module"}\n', "utf-8")
    npm, npx = ("npm.cmd", "npx.cmd") if os.name == "nt" else ("npm", "npx")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(TESTER / "browsers")  # where play.mjs looks
    for args in ([npm, "install", "--no-audit", "--no-fund", PLAYWRIGHT],
                 [npx, "playwright", "install", "--only-shell", "chromium"]):
        try:
            code, out = run(args, TESTER)
        except (OSError, subprocess.SubprocessError) as e:
            code, out = 1, [str(e)]
        if code:
            emit("build", "the game tester could not be installed, so the assistant checks the game without it: "
                 + (out[-1] if out else ""))
            return False
    return tester_ready()
