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


def command(app: Path, mcp: bool = False, images: list[Path] = [], web: bool = False) -> list[str]:
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
        *(["-c", 'web_search="live"'] if web else []),  # what `codex --search` turns on; exec has no such flag
        *[a for img in images for a in ("-i", str(img))],  # attached to the prompt, so the model sees them for sure
        "--skip-git-repo-check",
        "--color", "never",
        "--json",
        "-o", str(app / LAST_MESSAGE),
        "-C", str(app),
        "-",  # prompt on stdin
    ]


CREATE = """Read AGENTS.md and vibe.json. Build the app the user asked for:

{request}
{inspiration}{references}{features}
{naming} Set the name as "expo.name" in app.json. Implement the whole app, run `npx tsc --noEmit` until it passes, then finish. The first line of your final message must be `NAME: <the app name>`, followed by one short paragraph describing what the app does, written for a non-technical user. Do not mention TypeScript, code, builds or files."""

INSPIRE = """
The user was inspired by the Play Store app "{title}". Its store description{reviews_where} is in inspiration/listing.md and its store screenshots are inspiration/screenshot-*.png; read the listing and look at the screenshots before you start. Build your own app that serves the same purpose: cover its main features{reviews_how} and use a similar screen layout where it makes sense. No accounts, ads or payments. Apps like this usually keep their main content on their servers or behind a subscription (a library of books, a food database, lessons, recipes, plans); do not copy that content and do not shrink it to a small fixed list either: fill it as the "Content and data" section of AGENTS.md describes. Do not reuse the original's name, branding, icon, images or text: this is a new app with its own name.
"""
REVIEWS_WHERE = " and a selection of user reviews"
REVIEWS_HOW = ", keep what the reviews praise, fix what they complain about,"

INSPIRE_APK = """
The original app's APK is at inspiration/app.apk and you have the `rea` tools (inspect_android_package, search_android_classes, inspect_android_class, inspect_android_method). Before writing code, use them to learn how the original is structured: its activities and screens, navigation, data model and the features it really has. Write what you learned as a short functional spec to inspiration/spec.md (screens, features, data, and a "Content sources" section: what content the original serves from its servers or premium tier, and where your version gets each kind), then build from that spec. The APK is for understanding behaviour only: never copy code, strings, assets, package names or identifiers out of it.
"""


INSPIRE_SPEC = """
The original app was studied before you: inspiration/spec.md is a functional spec of it, from its APK and what people say about it online{phone}. Read it before writing code and build from it. It describes behaviour only: never copy code, strings, assets, package names or identifiers of the original.
"""
INSPIRE_SPEC_PHONE = (", plus a look through the app itself on the user's phone (screenshots in inspiration/screens/, "
                      "named in the spec; look at the ones for the screens you build)")


def inspiration_block(info: dict | None) -> str:
    if not info:
        return ""
    reviews = info.get("reviews", True)
    return (INSPIRE.format(title=info["title"], reviews_where=REVIEWS_WHERE if reviews else "",
                           reviews_how=REVIEWS_HOW if reviews else "")
            + (INSPIRE_APK if info.get("apk") else ""))


# "Make it closer to the original": a revision built from the studying step's spec (or the listing when it failed).
CLOSER = """Read AGENTS.md and vibe.json. This app already exists and works. It is the user's own version of the Play Store app "{title}", and the user wants it closer to that original: the same main screens, flows and features, arranged the way the original does it where that makes sense.
{source}
Keep everything the app already does and every change the user asked for earlier, keep its own name, and keep it free of accounts, ads and payments. Do not reuse the original's name, branding, icon, images or text. Run `npx tsc --noEmit` until it passes, then finish. Your final message must be one short paragraph describing what changed, written for a non-technical user. Do not mention TypeScript, code, builds or files."""
CLOSER_LISTING = """
The original's store description is in inspiration/listing.md and its store screenshots are inspiration/screenshot-*.png; read and look at them, and find what the app is still missing.
"""


