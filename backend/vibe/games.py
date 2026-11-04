"""Games: the Play Store game categories, the game area's one-time setup ("Turn on games"), and the game kit (repo
games/) every game app gets on top of the template.

Nothing here is installed by the setup scripts. "Turn on games" (turn_on) downloads the game skills and the game tester
into ~/vibeapping/tools once; a game build installs whatever is still missing (add_kit, ensure_skills, ensure_tester).
kit() says which parts are already on this computer; the dashboard shows the rest before anything is downloaded."""
import io
import json
import os
import shutil
import subprocess
import threading
import urllib.request
import zipfile
import zlib
from pathlib import Path
from typing import Callable

from . import workspace

KIT = workspace.REPO / "games"
TOOLS = workspace.ROOT / "tools"
TESTER = TOOLS / "game-tester"  # Playwright + headless Chromium, shared by all games
SKILLS = TOOLS / "game-skills"  # the skills, copied into each game as .claude/skills/
MARKER = TOOLS / "game-kit.json"  # the pinned packages once npm has downloaded them
PLAYWRIGHT = "playwright@1.64.1"
# threejs-game-skills (MIT, by Majid Manzarpour), pinned to the commit that was tested; downloaded, not vendored.
SKILLS_REPO = "majidmanzarpour/threejs-game-skills"
SKILLS_COMMIT = "8286774b22a2566bf894dbc825825c16921866af"

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

It opens the game in a phone-sized browser, taps, holds and drags left and right like a player, and saves screenshots to artifacts/play/. Open and look at every screenshot and fix what looks wrong, empty or broken.

When there are target pictures (inspiration/screenshot-*.png or references/ref-*), put your game next to them:

    node "{compare}" artifacts/play/2-play.png inspiration/screenshot-1.png artifacts/compare-1.png

Pick the store screenshot closest to that moment of play (use another play screenshot or target picture where it fits better), open the comparison image, and list the differences one by one: type of game, camera, density and scale, layout, colours and lighting, effects, HUD. Fix them, play again and compare again: at least two rounds, and keep going while the difference is big.

