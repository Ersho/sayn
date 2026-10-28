"""Android devices via adbutils, falling back to the adb binary where needed."""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import adbutils

from . import ios, workspace

ADB = str(Path(os.environ["ANDROID_HOME"]) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb"))
KNOWN = workspace.ROOT / "phones.json"  # {serial: {model, first_seen, last_seen}}: every device ever plugged in; optional "name" is the user's label
client = adbutils.AdbClient()
lock = threading.Lock()  # /devices and /apps poll concurrently; unsynced read-modify-write lost renames
# USB vendor ids of phone makers. A phone the OS sees but adb does not has USB debugging off;
# the brand picks the right "turn on developer access" steps in the dashboard.
VENDORS = {0x18D1: "google", 0x04E8: "samsung", 0x2717: "xiaomi", 0x2A70: "oneplus", 0x22D9: "oppo", 0x2D95: "vivo",
           0x22B8: "motorola", 0x12D1: "huawei", 0x339B: "honor", 0x0FCE: "sony", 0x1004: "lg", 0x2E04: "nokia",
           0x19D2: "zte", 0x05AC: "apple"}
GENERIC = re.compile(r"composite|adb|interface|usb device|input|^mtp|^android$|apple mobile device", re.I)


def list_devices(usb: bool = False) -> list[dict]:
    """adb and Xcode devices, merged with phones.json; usb=True adds phones only the OS sees (dashboard polling)."""
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
    merged = _remember(out + ios.list_devices())
    if not usb:
        return merged
    seen = {d["serial"] for d in merged if d["state"] != "offline"}
    for p in usb_phones():
        if p["serial"] in seen or (p["brand"] == "apple" and ios.available()):
            continue  # adb or Xcode already reports it
        known = next((d for d in merged if d["serial"] == p["serial"]), None)
        if known:  # e.g. a phone set up before whose debugging got switched off by an update
            known.update(state=p["state"], brand=p["brand"])
        else:
            merged.insert(0, {**p, "platform": "ios" if p["brand"] == "apple" else "android", "kind": "device",
                              "name": "", "first_seen": time.time(), "last_seen": time.time()})
    return merged


def usb_phones() -> list[dict]:
    """Phones plugged in over USB as the OS sees them: [{serial, brand, model, state}].

    state is "usb" (USB debugging off) or "driver" (Windows sees the phone's debugging interface but has no driver
    for it, common on Samsung). serial is the USB serial number, which Android also uses as its adb serial.
    """
    try:
        if os.name == "nt":
            found = _usb_windows()
        elif sys.platform == "darwin":
            found = _usb_mac()
        else:
            found = _usb_linux()
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    out = []
    for f in found:
        brand = VENDORS.get(f["vid"])
        if not brand or (brand == "apple" and not 0x1290 <= f["pid"] <= 0x12AF):  # Apple: iPhone/iPad ids only
            continue
        names = [n for n in f["names"] if n and not GENERIC.search(n)]
        out.append({"serial": f["serial"] or f"usb-{f['vid']:04x}-{f['pid']:04x}", "brand": brand,
                    "model": names[0] if names else "", "state": "driver" if f.get("adb") else "usb"})
    return out


def _usb_windows() -> list[dict]:
    # pnputil answers in ~50 ms (PowerShell's Get-PnpDevice takes over a second). Field labels are localized,
    # so read by position: "Instance ID" then "Device Description", and later a status containing "Problem".
    r = subprocess.run(["pnputil", "/enum-devices", "/connected", "/bus", "USB"], capture_output=True, text=True,
                       timeout=10, encoding="utf-8", errors="replace")
    devs: dict[str, dict] = {}
    for block in r.stdout.split("\n\n"):
        values = [line.split(":", 1)[1].strip() for line in block.splitlines() if ":" in line]
        m = re.match(r"USB\\VID_([0-9A-F]{4})&PID_([0-9A-F]{4})(&MI_\d+)?\\(.+)", values[0] if values else "", re.I)
        if not m:
            continue
        vid, pid, child, tail = int(m[1], 16), int(m[2], 16), m[3], m[4]
        d = devs.setdefault(f"{vid}:{pid}", {"vid": vid, "pid": pid, "serial": "", "names": [], "adb": False})
        desc = values[1] if len(values) > 1 else ""
        d["names"].append(desc)
        if not child and "&" not in tail:  # Windows makes up ids with "&" when the device has no serial number
            d["serial"] = tail
        if child and ("adb" in desc.lower() or "problem" in block.lower()):
            d["adb"] = True
    return list(devs.values())


def _usb_mac() -> list[dict]:
    r = subprocess.run(["ioreg", "-p", "IOUSB", "-l", "-w0"], capture_output=True, text=True, timeout=10)
    devs, cur = [], None
    for line in r.stdout.splitlines():
        if "+-o " in line:
            cur = {"vid": 0, "pid": 0, "serial": "", "names": []}
            devs.append(cur)
        elif cur is not None and (m := re.search(r'"(idVendor|idProduct|USB Serial Number|USB Product Name)" = "?([^"]*)"?', line)):
            key, val = m[1], m[2].strip()
            if key == "idVendor":
                cur["vid"] = int(val)
            elif key == "idProduct":
                cur["pid"] = int(val)
            elif key == "USB Serial Number":
                cur["serial"] = val
            else:
                cur["names"].append(val)
    return devs


def _usb_linux() -> list[dict]:
    devs = []
    for p in Path("/sys/bus/usb/devices").glob("*"):
        if not (p / "idVendor").exists():
            continue
        read = lambda name: (p / name).read_text().strip() if (p / name).exists() else ""
        devs.append({"vid": int(read("idVendor"), 16), "pid": int(read("idProduct"), 16), "serial": read("serial"),
                     "names": [read("product")]})
    return devs


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
    d.shell("wm dismiss-keyguard")  # only works without a PIN; screenshot() then refuses the lock screen
    d.shell("cmd statusbar collapse")
    d.app_start(package)


def screenshot(serial: str, dest: Path, package: str, wait: float = 6) -> bool:
    """Save a screenshot only while the app's own window has focus.

    Otherwise the picture would show the notification shade, lock screen or another app (private content).
    """
    d = client.device(serial)
    deadline = time.time() + wait
    while True:
        focus = d.shell("dumpsys window | grep mCurrentFocus")
        if f" {package}/" in focus:
            d.screenshot().save(dest)
            return True
        if time.time() > deadline:
            return False
        time.sleep(0.5)