def closer_prompt(info: dict, app: Path) -> str:
    if (app / "inspiration" / "spec.md").exists():
        phone = INSPIRE_SPEC_PHONE if any((app / "inspiration" / "screens").glob("*.png")) else ""
        source = INSPIRE_SPEC.format(phone=phone) + "Compare the spec with this app and add or change what it is missing.\n"
    else:
        source = CLOSER_LISTING
    return CLOSER.format(title=info["title"], source=source)


# The "studying" step before the check (apps inspired by a Play Store app, with its APK). It writes the spec only.
STUDY = """Read vibe.json. Do not change any app code and do not install anything; only write inspiration/spec.md. The user wants their own version of the Play Store app "{title}". Find out what that app really does, as a functional spec for building a new app:
- inspiration/listing.md (its store description{reviews}) and inspiration/screenshot-*.png (its store screenshots): read the listing and look at every screenshot.
{references}- inspiration/app.apk, with the `rea` tools (inspect_android_package, search_android_classes, inspect_android_class, inspect_android_method): its activities and screens, navigation, data model and the features it really has, including those behind a sign-in or a subscription.
- The web: search for what people say about it and how it works: Reddit, X, YouTube, review sites, its own help pages and website. Use this for features the listing only hints at, screens you cannot see, and what people love or hate about it.

Write inspiration/spec.md with these sections: Screens (each screen, what is on it, where it leads), Features, Data (what the user keeps in it), Content sources (what content the original serves from its servers or premium tier, and where a new version could get each kind), Sources (the web pages you used). Describe behaviour only: never copy code, strings, assets, package names or identifiers.

Finish with only these lines: one `MISSING: <what>` line for each important thing you still could not find out (a screen, a flow, how a main feature behaves), in a few plain words a non-technical user understands, at most 5, the most important first; or the single line `MISSING: none` when the spec covers the app well."""
STUDY_REVIEWS = " and a selection of user reviews"
STUDY_REFERENCES = "- The user's own pictures of how their version should look: {files}. Look at them too; they describe the user's wishes, not the original.\n"


def study_prompt(info: dict, app: Path) -> str:
    files = references(app)
    return STUDY.format(title=info["title"], reviews=STUDY_REVIEWS if info.get("reviews", True) else "",
                        references=STUDY_REFERENCES.format(files=", ".join(f"references/{f.name}" for f in files)) if files else "")


def parse_missing(answer: str) -> list[str]:
    found = [s.strip("*`\". ") for s in re.findall(r"^\W*MISSING\W*:\s*(.+)", answer, re.I | re.M)]
    return [s[:160] for s in found if s and s.lower() not in ("none", "nothing", "n/a")][:5]


# The "exploring" step: the original runs on the user's phone and the agent drives it with phone.py.
EXPLORE = """Read inspiration/spec.md. The Play Store app "{title}" is open on the user's phone. You can see and use it with this command, run from this folder (in PowerShell put `&` in front):

{phone} look           a screenshot (saved to inspiration/screens/) and the numbered elements on screen
{phone} tap N          tap element N of the last screen (or `tap X Y` for a spot on the screenshot)
{phone} scroll down    (or `scroll up`)
{phone} back           the phone's back button
{phone} restart        open the app again from its start screen
{phone} type TEXT      type into the selected field

Every command prints the screen after it. Open the screenshot files to see each screen. Start with `look`.

The spec still misses: {missing}. See those first, then every main screen once: tabs, menus, settings, the main add or create flows, empty states. Stop after about 60 commands.

Rules, without exception: never sign in, sign up or register; never type an email address, phone number, password, name or any other personal detail; never buy, subscribe, start a trial or tap an ad (close it); never delete, send or share anything; type only harmless sample text such as a search word. If the app asks for a permission, deny it unless the screen you need cannot be reached without it.

Then update inspiration/spec.md: add a "Seen on the phone" section with each screen you saw, its screenshot file (inspiration/screens/screen-NN.png), what is on it and where it leads, and correct the rest of the spec where the phone showed something else. You may search the web again for what you still could not see.

Finish with exactly one line: `LOGIN: <one plain sentence saying what the app asks for>` when a sign-in or registration screen stopped you from seeing what the spec misses, otherwise `DONE`."""
EXPLORE_SIGNED_IN = "\n\nThe user has just signed in on the phone themselves. Continue from the screen that is open now, with the same rules."


