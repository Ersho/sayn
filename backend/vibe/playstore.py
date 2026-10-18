"""Play Store browsing (via backend/playstore/playstore.mjs) and the per-app `inspiration/` folder."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from . import workspace

SCRAPER = workspace.REPO / "backend" / "playstore" / "playstore.mjs"
TOOLS = workspace.ROOT / "tools"
REA = "rea-agents@6.7.0"  # pinned; `npx -y rea-agents@6.7.0 mcp` is the MCP server the agents get in APK mode
JADX_JAR = Path(os.environ.get("REA_JADX_MCP_JAR") or TOOLS / "jadx-headless-mcp-0.7.1-all.jar")  # setup.ps1 downloads it
APK_URL = "https://d.apkpure.net/b/APK/{package}?version=latest"
MAX_SCREENSHOTS = 6
CACHE_TTL = 24 * 3600
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) vibeApping"}

CATEGORIES = ["PRODUCTIVITY", "HEALTH_AND_FITNESS", "LIFESTYLE", "TOOLS", "EDUCATION", "FINANCE", "FOOD_AND_DRINK",
              "TRAVEL_AND_LOCAL", "HOUSE_AND_HOME", "PARENTING", "SPORTS", "WEATHER", "GAME_PUZZLE", "GAME_CASUAL", "GAME_WORD"]

_cache: dict[tuple, tuple[float, object]] = {}


def _scrape(*args: str):
    key = args
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    proc = subprocess.run(["node", str(SCRAPER), *args], capture_output=True, text=True, encoding="utf-8", timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "scraper failed")
    data = json.loads(proc.stdout)
    _cache[key] = (time.time(), data)
    return data


def top(category: str, n: int = 24) -> list[dict]:
    return _scrape("top", category, str(n))


def search(term: str, n: int = 24) -> list[dict]:
    return _scrape("search", term, str(n))


def details(app_id: str) -> dict:
    return _scrape("app", app_id)


IMAGE_HOST = "https://play-lh.googleusercontent.com/"
IMAGE_CACHE = workspace.ROOT / "cache" / "images"


def image(url: str, width: int) -> Path:
    """Fetch a Play Store image once (resized by Google via the =w<px> suffix) and return the cached file."""
    if not url.startswith(IMAGE_HOST) or "?" in url:
        raise ValueError("not a Play Store image")
    url = url.split("=")[0] + f"=w{width}"
    IMAGE_CACHE.mkdir(parents=True, exist_ok=True)
    dst = IMAGE_CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".img")
    if not dst.exists():
        _download(url, dst)
    return dst


def apk_ready() -> bool:
    return JADX_JAR.exists()


def npx() -> tuple[str, list[str]]:
    """How an MCP config should spawn npx: through cmd on Windows (npx is a .cmd), directly elsewhere."""
    return ("cmd", ["/c", "npx"]) if os.name == "nt" else ("npx", [])


def agent_env() -> dict:
    """Environment for an agent run with REA: the JADX jar location reaches the MCP server either way."""
    return {**os.environ, "REA_JADX_MCP_JAR": str(JADX_JAR)}


def request_text(info: dict, notes: str) -> str:
    """The plain-language request stored in vibe.json and shown on the card."""
    text = f'My own version of "{info["title"]}"'
    if info.get("genre"):
        text += f" ({info['genre']})"
    text += f": {info['summary'][:300]}"
    if notes:
        text += f"\n\nWhat I want different: {notes}"
    return text


def save_inspiration(app: Path, app_id: str, use_apk: bool, use_reviews: bool, emit: Callable[[str, str], None]) -> dict:
    """Write inspiration/{listing.md, listing.json, screenshot-N.png[, app.apk]} and return the stored summary."""
    info = details(app_id)
    folder = app / "inspiration"
    folder.mkdir(exist_ok=True)
    # Keep screenshots and the APK out of the app's git history.
    exclude = app / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    if not exclude.exists() or "inspiration/" not in exclude.read_text("utf-8"):
        exclude.open("a", encoding="utf-8").write("\ninspiration/\n")

    (folder / "listing.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), "utf-8")
    reviews = info["reviews"] if use_reviews else []
    good = [r["text"] for r in reviews if r["score"] >= 4][:10]
    bad = [r["text"] for r in reviews if r["score"] <= 2][:10]
    md = [f"# {info['title']}", "", f"Play Store listing of the app the user was inspired by (by {info['developer']}, "
          f"category {info.get('genre') or 'unknown'}, rating {info.get('score') or '?'}/5, {info.get('installs') or '?'} installs).", "",
          "## Store description", "", info["description"], ""]
    if good:
        md += ["## What users like (reviews with 4 to 5 stars)", "", *[f"- {t}" for t in good], ""]
    if bad:
        md += ["## What users complain about (reviews with 1 to 2 stars)", "", *[f"- {t}" for t in bad], ""]
    (folder / "listing.md").write_text("\n".join(md), "utf-8")

    shots = []
    for i, url in enumerate(info["screenshots"][:MAX_SCREENSHOTS], 1):
        dst = folder / f"screenshot-{i}.png"
        try:
            _download(url, dst)
            shots.append(dst.name)
        except Exception as e:  # noqa: BLE001
            emit("inspire", f"screenshot {i} skipped: {e}")
    emit("inspire", f"saved listing, {len(reviews)} reviews and {len(shots)} screenshots for {info['title']}")

    apk = False
    if use_apk:
        emit("inspire", f"downloading the APK of {app_id}")
        try:
            _download_apk(app_id, folder / "app.apk")
            apk = True
            emit("inspire", f"APK saved ({(folder / 'app.apk').stat().st_size / 1e6:.1f} MB)")
        except Exception as e:  # noqa: BLE001
            emit("inspire", f"APK download failed, continuing with the listing only: {e}")
    return {"appId": app_id, "title": info["title"], "icon": info["icon"], "apk": apk, "reviews": bool(reviews)}


def _download(url: str, dst: Path) -> None:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)


def _download_apk(package: str, dst: Path) -> None:
    """APKPure serves either a plain APK or an XAPK (zip with the base APK inside)."""
    if not re.fullmatch(r"[\w.]+", package):
        raise ValueError("bad package name")
    _download(APK_URL.format(package=package), dst)
    with zipfile.ZipFile(dst) as z:
        names = z.namelist()
        if "AndroidManifest.xml" in names:
            return
        base = next((n for n in names if n.endswith(".apk") and "config." not in n and "split_" not in n), None)
        if not base:
            raise RuntimeError("downloaded file is neither an APK nor an XAPK")
        tmp = dst.with_suffix(".inner")
        with z.open(base) as src, open(tmp, "wb") as f:
            shutil.copyfileobj(src, f)
    tmp.replace(dst)
