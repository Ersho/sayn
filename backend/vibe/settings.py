"""Settings: agent subscription checks and API keys that generated apps may use.

Keys live in ~/vibeapping/keys.json. They never leave the backend except as a masked hint; enabled,
verified keys are written to each app's .env as EXPO_PUBLIC_* variables (Expo inlines them into the APK)."""
import json
import re
import subprocess
import urllib.request
from pathlib import Path

from . import claude, workspace

KEYS_FILE = workspace.ROOT / "keys.json"

# id -> label, env var inside generated apps, verification request (url, headers)
PROVIDERS = {
    "openai": {"label": "OpenAI", "env": "EXPO_PUBLIC_OPENAI_API_KEY",
               "check": lambda k: ("https://api.openai.com/v1/models", {"Authorization": f"Bearer {k}"})},
    "anthropic": {"label": "Anthropic (Claude)", "env": "EXPO_PUBLIC_ANTHROPIC_API_KEY",
                  "check": lambda k: ("https://api.anthropic.com/v1/models",
                                      {"x-api-key": k, "anthropic-version": "2023-06-01"})},
    "gemini": {"label": "Google Gemini", "env": "EXPO_PUBLIC_GEMINI_API_KEY",
               "check": lambda k: ("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": k})},
}


def _load() -> dict:
    return json.loads(KEYS_FILE.read_text("utf-8-sig")) if KEYS_FILE.exists() else {}


def _save(data: dict) -> None:
    KEYS_FILE.write_text(json.dumps(data, indent=2), "utf-8")


def _mask(value: str) -> str:
    return f"{value[:3]}…{value[-4:]}" if len(value) > 10 else "…"


def verify(provider: str, key: str) -> tuple[bool, str]:
    url, headers = PROVIDERS[provider]["check"](key)
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15).read()
        return True, "Key works"
    except urllib.error.HTTPError as e:
        return False, "Key was rejected" if e.code in (400, 401, 403) else f"Provider answered {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, f"Could not reach the provider: {e}"


def list_keys() -> list[dict]:
    data = _load()
    return [{"id": p, "label": v["label"], "saved": p in data,
             "hint": _mask(data[p]["value"]) if p in data else None,
             "valid": data.get(p, {}).get("valid"), "message": data.get(p, {}).get("message"),
             "enabled": data.get(p, {}).get("enabled", False)} for p, v in PROVIDERS.items()]


def set_key(provider: str, value: str) -> None:
    ok, message = verify(provider, value)
    data = _load()
    data[provider] = {"value": value, "valid": ok, "message": message, "enabled": ok}  # a working key is used right away
    _save(data)


def recheck(provider: str) -> None:
    data = _load()
    ok, message = verify(provider, data[provider]["value"])
    data[provider].update(valid=ok, message=message)
    if not ok:
        data[provider]["enabled"] = False
    _save(data)


def toggle(provider: str, enabled: bool) -> None:
    data = _load()
    data[provider]["enabled"] = enabled and bool(data[provider].get("valid"))
    _save(data)


def delete_key(provider: str) -> None:
    data = _load()
    data.pop(provider, None)
    _save(data)


def _cli(args: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except Exception as e:  # noqa: BLE001
        return False, f"Not installed or not responding ({e.__class__.__name__})"
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def subscriptions() -> list[dict]:
    """Is each coding agent signed in? (This is what the agents bill against, no key needed.)"""
    ok, out = _cli(["codex", "login", "status"])
    codex = {"id": "codex", "label": "Codex (ChatGPT)", "ok": ok and "logged in" in out.lower(),
             "detail": out.splitlines()[-1] if out else "Not signed in. Run `codex login` in a terminal."}
    ok, out = _cli([claude.CLAUDE, "auth", "status"])
    try:
        info = json.loads(out)
    except ValueError:
        info = {}
    detail = (info.get("email") or "Signed in") + (f" · {info['orgName']}" if info.get("orgName") else "")
    claude = {"id": "claude", "label": "Claude Code", "ok": ok and bool(info.get("loggedIn")),
              "detail": detail if info.get("loggedIn") else "Not signed in. Run `claude auth login` in a terminal."}
    return [codex, claude]


def active_keys() -> dict[str, str]:
    """env var -> value for keys that are verified and switched on."""
    return {PROVIDERS[p]["env"]: v["value"] for p, v in _load().items()
            if p in PROVIDERS and v.get("enabled") and v.get("valid")}


def write_env(app: Path) -> list[str]:
    """Write the app's .env (git-excluded) and return the variable names it holds."""
    keys = active_keys()
    env = app / ".env"
    if keys:
        env.write_text("".join(f"{k}={v}\n" for k, v in keys.items()), "utf-8")
        exclude = app / ".git" / "info" / "exclude"
        if exclude.exists() and ".env" not in exclude.read_text("utf-8").split():
            exclude.write_text(exclude.read_text("utf-8").rstrip("\n") + "\n.env\n", "utf-8")
    elif env.exists():
        env.unlink()
    return list(keys)


def keys_block(names: list[str]) -> str:
    """Prompt text telling the agent which keys exist (never their values)."""
    if not names:
        return ""
    return ("\nThe user has set up these API keys for the app; they are available as `process.env.<NAME>` "
            "(Expo inlines `EXPO_PUBLIC_*` variables at build time): " + ", ".join(names)
            + ". Use one only if the request really needs that provider, read it through process.env, and never "
            "write a key into source files.\n")