def explore_prompt(info: dict, missing: list[str], phone: str) -> str:
    return EXPLORE.format(title=info["title"], phone=phone, missing="; ".join(missing))


def parse_login(answer: str) -> str:
    m = re.search(r"^\W*LOGIN\W*:\s*(.+)", answer, re.I | re.M)
    return m.group(1).strip().strip("*`\"")[:200] if m else ""


REFERENCES = """
The user attached {count} picture(s) to show how the app should look: {files}. Open and look at every one of them before you start. Match their visual style: layout, spacing, colours, shapes, typography and overall mood, as far as it fits what the user asked for. They are a visual guide only: do not copy logos, brand names, icons or text from them.
"""


def references(app: Path) -> list[Path]:
    """The user's reference pictures for the current request (saved by the API to references/)."""
    return sorted((app / "references").glob("ref-*"))


def references_block(app: Path) -> str:
    files = references(app)
    if not files:
        return ""
    return REFERENCES.format(count=len(files), files=", ".join(f"references/{f.name}" for f in files))


NAME_PICK = ('Pick a plain name of one to three words that says what the app does, like "Book Ideas", "Calorie Counter" '
             'or "Video Editor": not a made-up brand and not the name of an existing app.')
NAME_GIVEN = 'The user wants the app to be called "{name}"; use exactly that name.'

REVISE = """Read AGENTS.md and vibe.json. This app already exists and works. The user asks for this change:

{request}
{references}
Implement it without breaking what is already there, run `npx tsc --noEmit` until it passes, then finish. Your final message must be one short paragraph describing what changed, written for a non-technical user. Do not mention TypeScript, code, builds or files."""

AI_CHECK = """Do not change any files and do not run any commands; only answer. A user asked for {what}:

{request}

First think about where the app's content comes from. Many popular apps are valuable because of content they keep on their servers or behind a subscription: a library of book summaries, lessons and exercises, recipes, workout plans, a food or product database. This app cannot copy that, so it fills the gap another way:
- Facts that must be true (nutrition values, barcodes, book titles and covers, places, exchange rates) come from a free public service that needs no key or account, if a well-known one exists (for example Open Food Facts, Open Library, Wikipedia).
- Written content (summaries, explanations, lessons, exercises, plans, stories, feedback) can be written by the user's own AI on request, so the app never runs out.

Then decide:
1. Does the app need an AI model from an online API (OpenAI, Anthropic Claude or Google Gemini)? Yes when the user asked for something like chat, understanding or writing text, summarising, translating or recognising what is in a photo, and also when the AI would write the app's main content on request as described above. Ordinary app logic, storage, lists, timers, charts, reminders and phone features do not need AI.
2. Does the app need a free public data service for facts as described above? Name at most one, and only one you know exists and needs no key.

Answer with exactly these lines and nothing else:
AI: yes or no
PROVIDER: openai, anthropic, gemini, or any (any unless the user named a provider)
WHY: one short sentence for a non-technical user saying what the AI would do in the app, starting with "to", e.g. "to write a summary of any book you add"
ONLINE: the name of the free public data service, or none{plan}"""
AI_CHECK_LISTING = """

The app is modelled on a Play Store app. Weigh its features too, especially the ones it calls AI, smart or automatic, and the content it serves. Its store listing:

{listing}

Now answer with exactly the lines described above."""

