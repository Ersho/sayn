"""Run `codex exec` unattended inside an app folder and stream its events."""
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Iterator

from . import playstore, workspace

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
The user was inspired by the Play Store app "{title}". Its store description{reviews_where} is in inspiration/listing.md and its store screenshots are inspiration/screenshot-*.png; read the listing and look at the screenshots before you start. Build your own app that serves the same purpose: cover its main features{reviews_how} and use a similar screen layout where it makes sense. No accounts, ads or payments. Apps like this usually keep their main content on their servers or behind a subscription (a library of books, a food database, lessons, recipes, plans); do not copy that content and do not shrink it to a small fixed list either: fill it as the "Content and data" section of AGENTS.md describes. Do not reuse the original's name, branding, icon, images or text: this is a new app with its own name.
"""
REVIEWS_WHERE = " and a selection of user reviews"
REVIEWS_HOW = ", keep what the reviews praise, fix what they complain about,"

INSPIRE_APK = """
The original app's APK is at inspiration/app.apk and you have the `rea` tools (inspect_android_package, search_android_classes, inspect_android_class, inspect_android_method). Before writing code, use them to learn how the original is structured: its activities and screens, navigation, data model and the features it really has. Write what you learned as a short functional spec to inspiration/spec.md (screens, features, data, and a "Content sources" section: what content the original serves from its servers or premium tier, and where your version gets each kind), then build from that spec. The APK is for understanding behaviour only: never copy code, strings, assets, package names or identifiers out of it.
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

AI_CHECK = """Do not change any files and do not run any commands; only answer. A user asked for {what}:

{request}

First think about where the app's content comes from. Many popular apps are valuable because of content they keep on their servers or behind a subscription: a library of book summaries, lessons and exercises, recipes, workout plans, a food or product database. This app cannot copy that, so it fills the gap another way:
- Facts that must be true (nutrition values, barcodes, book titles and covers, places, exchange rates) come from a free public service that needs no key or account, if a well-known one exists (for example Open Food Facts, Open Library, Wikipedia).
- Written content (summaries, explanations, lessons, exercises, plans, stories, feedback) can be written by the user's own AI on request, so the app never runs out.

Then decide:
1. Does the app need an AI model from an online API (OpenAI, Anthropic Claude or Google Gemini)? Yes when the user asked for something like chat, understanding or writing text, summarising, translating or recognising what is in a photo, and also when the AI would write the app's main content on request as described above. Ordinary app logic, storage, lists, timers, charts, reminders and phone features do not need AI.
2. Does the app need a free public data service for facts as described above? Name at most one, and only one you know exists and needs no key.

Answer with exactly these four lines and nothing else:
AI: yes or no
PROVIDER: openai, anthropic, gemini, or any (any unless the user named a provider)
WHY: one short sentence for a non-technical user saying what the AI would do in the app, starting with "to", e.g. "to write a summary of any book you add"
ONLINE: the name of the free public data service, or none"""
AI_CHECK_LISTING = """

The app is modelled on a Play Store app. Weigh its features too, especially the ones it calls AI, smart or automatic, and the content it serves. Its store listing:

{listing}

Now answer with exactly the four lines described above."""
AI_CHECK_CREATE = "this phone app"
AI_CHECK_REVISE = "this change to their existing phone app"


def parse_ai_check(answer: str) -> tuple[bool, str, str, str]:
    """(needs AI, provider or "any", why, online service or "") from the AI_CHECK answer; anything unreadable counts
    as no AI and no service."""
    need = re.search(r"^\W*AI\W*:\W*(yes|no)", answer, re.I | re.M)
    provider = re.search(r"^\W*PROVIDER\W*:\W*(openai|anthropic|gemini|any)", answer, re.I | re.M)
    why = re.search(r"^\W*WHY\W*:\s*(.+)", answer, re.I | re.M)
    online = re.search(r"^\W*ONLINE\W*:\s*(.+)", answer, re.I | re.M)
    service = online.group(1).strip().strip("*`\".") if online else ""
    return (bool(need and need.group(1).lower() == "yes"), provider.group(1).lower() if provider else "any",
            why.group(1).strip().strip("*`\"")[:200] if why else "",
            "" if service.lower() in ("", "none", "no", "n/a") else service[:60])


def online_block(service: str) -> str:
    """Prompt text naming the one free public data service the app may call, or none."""
    if not service:
        return "\nThis app uses no online data service. Do not call one.\n"
    return (f"\nThis app may use {service} over the internet (free, no key). Before relying on it, make one real "
            "request to it from the command line so you use its actual response format. Save what the user looks up "
            "on the phone so it works offline afterwards. Do not call any other online data service.\n")


FIX = """Read AGENTS.md. The release build of this app failed. Here is the tail of the build output:

```
{error}
```

Fix the cause, run `npx tsc --noEmit` until it passes, and finish with one sentence saying what you changed."""


def run(app: Path, prompt: str, emit: Callable[[str, str], None], mcp: bool = False) -> str:
    """Run Codex; emit('codex', line) per event, emit('model', name) once; return the final agent message. Raise on failure.
    mcp=True adds REA's MCP server (APK analysis)."""
    proc = workspace.popen(
        app, command(app, mcp), cwd=app, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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
