"""Android devices via adbutils, falling back to the adb binary where needed."""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import adbutils

from . import ios, workspace

ADB = str(Path(os.environ["ANDROID_HOME"]) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb"))
KNOWN = workspace.ROOT / "phones.json"  # {serial: {model, first_seen, last_seen}}: every device ever plugged in; optional "name" is the user's label
client = adbutils.AdbClient()
lock = threading.Lock()  # /devices and /apps poll concurrently; unsynced read-modify-write lost renames


def list_devices() -> list[dict]:
    out = []
    try:
        infos = client.list()
    except adbutils.AdbError:
        try:
            subprocess.run([ADB, "start-server"], check=True, capture_output=True, timeout=10)
            infos = client.list()
        except (adbutils.AdbError, OSError, subprocess.SubprocessError):
            infos = []
    for info in infos:
        model = ""
        if info.state == "device":
            try:
                model = client.device(info.serial).prop.model
            except Exception:
                pass
        out.append({"serial": info.serial, "state": info.state, "model": model, "platform": "android", "kind": "device"})
    return _remember(out + ios.list_devices())


def _remember(online: list[dict]) -> list[dict]:
    """Merge the live list with phones.json; phones not plugged in come back with state 'offline'."""
    with lock:
        return _merge(online)


def _merge(online: list[dict]) -> list[dict]:
    known = json.loads(KNOWN.read_text("utf-8-sig")) if KNOWN.exists() else {}
    now = time.time()
    for d in online:
        k = known.setdefault(d["serial"], {"model": d["model"], "first_seen": now, "last_seen": now})
        k["platform"] = d.get("platform", "android")
        k["kind"] = d.get("kind", "device")
        if d["state"] != "offline":
            k["last_seen"] = now
        if d["model"]:
            k["model"] = d["model"]
    KNOWN.parent.mkdir(parents=True, exist_ok=True)
    KNOWN.write_text(json.dumps(known, indent=2), "utf-8")
    live = {d["serial"]: d for d in online}
    out = []
    for serial, k in sorted(known.items(), key=lambda kv: -kv[1]["last_seen"]):
        d = live.get(serial, {"serial": serial, "state": "offline", "model": ""})
        out.append({**d, "platform": k.get("platform", "android"), "kind": k.get("kind", "device"), "model": d["model"] or k["model"], "name": k.get("name", ""), "first_seen": k["first_seen"], "last_seen": k["last_seen"]})
    return out


def rename(serial: str, name: str) -> None:
    with lock:
        known = json.loads(KNOWN.read_text("utf-8-sig"))
        known[serial]["name"] = name
        KNOWN.write_text(json.dumps(known, indent=2), "utf-8")


def installed_packages(serial: str, platform: str = "android", kind: str = "device") -> set[str]:
    if platform == "ios":
        return ios.installed_packages({"serial": serial, "kind": kind})
    try:
        return set(client.device(serial).list_packages())
    except Exception:
        return set()


def install(serial: str, apk: Path) -> None:
    # adb binary: adbutils' install goes through a push + pm path that is slow for 60MB APKs.
    r = subprocess.run([ADB, "-s", serial, "install", "-r", str(apk)], capture_output=True, text=True)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["adb install failed"]
        err = msg[0].replace("adb.exe: ", "")
        if "INSTALL_FAILED_USER_RESTRICTED" in err:
            err += " (on Xiaomi/HyperOS phones enable 'Install via USB' in Developer options, then approve the prompt on the phone)"
        raise RuntimeError(err)


def launch(serial: str, package: str) -> None:
    d = client.device(serial)
    d.keyevent("KEYCODE_WAKEUP")
    d.shell("wm dismiss-keyguard")  # only works without a PIN; otherwise the screenshot shows the lock screen
    d.app_start(package)


def screenshot(serial: str, dest: Path) -> Path:
    client.device(serial).screenshot().save(dest)
    return dest
