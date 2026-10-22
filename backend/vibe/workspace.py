"""Workspace layout: ~/vibeapping/{apps/<id>, config.json, vibe.jks} (%USERPROFILE%\vibeapping on Windows)."""
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
from pathlib import Path

ROOT = Path.home() / "vibeapping"
APPS = ROOT / "apps"
CONFIG = ROOT / "config.json"
REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "template"  # includes template/AGENTS.md, the instructions Codex reads inside each app

STATUS_FILE = "status.json"  # per app: {"status": ..., "error": ..., "summary": ...}


def config() -> dict:
    return json.loads(CONFIG.read_text("utf-8-sig"))


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "", name.lower())
    return s[:24] if len(s) >= 3 else ""


def new_id(name: str = "") -> str:
    base = slug(name) or f"app{secrets.token_hex(3)}"
    app_id = base
    while (APPS / app_id).exists():
        app_id = f"{base}{secrets.token_hex(2)}"
    return app_id


def app_dir(app_id: str) -> Path:
    return APPS / app_id


def create_app(app_id: str, name: str, request: str, agent: str = "codex", platform: str = "android",
               ios_target: str = "device", ios_device: str = "") -> Path:
    """Copy the template, fill placeholders, git init + commit."""
    dst = app_dir(app_id)
    shutil.copytree(TEMPLATE, dst, ignore=shutil.ignore_patterns("node_modules", ".expo", "android", "ios", ".git"))

    app_json = dst / "app.json"
    app_json.write_text(
        app_json.read_text("utf-8-sig").replace("__VIBE_ID__", app_id).replace("__VIBE_NAME__", name), "utf-8"
    )
    (dst / "vibe.json").write_text(
        json.dumps({"id": app_id, "name": name, "request": request, "agent": agent, "platform": platform,
                    "ios_target": ios_target, "ios_device": ios_device}, indent=2) + "\n", "utf-8"
    )
    write_status(app_id, "created")
    git(dst, "init", "-q")
    git(dst, "add", "-A")
    git(dst, "commit", "-q", "-m", "template", "--allow-empty")
    return dst


def install_node_modules(dst: Path) -> None:
    """Copy the template's node_modules (seconds) instead of running npm ci (half a minute)."""
    if not (dst / "node_modules").exists():
        shutil.copytree(TEMPLATE / "node_modules", dst / "node_modules", symlinks=True)


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "vibe", "GIT_AUTHOR_EMAIL": "vibe@local",
                        "GIT_COMMITTER_NAME": "vibe", "GIT_COMMITTER_EMAIL": "vibe@local"})


def commit(cwd: Path, message: str) -> None:
    git(cwd, "add", "-A")
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=cwd, capture_output=True)  # no-op if clean


class Cancelled(Exception):
    pass


JOBS: set[str] = set()  # app ids with a create/revise job running in this backend process
CANCELLED: set[str] = set()  # app ids whose job the user asked to stop
ANSWERS: dict[str, bool] = {}  # app id -> the user's "use AI?" answer, for a job paused in "waiting"
_PROCS: dict[str, subprocess.Popen] = {}  # app id -> the agent or build command running for it


def popen(app: Path, args: list[str], **kw) -> subprocess.Popen:
    """subprocess.Popen for a job step, registered so cancel() can stop it and everything it started."""
    check_cancelled(app.name)
    proc = subprocess.Popen(args, start_new_session=os.name != "nt", **kw)
    _PROCS[app.name] = proc
    if app.name in CANCELLED:  # cancel() ran while the process was starting
        _kill(proc)
    return proc


def check_cancelled(app_id: str) -> None:
    if app_id in CANCELLED:
        raise Cancelled("Cancelled")


def cancel(app_id: str) -> bool:
    """Stop the app's running job. False when no job is running here (e.g. a status left by a backend restart)."""
    if app_id not in JOBS:
        return False
    CANCELLED.add(app_id)
    if app_id in _PROCS:
        _kill(_PROCS[app_id])
    return True


def end_job(app_id: str) -> None:
    JOBS.discard(app_id)
    CANCELLED.discard(app_id)
    ANSWERS.pop(app_id, None)
    _PROCS.pop(app_id, None)


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGTERM)


def head(cwd: Path) -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def rollback(cwd: Path, rev: str) -> None:
    """Put the app's files back to commit rev; the event log and status stay as they are."""
    git(cwd, "reset", "-q", rev)
    git(cwd, "checkout", rev, "--", ".", ":(exclude)events.jsonl", ":(exclude)status.json")
    git(cwd, "clean", "-fdq")


def write_status(app_id: str, status: str, **extra) -> dict:
    data = {"status": status, **extra}
    (app_dir(app_id) / STATUS_FILE).write_text(json.dumps(data, indent=2), "utf-8")
    return data


def read_status(app_id: str) -> dict:
    p = app_dir(app_id) / STATUS_FILE
    return json.loads(p.read_text("utf-8-sig")) if p.exists() else {"status": "unknown"}


def read_vibe(app_id: str) -> dict:
    return json.loads((app_dir(app_id) / "vibe.json").read_text("utf-8-sig"))


def update_vibe(app_id: str, **fields) -> None:
    vibe = {**read_vibe(app_id), **fields}
    (app_dir(app_id) / "vibe.json").write_text(json.dumps(vibe, indent=2, ensure_ascii=False) + "\n", "utf-8")


def package_name(app_id: str) -> str:
    return f"com.vibeapping.{app_id}"


def list_apps() -> list[dict]:
    out = []
    if not APPS.exists():
        return out
    for d in sorted(APPS.iterdir(), key=lambda p: p.stat().st_ctime, reverse=True):
        if (d / "vibe.json").exists():
            out.append({**read_vibe(d.name), **read_status(d.name), "package": package_name(d.name), "platform": read_vibe(d.name).get("platform", "android"), **details(d)})
    return out


def details(d: Path) -> dict:
    """Non-technical extras for the dashboard: version, dates, history of Codex runs."""
    version = "1.0.0"
    try:
        version = json.loads((d / "app.json").read_text("utf-8-sig"))["expo"].get("version", version)
    except Exception:
        pass
    history = []
    log = subprocess.run(["git", "log", "--format=%ct|%s"], cwd=d, capture_output=True, text=True)
    for line in log.stdout.splitlines():
        ts, _, msg = line.partition("|")
        history.append({"time": int(ts), "message": msg})
    status_file = d / STATUS_FILE
    return {
        "version": version,
        "build": max(0, len(history) - 1),  # commits after the template copy = Codex runs
        "created": d.stat().st_ctime,
        "updated": status_file.stat().st_mtime if status_file.exists() else d.stat().st_mtime,
        "history": history,
        "screenshot": (d / "screenshot.png").exists(),
        "preview": (d / "dist" / "index.html").exists(),
        "reference_shots": sorted(p.name for p in (d / "inspiration").glob("screenshot-*.png")),
    }