# Feature understanding, asked in the same call as AI_CHECK when an app is created; the user may review the list.
PLAN_ASK = """
{name}FEATURE: one feature the app will have, in a few plain words a non-technical user understands; one FEATURE line per feature, 5 to 8 of them, the most important first, covering what the user asked for
EXTRA: one feature it could also have but will not get unless the user picks it; 3 to 5 EXTRA lines"""
PLAN_NAME = """NAME: a plain name of one to three words that says what the app does, like "Book Ideas", "Calorie Counter" or "Video Editor"; not a made-up brand and not the name of an existing app
"""


def plan_ask(name_given: bool) -> str:
    return PLAN_ASK.format(name="" if name_given else PLAN_NAME)


def parse_plan(answer: str) -> dict | None:
    """{name, features, extras} from the PLAN_ASK lines; None when the answer lists no features."""
    def lines(key: str) -> list[str]:
        found = re.findall(rf"^\W*{key}\W*:\s*(.+)", answer, re.I | re.M)
        return [s.strip().strip("*`\"")[:120] for s in found if s.strip()][:10]
    features = lines("FEATURE")
    if not features:
        return None
    name = lines("NAME")
    return {"name": name[0][:40] if name else "", "features": features, "extras": lines("EXTRA")}


def features_block(features: list[str]) -> str:
    if not features:
        return ""
    return ("\nThe user confirmed that the app has these features; build all of them and keep the app focused on them:\n"
            + "".join(f"- {f}\n" for f in features))
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


def run(app: Path, prompt: str, emit: Callable[[str, str], None], mcp: bool = False, images: list[Path] = [],
        web: bool = False) -> str:
    """Run Codex; emit('codex', line) per event, emit('model', name) once; return the final agent message. Raise on failure.
    mcp=True adds REA's MCP server (APK analysis); images are attached to the prompt (-i); web=True allows web search."""
    for img in images:
        emit("codex", f"attached {img.relative_to(app).as_posix()}")
    proc = workspace.popen(
        app, command(app, mcp, images, web), cwd=app, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1, env=playstore.agent_env() if mcp else None,
    )
    proc.stdin.write(prompt)
    proc.stdin.close()
    failed = None
    emit("model", MODEL)  # codex --json does not report it, but we always pass -m
    for line in proc.stdout:
        for text in _summarize(line):
            emit("codex", text)
        ev = _event(line)
        if ev is None:
            continue
        if ev.get("type") in ("turn.failed", "error"):
            failed = ev.get("error", {}).get("message") if isinstance(ev.get("error"), dict) else ev.get("message")
    proc.wait()
    if proc.returncode != 0 or failed:
        raise RuntimeError(failed or f"codex exited with {proc.returncode}")
    last = app / LAST_MESSAGE
    return last.read_text("utf-8").strip() if last.exists() else ""


def _event(line: str) -> dict | None:
    """The JSONL event on this line, or None. Stderr is mixed in, and a stray line like `"text",` or `42` is
    valid JSON too, so only objects count."""
    try:
        ev = json.loads(line)
    except ValueError:
        return None
    return ev if isinstance(ev, dict) else None


def _summarize(line: str) -> Iterator[str]:
    """Turn a JSONL event into one readable line (or nothing)."""
    ev = _event(line)
    if ev is None:
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
        elif kind == "web_search":
            yield f"[web search] {item.get('query', '')}".rstrip()
        elif kind == "reasoning":
            yield f"[thinking] {item.get('text', '')[:200]}"
        elif kind == "error":
            yield f"[codex error] {item.get('message')}"
    elif t in ("turn.failed", "error"):
        yield f"[codex error] {json.dumps(ev.get('error') or ev.get('message'))}"
    elif t == "turn.completed":
        usage = ev.get("usage", {})
        yield f"[codex done] tokens in={usage.get('input_tokens')} out={usage.get('output_tokens')}"
