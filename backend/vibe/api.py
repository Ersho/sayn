"""FastAPI app. Run: uv run uvicorn vibe.api:app --port 8000"""
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from . import build, devices, ios, playstore, settings, workspace

app = FastAPI(title="vibeApping")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

TERMINAL = {"ready", "failed", "cancelled", "deployed", "unknown"}
BUSY = {"created", "preparing", "inspiring", "checking", "waiting", "reviewing", "coding", "building", "fixing"}
HOLDABLE = {"created", "preparing", "inspiring", "checking", "waiting", "coding"}  # before the code is finished
EVENTS_FILE = "events.jsonl"


def emit(app_id: str, kind: str, text: str) -> None:
    line = json.dumps({"t": time.time(), "kind": kind, "text": text})
    with open(workspace.app_dir(app_id) / EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _events(app_id: str) -> list[dict]:
    p = workspace.app_dir(app_id) / EVENTS_FILE
    return [json.loads(l) for l in p.read_text("utf-8").splitlines() if l] if p.exists() else []


class Inspiration(BaseModel):
    app_id: str   # Play Store package name
    apk: bool = False  # also download the APK and let the agent study it with REA
    reviews: bool = True  # give the agent user reviews: keep what people praise, fix what they complain about


class NewApp(BaseModel):
    request: str = ""  # may be empty when inspiration is given: then it holds the user's notes
    name: str = ""
    agent: str = "codex"  # "codex" or "claude"
    platform: str = "android"
    ios_target: str = "device"  # "device" or "simulator"
    ios_device: str = ""
    inspiration: Inspiration | None = None


class Revise(BaseModel):
    request: str


class Deploy(BaseModel):
    serial: str


class DeviceName(BaseModel):
    name: str


class KeyValue(BaseModel):
    value: str


class Answer(BaseModel):
    use_ai: bool


class Plan(BaseModel):
    name: str = ""
    features: list[str]
    extras: list[str] = []  # suggestions the user left out, kept as ideas for later


@app.get("/settings")
def get_settings():
    return {"keys": settings.list_keys(), "android": _android_sdk(),
            "ios": {"mac": sys.platform == "darwin", "available": ios.ready(), "team": ios.team()}}


def _android_sdk() -> bool:
    # setup.sh --no-android (macOS, iPhone only) leaves the SDK out.
    return (Path(os.environ.get("ANDROID_HOME", "")) / "platforms" / "android-36").is_dir()


@app.get("/settings/ios/checks")
def get_ios_checks():
    # Separate from /settings: devicectl takes a few seconds and only the iPhone panel needs it.
    return {"checks": ios.checks(), "teams": ios.teams()}


class IosTeam(BaseModel):
    team: str = ""


@app.put("/settings/ios")
def set_ios_team(body: IosTeam):
    team = body.team.strip().upper()
    if team and not re.fullmatch(r"[A-Z0-9]{10}", team):
        raise HTTPException(400, "An Apple team ID has 10 letters or digits.")
    cfg = workspace.config()
    cfg["ios_team"] = team
    workspace.CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", "utf-8")
    return {"team": ios.team()}


@app.get("/settings/subscriptions")
def get_subscriptions():
    return settings.subscriptions()


@app.put("/settings/keys/{provider}")
def put_key(provider: str, body: KeyValue):
    _provider(provider)
    if not body.value.strip():
        raise HTTPException(400, "empty key")
    settings.set_key(provider, body.value.strip())
    return {"keys": settings.list_keys()}


@app.post("/settings/keys/{provider}/check")
def check_key(provider: str):
    _saved(provider)
    settings.recheck(provider)
    return {"keys": settings.list_keys()}


@app.delete("/settings/keys/{provider}")
def remove_key(provider: str):
    _provider(provider)
    settings.delete_key(provider)
    return {"keys": settings.list_keys()}


def _provider(provider: str) -> None:
    if provider not in settings.PROVIDERS:
        raise HTTPException(404, "unknown provider")


def _saved(provider: str) -> None:
    _provider(provider)
    if not next(k for k in settings.list_keys() if k["id"] == provider)["saved"]:
        raise HTTPException(404, "no key saved")


@app.get("/devices")
def get_devices():
    return devices.list_devices()


@app.put("/devices/{serial}/name")
def put_device_name(serial: str, body: DeviceName):
    if serial not in {d["serial"] for d in devices.list_devices()}:
        raise HTTPException(404, "unknown device")
    devices.rename(serial, body.name.strip()[:40])
    return {"ok": True}


@app.get("/apps")
def get_apps():
    installed = {d["serial"]: devices.installed_packages(d["serial"], d["platform"], d["kind"])
                 for d in devices.list_devices() if d["state"] == "device"}
    apps = workspace.list_apps()
    for a in apps:
        a["installed_on"] = [serial for serial, pkgs in installed.items() if a["package"] in pkgs]
        apk = build.apk_path(workspace.app_dir(a["id"]))
        a["apk"] = apk.exists()
        a["apk_mb"] = round(apk.stat().st_size / 1e6, 1) if apk.exists() else None
        a["artifact"] = build.artifact_path(workspace.app_dir(a["id"])).exists()
        a["ai_used"] = [settings.PROVIDERS[p]["label"] for p in settings.used_providers(workspace.app_dir(a["id"]))]
        a["held"] = a["id"] in workspace.HOLDS
        if a["status"] == "waiting" and a.get("question"):  # a key added in Settings meanwhile shows up right away
            a["question"]["key"] = settings.pick(a["question"]["provider"])
    return apps


@app.post("/apps")
def post_app(body: NewApp):
    request = body.request.strip()
    inspiration = body.inspiration.model_dump() if body.inspiration else None
    if inspiration:
        request = playstore.request_text(playstore.details(inspiration["app_id"]), request)
    if not request:
        raise HTTPException(400, "empty request")
    if body.agent not in ("codex", "claude"):
        raise HTTPException(400, "unknown agent")
    if body.platform not in {"android", "ios"}:
        raise HTTPException(400, "Choose Android or iOS.")
    if body.ios_target not in {"device", "simulator"}:
        raise HTTPException(400, "Choose an iOS device or Simulator.")
    if body.platform == "android" and not _android_sdk():
        raise HTTPException(400, "Android builds need the Android SDK. Run scripts/setup.sh without --no-android, then restart sayn.")
    if body.platform == "ios":
        if not ios.ready():
            raise HTTPException(400, "iOS builds require macOS, full Xcode, and CocoaPods. See Settings → iPhone and iPad.")
        if body.ios_target == "device" and not ios.team():
            raise HTTPException(400, "Set your Apple signing team in Settings first.")
        if body.ios_device and not any(d["serial"] == body.ios_device and d["platform"] == "ios"
                                       and d["kind"] == body.ios_target and d["state"] == "device"
                                       for d in devices.list_devices()):
            raise HTTPException(400, "Connect the selected iPhone/iPad or start the selected Simulator first.")
    name = body.name.strip()[:40]
    app_id = workspace.new_id(name)
    workspace.create_app(app_id, name or "New app", request, body.agent, body.platform,
                         body.ios_target if body.platform == "ios" else "device",
                         body.ios_device if body.platform == "ios" else "")
    emit(app_id, "status", "created")
    build.start(build.pipeline, app_id, request, lambda k, t: emit(app_id, k, t), body.agent, name, inspiration)
    return {"id": app_id}


@app.get("/inspire")
def inspire_info():
    return {"categories": playstore.CATEGORIES, "apk_ready": playstore.apk_ready()}


@app.get("/inspire/top/{category}")
def inspire_top(category: str):
    if category not in playstore.CATEGORIES:
        raise HTTPException(400, "unknown category")
    return _scrape(lambda: playstore.top(category))


@app.get("/inspire/search")
def inspire_search(q: str):
    if not q.strip():
        return []
    return _scrape(lambda: playstore.search(q.strip()))


@app.get("/inspire/image")
def inspire_image(u: str, w: int = 512):
    """Icons and screenshots go through here: cached on disk, so Google's rate limit stops blanking them."""
    try:
        path = playstore.image(u, min(max(w, 32), 1080))
    except ValueError:
        raise HTTPException(400, "not a Play Store image")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"image fetch failed: {e}")
    head = path.read_bytes()[:12]
    media = "image/png" if head.startswith(b"\x89PNG") else "image/webp" if head[8:12] == b"WEBP" else "image/jpeg"
    return FileResponse(path, media_type=media, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/inspire/app/{app_id}")
def inspire_app(app_id: str):
    return _scrape(lambda: playstore.details(app_id))


def _scrape(fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001  (Play Store markup changes break the scraper now and then)
        raise HTTPException(502, f"Play Store lookup failed: {e}")


@app.post("/apps/{app_id}/revise")
def post_revise(app_id: str, body: Revise):
    _exists(app_id)
    request = body.request.strip()
    if not request:
        raise HTTPException(400, "empty request")
    if workspace.read_status(app_id)["status"] in BUSY:
        raise HTTPException(409, "app is busy")
    workspace.write_status(app_id, "created")
    emit(app_id, "status", "created")
    build.start(build.revise, app_id, request, lambda k, t: emit(app_id, k, t))
    return {"id": app_id}


@app.post("/apps/{app_id}/cancel")
def post_cancel(app_id: str):
    """Stop the running create/revise job: kills the agent or build command; a revise is rolled back."""
    _exists(app_id)
    if workspace.read_status(app_id)["status"] not in BUSY:
        raise HTTPException(409, "Nothing is running for this app.")
    emit(app_id, "build", "cancel requested")
    if not workspace.cancel(app_id):  # status left over from a backend restart: no job behind it
        workspace.write_status(app_id, "cancelled")
        emit(app_id, "status", "cancelled")
    return {"ok": True}


@app.post("/apps/{app_id}/answer")
def post_answer(app_id: str, body: Answer):
    """The user's answer to "this app wants to use AI": the paused job carries on with or without the key."""
    _exists(app_id)
    st = workspace.read_status(app_id)
    if st["status"] != "waiting":
        raise HTTPException(409, "This app is not waiting for an answer.")
    if body.use_ai and not settings.pick(st["question"]["provider"]):
        raise HTTPException(400, "Add a working key in Settings first.")
    if app_id not in workspace.JOBS:  # the backend restarted while the job was waiting
        workspace.write_status(app_id, "cancelled")
        emit(app_id, "status", "cancelled")
        raise HTTPException(409, "This build stopped while it waited. Start it again.")
    workspace.ANSWERS[app_id] = body.use_ai
    return {"ok": True}


@app.post("/apps/{app_id}/hold")
def post_hold(app_id: str):
    """"Stop and review features": the new app's job pauses once its features are known. During coding this stops
    the agent; it starts over after the review."""
    _exists(app_id)
    st = workspace.read_status(app_id)
    if app_id not in workspace.JOBS or st["status"] not in HOLDABLE or (st["status"] == "coding" and not st.get("plan")):
        raise HTTPException(409, "This build can't stop for a review now.")
    emit(app_id, "build", "feature review requested")
    workspace.hold(app_id, stop_agent=st["status"] == "coding")
    return {"ok": True}


@app.post("/apps/{app_id}/plan")
def post_plan(app_id: str, body: Plan):
    """The features the user confirmed: the paused job writes the code for exactly these."""
    _exists(app_id)
    if workspace.read_status(app_id)["status"] != "reviewing":
        raise HTTPException(409, "This app is not waiting for a feature review.")
    features = [f.strip()[:120] for f in body.features if f.strip()][:20]
    if not features:
        raise HTTPException(400, "Keep at least one feature.")
    if app_id not in workspace.JOBS:  # the backend restarted while the job was waiting
        workspace.write_status(app_id, "cancelled")
        emit(app_id, "status", "cancelled")
        raise HTTPException(409, "This build stopped while it waited. Start it again.")
    workspace.PLANS[app_id] = {"name": body.name.strip()[:40], "features": features,
                               "extras": [e.strip()[:120] for e in body.extras if e.strip()][:10]}
    return {"ok": True}


@app.get("/apps/{app_id}/events")
async def events(app_id: str):
    _exists(app_id)

    async def gen():
        sent = 0
        while True:
            evs = _events(app_id)
            for ev in evs[sent:]:
                yield {"event": ev["kind"], "data": ev["text"]}
            sent = len(evs)
            status = workspace.read_status(app_id)["status"]
            if status in TERMINAL and sent == len(_events(app_id)):
                yield {"event": "end", "data": status}
                return
            await asyncio.sleep(0.3)

    return EventSourceResponse(gen())


@app.post("/apps/{app_id}/deploy")
def deploy(app_id: str, body: Deploy):
    app_dir = _exists(app_id)
    vibe = workspace.read_vibe(app_id)
    if workspace.read_status(app_id).get("status") in BUSY:
        raise HTTPException(409, "The app is still building.")
    artifact = build.artifact_path(app_dir)
    if not artifact.exists():
        raise HTTPException(409, "Build the app before installing it.")
    device = next((d for d in devices.list_devices() if d["serial"] == body.serial and d["state"] == "device"), None)
    if device is None:
        raise HTTPException(400, "Connect and unlock the selected device first.")
    platform = vibe.get("platform", "android")
    if device["platform"] != platform or (platform == "ios" and device["kind"] != vibe.get("ios_target", "device")):
        raise HTTPException(400, "This build is for a different platform or device type.")
    package = workspace.package_name(app_id)
    emit(app_id, "deploy", f"installing on {body.serial}")
    try:
        if platform == "ios":
            ios.install(device, artifact)
            ios.launch(device, package)
            time.sleep(3)
            captured = ios.screenshot(device, app_dir / "screenshot.png")
            emit(app_id, "deploy", "installed and launched" + (", screenshot taken" if captured else "; device screenshots are available in Xcode"))
        else:
            devices.install(body.serial, artifact)
            devices.launch(body.serial, package)
            time.sleep(3)
            captured = devices.screenshot(body.serial, app_dir / "screenshot.png", package)
            emit(app_id, "deploy", "installed and launched" + (", screenshot taken" if captured else "; no screenshot (the app was not in front, e.g. phone locked or notifications open)"))
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        emit(app_id, "deploy", f"install failed: {e}")
        detail = str(e)
        if platform == "ios" and "explicitly trusted" in detail:
            detail = "iOS blocked launch. Trust your developer profile in Settings → General → VPN & Device Management, then try again."
        elif platform == "ios" and "locked" in detail.lower():
            detail = "Unlock your iPhone or iPad and try installing again."
        raise HTTPException(502, detail)

    return {"ok": True, "package": package}


@app.get("/apps/{app_id}/permissions")
def permissions(app_id: str):
    _exists(app_id)
    return build.permissions(app_id)


@app.get("/apps/{app_id}/screenshot.png")
def screenshot(app_id: str):
    p = _exists(app_id) / "screenshot.png"
    if not p.exists():
        raise HTTPException(404, "no screenshot")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.post("/apps/{app_id}/preview")
def make_preview(app_id: str):
    """Build the browser preview for an app that has none (older apps); blocks ~40 s."""
    app_dir = _exists(app_id)
    if workspace.read_status(app_id).get("status") in BUSY:
        raise HTTPException(409, "app is busy")
    build.export_preview(app_dir, lambda k, t: emit(app_id, k, t))
    return {"preview": (app_dir / "dist" / "index.html").exists()}


@app.get("/apps/{app_id}/preview/{path:path}")
def preview(app_id: str, path: str = ""):
    """Static web export of the app (see build.export_preview); unknown paths fall back to index.html (SPA)."""
    root = (_exists(app_id) / "dist").resolve()
    p = (root / path).resolve()
    if root not in p.parents or not p.is_file():
        p = root / "index.html"
    if not p.is_file():
        raise HTTPException(404, "no preview")
    return FileResponse(p)


@app.get("/apps/{app_id}/reference/{name}")
def reference_shot(app_id: str, name: str):
    p = _exists(app_id) / "inspiration" / name
    if not re.fullmatch(r"screenshot-\d+\.png", name) or not p.exists():
        raise HTTPException(404, "no such screenshot")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


def _exists(app_id: str) -> Path:
    d = workspace.app_dir(app_id)
    if not (d / "vibe.json").exists():
        raise HTTPException(404, "unknown app")
    return d
