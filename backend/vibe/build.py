"""Typecheck, prebuild and compile with Gradle or Xcode, with an agent fix loop."""
import json
import os
import plistlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from . import claude, codex, ios, playstore, settings, workspace

MAX_FIX_ROUNDS = 5
ERROR_TAIL = 200
WIN = os.name == "nt"
NPX = "npx.cmd" if WIN else "npx"
Emit = Callable[[str, str], None]


def apk_path(app: Path) -> Path:
    return app / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"


def artifact_path(app: Path) -> Path:
    vibe = workspace.read_vibe(app.name)
    if vibe.get("platform", "android") == "android":
        return apk_path(app)
    sdk = "iphonesimulator" if vibe.get("ios_target") == "simulator" else "iphoneos"
    products = app / "ios" / "build" / "Build" / "Products" / f"Release-{sdk}"
    return next(products.glob("*.app"), products / "app.app")


def _run(app: Path, args: list[str], emit: Emit, cwd: Path | None = None) -> tuple[int, list[str]]:
    emit("build", "$ " + " ".join(args))
    proc = subprocess.Popen(args, cwd=cwd or app, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    lines: list[str] = []
    for line in proc.stdout:
        line = line.rstrip()
        if not line or "NO_COLOR" in line or "trace-warnings" in line:
            continue
        lines.append(line)
        emit("build", line)
    proc.wait()
    return proc.returncode, lines


def build(app: Path, emit: Emit) -> str | None:
    """Return None on success, else the error tail."""
    code, out = _run(app, [NPX, "tsc", "--noEmit"], emit)
    if code != 0:
        return "tsc --noEmit failed:\n" + "\n".join(out[-ERROR_TAIL:])

    if workspace.read_vibe(app.name).get("platform", "android") == "ios":
        return _build_ios(app, emit)

    code, out = _run(app, [NPX, "expo", "prebuild", "--platform", "android", "--no-install"], emit)
    if code != 0:
        return "expo prebuild failed:\n" + "\n".join(out[-ERROR_TAIL:])

    # Launcher label "my:<name>" so every vibeApping app is found by typing "my:" in the phone's app search.
    strings = app / "android" / "app" / "src" / "main" / "res" / "values" / "strings.xml"
    label = re.sub(r"^(my:)?", "my:", workspace.read_vibe(app.name)["name"]).replace("&", "&amp;").replace("<", "&lt;")
    strings.write_text(re.sub(r'(<string name="app_name">).*?(</string>)', lambda m: m[1] + label + m[2],
                              strings.read_text("utf-8")), "utf-8")

    cfg = workspace.config()
    sdk = os.environ["ANDROID_HOME"].replace("\\", "/")
    android = app / "android"
    (android / "local.properties").write_text(f"sdk.dir={sdk}\ncmake.dir={sdk}/cmake/4.1.2\n", "ascii")
    props = android / "gradle.properties"
    text = re.sub(r"^(VIBE_|reactNativeArchitectures).*\n?", "", props.read_text("utf-8"), flags=re.M)
    keystore = cfg["keystore"].replace("\\", "/")
    props.write_text(
        text.rstrip("\n") + "\nreactNativeArchitectures=arm64-v8a\n"  # phones only; halves native compile time
        f"VIBE_KEYSTORE={keystore}\nVIBE_ALIAS={cfg['alias']}\nVIBE_PASSWORD={cfg['password']}\n", "utf-8")

    code, out = _run(app, [str(android / ("gradlew.bat" if WIN else "gradlew")), "assembleRelease"], emit, cwd=android)
    if code != 0 or not apk_path(app).exists():
        return "gradlew assembleRelease failed:\n" + "\n".join(out[-ERROR_TAIL:])
    return None


def _build_ios(app: Path, emit: Emit) -> str | None:
    if not ios.available():
        return "iOS builds require macOS with full Xcode selected (xcode-select)."
    if not shutil.which("pod"):
        return "CocoaPods is required for iOS builds. Install it, then restart sayn."
    vibe = workspace.read_vibe(app.name)
    simulator = vibe.get("ios_target") == "simulator"
    team = ios.team()
    if not simulator and not team:
        return "Choose your Apple signing team in Settings before building for an iPhone or iPad."
    code, out = _run(app, [NPX, "expo", "prebuild", "--platform", "ios", "--no-install"], emit)
    if code:
        return "expo prebuild failed:\n" + "\n".join(out[-ERROR_TAIL:])
    native = app / "ios"
    # Generated native files can be recreated on the next prebuild.
    for info in native.glob("*/Info.plist"):
        data = plistlib.loads(info.read_bytes())
        data["CFBundleDisplayName"] = "my:" + vibe["name"].removeprefix("my:")
        info.write_bytes(plistlib.dumps(data))
    code, out = _run(app, ["pod", "install"], emit, cwd=native)
    if code:
        return "pod install failed:\n" + "\n".join(out[-ERROR_TAIL:])
    project = next(native.glob("*.xcworkspace"), None)
    if project is None:
        return "CocoaPods did not create an Xcode workspace."
    device = vibe.get("ios_device", "")
    destination = f"id={device}" if device else ("generic/platform=iOS Simulator" if simulator else "generic/platform=iOS")
    args = ["xcodebuild", "-quiet", "-workspace", str(project), "-scheme", project.stem,
            "-configuration", "Release", "-sdk", "iphonesimulator" if simulator else "iphoneos",
            "-destination", destination, "-derivedDataPath", str(native / "build")]
    if simulator:
        args += ["CODE_SIGNING_ALLOWED=NO"]
    else:
        args += [f"DEVELOPMENT_TEAM={team}", "CODE_SIGN_STYLE=Automatic",
                 "-allowProvisioningUpdates", "-allowProvisioningDeviceRegistration"]
    code, out = _run(app, [*args, "build"], emit, cwd=native)
    if code or not artifact_path(app).exists():
        return "xcodebuild failed:\n" + "\n".join(out[-ERROR_TAIL:])
    return None


def export_preview(app: Path, emit: Emit) -> None:
    """Best-effort browser preview: `expo export --platform web` into dist/, served by the API at /apps/<id>/preview/."""
    app_json = app / "app.json"
    original = app_json.read_text("utf-8")
    data = json.loads(original.lstrip("﻿"))
    data["expo"].setdefault("experiments", {})["baseUrl"] = f"/apps/{app.name}/preview"
    try:
        app_json.write_text(json.dumps(data, indent=2), "utf-8")
        shutil.rmtree(app / "dist", ignore_errors=True)
        code, _ = _run(app, [NPX, "expo", "export", "--platform", "web"], emit)
        if code != 0:
            emit("build", "web preview failed, continuing without it")
    finally:
        app_json.write_text(original, "utf-8")


def runner(agent: str):
    return claude if agent == "claude" else codex


def pipeline(app_id: str, request: str, emit: Emit, agent: str = "codex", name: str = "",
             inspiration: dict | None = None) -> None:
    """Create with the chosen agent, then build/fix until the artifact exists. Writes status.json as it goes.

    inspiration = {"app_id": <Play Store package>, "apk": bool, "reviews": bool}: the listing (and APK) is saved to
    inspiration/ first and the create prompt tells the agent to build its own version of that app."""
    naming = codex.NAME_GIVEN.format(name=name) if name else codex.NAME_PICK

    def prompt(info: dict | None) -> str:
        return codex.CREATE.format(request=request, naming=naming, inspiration=codex.inspiration_block(info))

    _job(app_id, emit, agent, prompt, "create", after=lambda message: _apply_name(app_id, message),
         inspiration=inspiration)


def revise(app_id: str, request: str, emit: Emit) -> None:
    """Change an existing app with the agent that wrote it, bump the patch version, rebuild."""
    agent = workspace.read_vibe(app_id).get("agent", "codex")
    _job(app_id, emit, agent, lambda _: codex.REVISE.format(request=request), f"revise: {request[:60]}",
         after=lambda _: _bump_version(app_id))


def _job(app_id: str, emit: Emit, agent: str, prompt: Callable[[dict | None], str], commit: str,
         after: Callable[[str], None], inspiration: dict | None = None) -> None:
    app = workspace.app_dir(app_id)
    agent_run = runner(agent).run

    def run(app, prompt, emit, mcp=False):
        def on_event(kind: str, text: str):
            if kind == "model":  # the model the agent CLI reports; shown in the dashboard
                workspace.update_vibe(app_id, model=text)
                emit("codex", f"model: {text}")
            else:
                emit(kind, text)
        vibe = workspace.read_vibe(app_id)
        target = vibe.get("platform", "android")
        prompt += f"\nTarget platform: {target}. Keep native APIs and permission declarations correct for this platform."
        return agent_run(app, prompt, on_event, mcp=mcp)

    def status(s: str, **extra):
        workspace.write_status(app_id, s, **extra)
        emit("status", s)

    try:
        status("preparing")
        workspace.install_node_modules(app)
        key_names = settings.write_env(app)  # API keys switched on in Settings, as EXPO_PUBLIC_* in the app's .env
        info = None
        if inspiration:
            status("inspiring")
            info = playstore.save_inspiration(app, inspiration["app_id"], inspiration["apk"], inspiration["reviews"], emit)
            workspace.update_vibe(app_id, inspiration=info)
        status("coding")
        message = run(app, prompt(info) + settings.keys_block(key_names), emit, mcp=bool(info and info["apk"]))
        if commit == "create":
            changes = subprocess.run(["git", "status", "--porcelain", "--", "app", "src", "modules"],
                                     cwd=app, capture_output=True, text=True, check=True)
            if not changes.stdout.strip():
                raise RuntimeError("The assistant made no app changes. Check the technical log and try again.")
        after(message)
        workspace.commit(app, f"{agent}: {commit}")

        error = None
        for round_ in range(MAX_FIX_ROUNDS + 1):
            status("building", round=round_)
            error = build(app, emit)
            if error is None:
                break
            if round_ == MAX_FIX_ROUNDS:
                break
            status("fixing", round=round_ + 1)
            run(app, codex.FIX.format(error=error), emit)
            workspace.commit(app, f"{agent}: fix {round_ + 1}")

        if error:
            status("failed", error=error[-4000:], fix_rounds=MAX_FIX_ROUNDS)
        else:
            summary = message.split("\n", 1)[-1] if message.startswith("NAME:") else message
            export_preview(app, emit)
            status("ready", fix_rounds=round_, summary=summary.strip()[:1000])
    except Exception as e:  # noqa: BLE001
        status("failed", error=str(e)[-4000:])


def _bump_version(app_id: str) -> None:
    app_json = workspace.app_dir(app_id) / "app.json"
    data = json.loads(app_json.read_text("utf-8-sig"))
    parts = str(data["expo"].get("version", "1.0.0")).split(".")
    while len(parts) < 3:
        parts.append("0")
    parts[-1] = str(int(parts[-1] or 0) + 1)
    data["expo"]["version"] = ".".join(parts)
    app_json.write_text(json.dumps(data, indent=2) + "\n", "utf-8")


def _apply_name(app_id: str, message: str) -> None:
    m = re.match(r"\s*NAME:\s*(.+)", message)
    if not m:
        return
    name = m.group(1).strip().strip("*`\"")[:40]
    app = workspace.app_dir(app_id)
    vibe = workspace.read_vibe(app_id)
    vibe["name"] = name
    (app / "vibe.json").write_text(json.dumps(vibe, indent=2) + "\n", "utf-8")
    app_json = app / "app.json"
    data = json.loads(app_json.read_text("utf-8"))
    data["expo"]["name"] = name
    app_json.write_text(json.dumps(data, indent=2) + "\n", "utf-8")


def permissions(app_id: str) -> list[str]:
    if workspace.read_vibe(app_id).get("platform", "android") == "ios":
        app_json = json.loads((workspace.app_dir(app_id) / "app.json").read_text("utf-8-sig"))
        info = app_json["expo"].get("ios", {}).get("infoPlist", {})
        for native_info in (workspace.app_dir(app_id) / "ios").glob("*/Info.plist"):
            info.update(plistlib.loads(native_info.read_bytes()))
        return sorted(k for k in info if k.endswith("UsageDescription"))
    manifest = workspace.app_dir(app_id) / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    if not manifest.exists():
        return []
    return sorted(set(re.findall(r'<uses-permission[^>]*android:name="([^"]+)"', manifest.read_text("utf-8"))))
