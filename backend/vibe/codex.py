"""Run `codex exec` unattended inside an app folder and stream its events."""
import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Iterator

from . import playstore

MODEL = os.environ.get("VIBE_CODEX_MODEL", "gpt-5.6-sol")  # the config.toml default is not usable on ChatGPT plans
LAST_MESSAGE = "codex-last.md"


# Outside-the-workspace dirs that `npx expo install` writes to; the sandbox blocks them otherwise.
EXTRA_WRITABLE = [Path.home() / ".expo"] + (
    [Path(os.environ["LOCALAPPDATA"]) / "npm-cache", Path(os.environ["APPDATA"]) / "npm"] if os.name == "nt"
    else [Path.home() / ".npm"])


def command(app: Path, mcp: bool = False) -> list[str]:
    add_dirs = []
    for d in EXTRA_WRITABLE:
        d.mkdir(parents=True, exist_ok=True)
        add_dirs += ["--add-dir", str(d.resolve())]
    rea = []
    if mcp:  # REA's MCP server, so the agent can study inspiration/app.apk (values are TOML)
        jar = playstore.JADX_JAR.as_posix()
        cmd, args = playstore.npx()
        rea = ["-c", f'mcp_servers.rea.command="{cmd}"',
               "-c", f'mcp_servers.rea.args={json.dumps([*args, "-y", playstore.REA, "mcp"])}',
               "-c", f'mcp_servers.rea.env={{REA_JADX_MCP_JAR="{jar}"}}',
               "-c", "mcp_servers.rea.startup_timeout_sec=90",
               "-c", "mcp_servers.rea.tool_timeout_sec=300"]
    return [
        "codex", "exec",
        "-m", MODEL,
        "-s", "workspace-write",
        "-c", "approval_policy=never",
        "-c", "sandbox_workspace_write.network_access=true",  # npx expo install needs the network
        *add_dirs, *rea,
        "--skip-git-repo-check",
        "--color", "never",
        "--json",
        "-o", str(app / LAST_MESSAGE),
        "-C", str(app),
        "-",  # prompt on stdin
    ]


CREATE = """Read AGENTS.md and vibe.json. Build the app the user asked for:

{request}
{inspiration}
{naming} Set the name as "expo.name" in app.json. Implement the whole app, run `npx tsc --noEmit` until it passes, then finish. The first line of your final message must be `NAME: <the app name>`, followed by one short paragraph describing what the app does, written for a non-technical user. Do not mention TypeScript, code, builds or files."""

INSPIRE = """
The user was inspired by the Play Store app "{title}". Its store description{reviews_where} is in inspiration/listing.md and its store screenshots are inspiration/screenshot-*.png; read the listing and look at the screenshots before you start. Build your own app that serves the same purpose: cover its main features{reviews_how} and use a similar screen layout where it makes sense. Keep it to what a small offline app can do (no accounts, servers, ads or payments). Do not reuse the original's name, branding, icon, images or text: this is a new app with its own name.
"""
REVIEWS_WHERE = " and a selection of user reviews"
REVIEWS_HOW = ", keep what the reviews praise, fix what they complain about,"

INSPIRE_APK = """
The original app's APK is at inspiration/app.apk and you have the `rea` tools (inspect_android_package, search_android_classes, inspect_android_class, inspect_android_method). Before writing code, use them to learn how the original is structured: its activities and screens, navigation, data model and the features it really has. Write what you learned as a short functional spec to inspiration/spec.md (screens, features, data), then build from that spec. The APK is for understanding behaviour only: never copy code, strings, assets, package names or identifiers out of it.
"""


def inspiration_block(info: dict | None) -> str:
    if not info:
        return ""
    reviews = info.get("reviews", True)
    return (INSPIRE.format(title=info["title"], reviews_where=REVIEWS_WHERE if reviews else "",
                           reviews_how=REVIEWS_HOW if reviews else "")
            + (INSPIRE_APK if info.get("apk") else ""))


NAME_PICK = "Pick a short, fitting app name."
NAME_GIVEN = 'The user wants the app to be called "{name}"; use exactly that name.'

REVISE = """Read AGENTS.md and vibe.json. This app already exists and works. The user asks for this change:

{request}

Implement it without breaking what is already there, run `npx tsc --noEmit` until it passes, then finish. Your final message must be one short paragraph describing what changed, written for a non-technical user. Do not mention TypeScript, code, builds or files."""

FIX = """Read AGENTS.md. The release build of this app failed. Here is the tail of the build output:

```
{error}
```

Fix the cause, run `npx tsc --noEmit` until it passes, and finish with one sentence saying what you changed."""


def run(app: Path, prompt: str, emit: Callable[[str, str], None], mcp: bool = False) -> str:
    """Run Codex; emit('codex', line) per event, emit('model', name) once; return the final agent message. Raise on failure.
    mcp=True adds REA's MCP server (APK analysis)."""
    proc = subprocess.Popen(
        command(app, mcp), cwd=app, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1, env=playstore.agent_env() if mcp else None,
    )
    proc.stdin.write(prompt)
    proc.stdin.close()
    failed = None
    emit("model", MODEL)  # codex --json does not report it, but we always pass -m
    for line in proc.stdout:
        for text in _summarize(line):
            emit("codex", text)
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") in ("turn.failed", "error"):
            failed = ev.get("error", {}).get("message") if isinstance(ev.get("error"), dict) else ev.get("message")
    proc.wait()
    if proc.returncode != 0 or failed:
        raise RuntimeError(failed or f"codex exited with {proc.returncode}")
    last = app / LAST_MESSAGE
    return last.read_text("utf-8").strip() if last.exists() else ""


def _summarize(line: str) -> Iterator[str]:
    """Turn a JSONL event into one readable line (or nothing)."""
    try:
        ev = json.loads(line)
    except ValueError:
        if line.strip():
            yield line.rstrip()
        return
    t = ev.get("type", "")
    item = ev.get("item", {})
    if t == "item.completed":
        kind = item.get("type")
        if kind == "command_execution":
            yield f"$ {item.get('command', '')}  (exit {item.get('exit_code')})"
            out = (item.get("aggregated_output") or "").strip()
            if out and item.get("exit_code") not in (0, None):
                yield from out.splitlines()[-20:]
        elif kind == "file_change":
            for ch in item.get("changes", []):
                yield f"{ch.get('kind', 'edit')} {ch.get('path')}"
        elif kind == "agent_message":
            yield item.get("text", "")
        elif kind == "reasoning":
            yield f"[thinking] {item.get('text', '')[:200]}"
        elif kind == "error":
            yield f"[codex error] {item.get('message')}"
    elif t in ("turn.failed", "error"):
        yield f"[codex error] {json.dumps(ev.get('error') or ev.get('message'))}"
    elif t == "turn.completed":
        usage = ev.get("usage", {})
        yield f"[codex done] tokens in={usage.get('input_tokens')} out={usage.get('output_tokens')}"
