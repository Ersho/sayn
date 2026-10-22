"""Run `claude -p` (Claude Code) unattended inside an app folder and stream its events."""
import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Iterator

from . import playstore, workspace

MODEL = os.environ.get("VIBE_CLAUDE_MODEL", "")  # empty: the CLI's own default
LAST_MESSAGE = "claude-last.md"
MCP_CONFIG = "inspiration/mcp.json"
CLAUDE = "claude.cmd" if os.name == "nt" else "claude"


def command(app: Path, mcp: bool = False) -> list[str]:
    rea = []
    if mcp:  # REA's MCP server, so the agent can study inspiration/app.apk
        (app / MCP_CONFIG).write_text(json.dumps({"mcpServers": {"rea": {
            "command": playstore.npx()[0], "args": [*playstore.npx()[1], "-y", playstore.REA, "mcp"],
            "env": {"REA_JADX_MCP_JAR": str(playstore.JADX_JAR)}}}}, indent=2), "utf-8")
        rea = ["--mcp-config", MCP_CONFIG]
    return [
        CLAUDE, "-p",
        "--output-format", "stream-json", "--verbose",
        "--permission-mode", "acceptEdits",
        *rea,
        "--allowedTools", "Bash", "PowerShell", "Edit", "Write", "Read", "Glob", "Grep", *(["mcp__rea"] if mcp else []),
        *(["--model", MODEL] if MODEL else []),
    ]


def run(app: Path, prompt: str, emit: Callable[[str, str], None], mcp: bool = False) -> str:
    """Run Claude Code; emit('codex', line) per event, emit('model', name) once; return the final message. Raise on failure.
    mcp=True adds REA's MCP server (APK analysis)."""
    proc = workspace.popen(
        app, command(app, mcp), cwd=app, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1, env=playstore.agent_env() if mcp else None,
    )
    proc.stdin.write(prompt)
    proc.stdin.close()
    failed = None
    last_text = ""
    for line in proc.stdout:
        for text in _summarize(line):
            emit("codex", text)
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "system" and ev.get("model"):
            emit("model", ev["model"])  # what the CLI actually picked, even when no --model is given
        elif ev.get("type") == "assistant":
            texts = [c.get("text", "") for c in ev["message"].get("content", []) if c.get("type") == "text"]
            if any(texts):
                last_text = "\n".join(t for t in texts if t)
        elif ev.get("type") == "result":
            if ev.get("result"):
                last_text = ev["result"]
            if ev.get("is_error"):
                failed = ev.get("result") or ev.get("subtype") or "claude failed"
    proc.wait()
    if proc.returncode != 0 or failed:
        raise RuntimeError(failed or f"claude exited with {proc.returncode}")
    (app / LAST_MESSAGE).write_text(last_text, "utf-8")
    return last_text.strip()


def _summarize(line: str) -> Iterator[str]:
    """Turn a stream-json event into one readable line (or nothing)."""
    try:
        ev = json.loads(line)
    except ValueError:
        if line.strip():
            yield line.rstrip()
        return
    t = ev.get("type")
    if t == "assistant":
        for c in ev["message"].get("content", []):
            if c.get("type") == "text" and c["text"].strip():
                yield c["text"]
            elif c.get("type") == "tool_use":
                inp = c.get("input", {})
                if c["name"] in ("Bash", "PowerShell"):
                    yield f"$ {inp.get('command', '')}"
                elif c["name"] in ("Edit", "Write"):
                    yield f"edit {inp.get('file_path', '')}"
                else:
                    yield f"{c['name']} {inp.get('file_path') or inp.get('pattern') or ''}".rstrip()
    elif t == "user":
        for c in ev["message"].get("content", []):
            if c.get("type") == "tool_result" and c.get("is_error"):
                out = c.get("content")
                if isinstance(out, list):
                    out = "\n".join(x.get("text", "") for x in out if isinstance(x, dict))
                yield from str(out or "").strip().splitlines()[-20:]
    elif t == "result":
        if ev.get("is_error"):
            yield f"[claude error] {ev.get('result') or ev.get('subtype')}"
        else:
            usage = ev.get("usage", {})
            yield f"[claude done] tokens in={usage.get('input_tokens')} out={usage.get('output_tokens')}"
