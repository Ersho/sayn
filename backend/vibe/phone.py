"""Look at and use the original app on the user's phone, for the agent that studies it. Run from the app folder:

    python phone.py look | tap N | tap X Y | type TEXT | scroll down|up | back | restart

Every command prints the screen afterwards: the screenshot saved to inspiration/screens/ and the numbered elements on it.
Only the app being studied is shown and driven: with another app, a store dialog or the lock screen in front, nothing
is captured or tapped. Standalone on purpose (only adbutils), so the agent can run it with the backend's Python.
"""
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import adbutils

CONFIG = Path("inspiration/phone.json")  # {serial, package}, written by the backend while the agent explores
SCREENS = Path("inspiration/screens")
ELEMENTS = SCREENS / "elements.json"  # the numbered elements of the last look, for `tap N`
MAX_ELEMENTS = 60


def main(args: list[str]) -> str:
    cfg = json.loads(CONFIG.read_text("utf-8"))
    d = adbutils.AdbClient().device(cfg["serial"])
    package = cfg["package"]
    cmd, rest = (args[0], args[1:]) if args else ("look", [])
    if cmd == "restart":
        d.app_stop(package)
        d.app_start(package)
        time.sleep(3)
        return look(d, package)
    if cmd != "look":
        if not in_front(d, package):
            return "Not done: the app is not in front. Run `restart` to open it again."
        if cmd == "tap":
            x, y = (map(int, rest) if len(rest) == 2 else element(int(rest[0])))
            d.click(x, y)
        elif cmd == "type":
            if focused_password(d):
                return "Not done: the focused field is a password field. Never type into it."
            d.send_keys(" ".join(rest))
        elif cmd == "scroll":
            w, h = d.window_size()
            start, end = (h // 4, h * 3 // 4) if rest[:1] == ["up"] else (h * 3 // 4, h // 4)  # the finger's path
            d.swipe(w // 2, start, w // 2, end, 0.4)
        elif cmd == "back":
            d.keyevent("BACK")
        else:
            return __doc__
        time.sleep(1.5)
    return look(d, package)


def in_front(d: adbutils.AdbDevice, package: str) -> bool:
    """The app's own window has focus (not the notification shade, a Play billing dialog, the lock screen or another app)."""
    return f" {package}/" in d.shell("dumpsys window | grep mCurrentFocus")


def look(d: adbutils.AdbDevice, package: str) -> str:
    if not in_front(d, package):
        return "The app is not in front (another app, a dialog or the lock screen is). Run `restart` to open it again."
    SCREENS.mkdir(parents=True, exist_ok=True)
    shot = SCREENS / f"screen-{len(list(SCREENS.glob('screen-*.png'))) + 1:02d}.png"
    d.screenshot().save(shot)
    items = elements(hierarchy(d))
    ELEMENTS.write_text(json.dumps(items), "utf-8")
    lines = [f"Screenshot: {shot.as_posix()} (open it to see the screen)"]
    for i, e in enumerate(items, 1):
        lines.append(f"[{i}] {e['label']}" + (" (tap)" if e["tap"] else ""))
    return "\n".join(lines) if items else lines[0] + "\nNo readable elements (a game or a custom-drawn screen): use the screenshot and `tap X Y`."


def hierarchy(d: adbutils.AdbDevice) -> ET.Element:
    try:
        return ET.fromstring(d.dump_hierarchy())
    except (ET.ParseError, adbutils.AdbError):  # e.g. an animation still running; the screenshot still helps
        return ET.Element("hierarchy")


def elements(root: ET.Element) -> list[dict]:
    out = []
    for n in root.iter("node"):
        text = (n.get("text") or "").strip() or (n.get("content-desc") or "").strip()
        tap = n.get("clickable") == "true" or n.get("long-clickable") == "true"
        if not text and not tap:
            continue
        m = re.findall(r"\d+", n.get("bounds", ""))
        if len(m) != 4:
            continue
        x1, y1, x2, y2 = map(int, m)
        if x2 <= x1 or y2 <= y1:
            continue
        kind = (n.get("class") or "").rsplit(".", 1)[-1]
        rid = (n.get("resource-id") or "").rsplit("/", 1)[-1]
        label = f'{kind} "{text[:80]}"' if text else kind
        out.append({"label": label + (f" id={rid}" if rid else ""), "tap": tap, "x": (x1 + x2) // 2, "y": (y1 + y2) // 2})
        if len(out) == MAX_ELEMENTS:
            break
    return out


def element(n: int) -> tuple[int, int]:
    e = json.loads(ELEMENTS.read_text("utf-8"))[n - 1]
    return e["x"], e["y"]


def focused_password(d: adbutils.AdbDevice) -> bool:
    return any(n.get("focused") == "true" and n.get("password") == "true" for n in hierarchy(d).iter("node"))


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except adbutils.AdbError as e:  # unplugged or locked mid-way: tell the agent, not a traceback
        print(f"The phone is not reachable ({e}). Stop using the phone and finish with what you have.")
