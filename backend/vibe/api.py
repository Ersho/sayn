"""FastAPI app. Run: uv run uvicorn vibe.api:app --port 8000"""
import asyncio
import json
import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from . import build, devices, playstore, settings, workspace

app = FastAPI(title="vibeApping")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

TERMINAL = {"ready", "failed", "deployed", "unknown"}
BUSY = {"created", "preparing", "inspiring", "coding", "building", "fixing"}
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
    inspiration: Inspiration | None = None


class Revise(BaseModel):
    request: str


class Deploy(BaseModel):
    serial: str


class DeviceName(BaseModel):
    name: str


class KeyValue(BaseModel):
    value: str


class KeyToggle(BaseModel):
    enabled: bool


@app.get("/settings")
def get_settings():
    return {"keys": settings.list_keys()}


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


@app.post("/settings/keys/{provider}/enabled")
def enable_key(provider: str, body: KeyToggle):
    _saved(provider)
    settings.toggle(provider, body.enabled)
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
    installed = {d["serial"]: devices.installed_packages(d["serial"])
                 for d in devices.list_devices() if d["state"] == "device"}
    apps = workspace.list_apps()
    for a in apps:
        a["installed_on"] = [serial for serial, pkgs in installed.items() if a["package"] in pkgs]
        apk = build.apk_path(workspace.app_dir(a["id"]))
        a["apk"] = apk.exists()
        a["apk_mb"] = round(apk.stat().st_size / 1e6, 1) if apk.exists() else None
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
    name = body.name.strip()[:40]
    app_id = workspace.new_id(name)
    workspace.create_app(app_id, name or "New app", request, body.agent)
    emit(app_id, "status", "created")
    threading.Thread(target=build.pipeline,
                     args=(app_id, request, lambda k, t: emit(app_id, k, t), body.agent, name, inspiration),
                     daemon=True).start()
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
    threading.Thread(target=build.revise, args=(app_id, request, lambda k, t: emit(app_id, k, t)), daemon=True).start()
    return {"id": app_id}


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
    apk = build.apk_path(app_dir)
    if not apk.exists():
        raise HTTPException(409, "no APK yet")
    package = workspace.package_name(app_id)
    emit(app_id, "deploy", f"installing on {body.serial}")
    try:
        devices.install(body.serial, apk)
    except RuntimeError as e:
        emit(app_id, "deploy", f"install failed: {e}")
        raise HTTPException(502, str(e))
    devices.launch(body.serial, package)
    time.sleep(3)
    devices.screenshot(body.serial, app_dir / "screenshot.png")
    emit(app_id, "deploy", "installed, launched, screenshot taken")
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