Stop the web server when you are done. The browser renders in software, so its frame rate says nothing about the phone. Do not install Playwright into this project."""
TESTER_MISSING = """No browser tester is installed on this computer. Check your work by reading the code carefully: the scene setup, the camera, the game loop and every game state."""

Emit = Callable[[str, str], None]
ACTIVATION = {"running": False, "step": "", "error": ""}  # the "Turn on games" job, polled by the dashboard


def _packages_ready() -> bool:
    try:
        return json.loads(MARKER.read_text("utf-8")) == PACKAGES + DEV_PACKAGES
    except (OSError, ValueError):
        return False


def skills_ready() -> bool:
    try:
        return (SKILLS / ".commit").read_text("utf-8") == SKILLS_COMMIT
    except OSError:
        return False


def tester_ready() -> bool:
    return (TESTER / "node_modules" / "playwright").is_dir() and any((TESTER / "browsers").glob("chromium_headless_shell-*"))


def active() -> bool:
    """The game area is on: the skills and the game tester are on this computer."""
    return skills_ready() and tester_ready()


def kit() -> list[dict]:
    """What games need beyond a normal app, for the dashboard. ready = already on this computer (nothing to download)."""
    return [
        {"id": "skills", "label": "Game-making skills for your assistant", "ready": skills_ready(), "size": "about 1 MB, from GitHub",
         "detail": "threejs-game-skills (MIT): how to design gameplay, graphics, menus and tests for a polished game."},
        {"id": "tester", "label": "Game tester", "ready": tester_ready(), "size": "about 300 MB, once on this computer",
         "detail": "A hidden browser (Playwright with Chromium) where your assistant plays the game and looks at screenshots before it finishes."},
        {"id": "engine", "label": "3D game engine", "ready": _packages_ready(), "size": "about 30 MB, while your first game builds",
         "detail": "three.js and React Three Fiber draw the game; expo-gl runs them on the phone. Added to every game (about 3 MB in the app)."},
        {"id": "sound", "label": "Sound and vibration", "ready": _packages_ready(), "size": "comes with the engine",
         "detail": "expo-audio and expo-haptics, so hits, wins and taps can be heard and felt."},
    ]


def turn_on() -> None:
    """Start "Turn on games" in the background: download the skills and install the game tester."""
    if ACTIVATION["running"]:
        return
    ACTIVATION.update(running=True, step="Starting", error="")

    def job():
        step: Emit = lambda _, text: ACTIVATION.update(step=text)  # noqa: E731
        try:
            ensure_skills(step)
            if not ensure_tester(step):
                ACTIVATION["error"] = "The game tester could not be installed. Check your internet connection and try again."
        except Exception as e:  # noqa: BLE001
            ACTIVATION["error"] = f"Turning on games failed: {e}"
        finally:
            ACTIVATION["running"] = False

    threading.Thread(target=job, daemon=True).start()


def _run(args: list[str], cwd: Path, emit: Emit) -> tuple[int, list[str]]:
    emit("build", "$ " + " ".join(args))
    proc = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    lines = []
    for line in proc.stdout:
        if line.strip():
            lines.append(line.rstrip())
            emit("build", line.rstrip())
    return proc.wait(), lines


def ensure_skills(emit: Emit) -> None:
    """Download the pinned skills from GitHub into SKILLS once (its skills/ folder and LICENSE)."""
    if skills_ready():
        return
    emit("build", f"downloading the game-making skills ({SKILLS_REPO})")
    url = f"https://codeload.github.com/{SKILLS_REPO}/zip/{SKILLS_COMMIT}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "sayn"}), timeout=120) as r:
        archive = zipfile.ZipFile(io.BytesIO(r.read()))
    root = f"{SKILLS_REPO.split('/')[1]}-{SKILLS_COMMIT}/"
    tmp = SKILLS.with_name("game-skills.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    for name in archive.namelist():
        rel = name.removeprefix(root)
        if name.endswith("/") or not (rel.startswith("skills/") or rel == "LICENSE"):
            continue
        dst = tmp / rel.removeprefix("skills/")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(archive.read(name))
    if not (tmp / "threejs-game-director" / "SKILL.md").exists():
        raise RuntimeError("the skills download was incomplete")
    (tmp / ".commit").write_text(SKILLS_COMMIT, "utf-8")
    shutil.rmtree(SKILLS, ignore_errors=True)
    tmp.rename(SKILLS)


def ensure_tester(emit: Emit) -> bool:
    """Install the game tester once (Playwright and its headless Chromium in TESTER); False when that fails."""
    TESTER.mkdir(parents=True, exist_ok=True)
    for script in ("play.mjs", "compare.mjs"):
        shutil.copy2(KIT / script, TESTER / script)
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
            code, out = _run(args, TESTER, emit)
        except (OSError, subprocess.SubprocessError) as e:
            code, out = 1, [str(e)]
        if code:
            emit("build", "the game tester could not be installed: " + (out[-1] if out else ""))
            return False
    return tester_ready()


def add_kit(app: Path, run: Callable[[list[str], Path], tuple[int, list[str]]], emit: Emit, tester: bool) -> None:
    """Copy games/ and the skills into the app and install the packages; safe to repeat (a revision of a game runs it
    again). run is the build's cancellable command runner."""
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
    shutil.copytree(SKILLS, app / ".claude" / "skills", dirs_exist_ok=True, ignore=shutil.ignore_patterns(".commit"))
    port = 19100 + zlib.crc32(app.name.encode()) % 800  # one per app, so two games can be tested at once
    testing = (TESTER_READY.format(port=port, play=(TESTER / "play.mjs").as_posix(), compare=(TESTER / "compare.mjs").as_posix())
               if tester else TESTER_MISSING)
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
