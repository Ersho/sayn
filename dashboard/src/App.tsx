import { useEffect, useRef, useState, type ReactNode } from "react";

const API = "http://localhost:8000";

type Platform = "android" | "ios";
type BuildTarget = { platform: Platform; ios_target: "device" | "simulator"; ios_device: string };
const ANDROID_TARGET: BuildTarget = { platform: "android", ios_target: "device", ios_device: "" };
// state: "device" ready, "unauthorized" waiting for Allow, "usb" plugged in with USB debugging off,
// "driver" Windows lacks the phone's USB driver, "offline" not plugged in (remembered from before)
type Device = { platform: Platform; kind: "device" | "simulator"; serial: string; model: string; name: string; state: string; brand?: string; first_seen: number; last_seen: number };
type App = {
  id: string; name: string; request: string; platform: Platform; ios_target?: "device" | "simulator"; artifact: boolean; agent?: string; model?: string; status: string; package: string;
  installed_on: string[]; apk: boolean; apk_mb: number | null; error?: string; summary?: string;
  fix_rounds?: number; version: string; build: number; created: number; updated: number;
  history: { time: number; message: string }[]; screenshot: boolean; preview: boolean; reference_shots: string[];
  inspiration?: { appId: string; title: string; icon: string; apk: boolean; reviews: boolean };
  ai_used: string[]; online?: string; question?: { why: string; provider: string; key: string | null };
  plan?: Plan; held?: boolean; features?: string[];
};
type Plan = { name: string; features: string[]; extras: string[] };
type StoreApp = {
  appId: string; title: string; developer: string; icon: string; score: number | null; installs: string | null;
  genre: string | null; summary: string;
};
type StoreDetails = StoreApp & { description: string; screenshots: string[]; url: string; reviews: { score: number; text: string }[] };
type View = "apps" | "devices" | "inspire" | "new" | "settings";
type KeyInfo = { id: string; label: string; saved: boolean; hint: string | null; valid: boolean | null; message: string | null };
type Subscription = { id: string; label: string; ok: boolean; detail: string };
type IosCheck = { id: string; label: string; ok: boolean; hint: string };
type IosTeam = { id: string; name: string; personal: boolean };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

/** Play Store images go through the backend, which caches them on disk (Google rate-limits direct hotlinking). */
const storeImg = (url: string, w: number) => `${API}/inspire/image?u=${encodeURIComponent(url)}&w=${w}`;

const fmtDate = (t: number) =>
  new Date(t * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function ago(t: number) {
  const s = Date.now() / 1000 - t;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  if (d < 7) return `${d} day${d > 1 ? "s" : ""} ago`;
  const w = Math.floor(d / 7);
  return w < 5 ? `${w} week${w > 1 ? "s" : ""} ago` : fmtDate(t);
}

const STATUS_LABEL: Record<string, string> = {
  created: "Queued", preparing: "Preparing", inspiring: "Studying the original", checking: "Understanding features",
  waiting: "Needs your answer", reviewing: "Waiting for your review", coding: "Writing code", building: "Building",
  fixing: "Fixing build", ready: "Ready to install", failed: "Failed", cancelled: "Cancelled", unknown: "Imported",
};
const BUSY = new Set(["created", "preparing", "inspiring", "checking", "waiting", "reviewing", "coding", "building", "fixing"]);
const BEFORE_CODE = new Set(["created", "preparing", "inspiring", "checking", "waiting"]);
const PROVIDER_LABEL: Record<string, string> = { openai: "OpenAI", anthropic: "Anthropic (Claude)", gemini: "Google Gemini" };
const CATEGORY_LABEL: Record<string, string> = {
  PRODUCTIVITY: "Productivity", HEALTH_AND_FITNESS: "Health & fitness", LIFESTYLE: "Lifestyle", TOOLS: "Tools",
  EDUCATION: "Education", FINANCE: "Finance", FOOD_AND_DRINK: "Food & drink", TRAVEL_AND_LOCAL: "Travel",
  HOUSE_AND_HOME: "Home", PARENTING: "Parenting", SPORTS: "Sports", WEATHER: "Weather",
  GAME_PUZZLE: "Puzzle games", GAME_CASUAL: "Casual games", GAME_WORD: "Word games",
};
const AGENTS = {
  claude: { label: "Claude Code", blurb: "Thoughtful, reliable, great for polished apps." },
  codex: { label: "Codex", blurb: "Fast and versatile, ideal for iterative builds." },
};
const IDEAS = [
  { label: "Daily journal", text: "A private offline journal with a daily prompt, mood tracker, and a calendar of past entries. Warm colors and a calm, minimal design." },
  { label: "Workout tracker", text: "A workout tracker: log exercises with sets, reps and weight, see history per exercise, and a weekly summary." },
  { label: "Focus timer", text: "A focus timer with 25-minute sessions and 5-minute breaks, a daily session count, and gentle sounds when a session ends." },
];
const TONES = ["green", "lavender", "sand", "sky", "rose"];

/* ---------- icons (inline SVG, 20px grid) ---------- */
const I = {
  grid: <svg viewBox="0 0 20 20"><rect x="3" y="3" width="6" height="6" rx="1.5" /><rect x="11" y="3" width="6" height="6" rx="1.5" /><rect x="3" y="11" width="6" height="6" rx="1.5" /><rect x="11" y="11" width="6" height="6" rx="1.5" /></svg>,
  phone: <svg viewBox="0 0 20 20"><rect x="5" y="2" width="10" height="16" rx="2" /><circle cx="10" cy="15" r=".8" fill="currentColor" /></svg>,
  plus: <svg viewBox="0 0 20 20"><path d="M10 4v12M4 10h12" /></svg>,
  newfile: <svg viewBox="0 0 20 20"><path d="M11 2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7z" /><path d="M11 2v5h5M10 10v5M7.5 12.5h5" /></svg>,
  search: <svg viewBox="0 0 20 20"><circle cx="9" cy="9" r="5.5" /><path d="M13 13l4 4" /></svg>,
  pencil: <svg viewBox="0 0 20 20"><path d="M3 17l3.5-.7L16 6.8a1.5 1.5 0 0 0 0-2.1l-.7-.7a1.5 1.5 0 0 0-2.1 0L3.7 13.5z" /></svg>,
  download: <svg viewBox="0 0 20 20"><path d="M10 3v10M6 9l4 4 4-4M4 17h12" /></svg>,
  arrow: <svg viewBox="0 0 20 20"><path d="M4 10h12M11 5l5 5-5 5" /></svg>,
  check: <svg viewBox="0 0 20 20"><path d="M5 10.5l3.5 3.5L15 7" /></svg>,
  chevron: <svg viewBox="0 0 20 20"><path d="M7 5l5 5-5 5" /></svg>,
  shield: <svg viewBox="0 0 20 20"><path d="M10 2l6 2.5v5c0 4-2.6 6.6-6 8.5-3.4-1.9-6-4.5-6-8.5v-5z" /><path d="M7.5 10l2 2 3.5-3.5" /></svg>,
  android: <svg viewBox="0 0 20 20"><path d="M4 9a6 6 0 0 1 12 0v6H4z" /><path d="M6 5l-1.5-2M14 5l1.5-2" /><circle cx="8" cy="8" r=".6" fill="currentColor" /><circle cx="12" cy="8" r=".6" fill="currentColor" /></svg>,
  sprout: <svg viewBox="0 0 20 20"><path d="M10 17v-7" /><path d="M10 10c0-3 2-5 6-5 0 3-2 5-6 5zM10 12c0-2.5-1.5-4-5-4 0 2.5 1.5 4 5 4z" /></svg>,
  claude: <svg viewBox="0 0 20 20"><path d="M10 3v14M3 10h14M5 5l10 10M15 5L5 15" /></svg>,
  codex: <svg viewBox="0 0 20 20"><path d="M10 2.5l6.5 3.75v7.5L10 17.5l-6.5-3.75v-7.5z" /><path d="M10 6.5l3 1.75v3.5L10 13.5l-3-1.75v-3.5z" /></svg>,
  bulb: <svg viewBox="0 0 20 20"><path d="M7 14.5a5.5 5.5 0 1 1 6 0V16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1z" /><path d="M8.5 18.5h3" /></svg>,
  globe: <svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="7.5" /><path d="M2.5 10h15M10 2.5c2.2 2.2 2.2 12.8 0 15M10 2.5c-2.2 2.2-2.2 12.8 0 15" /></svg>,
  gear: <svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="2.5" /><path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4" /></svg>,
  pause: <svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="7.5" /><path d="M8.25 7v6M11.75 7v6" /></svg>,
  star: <svg viewBox="0 0 20 20"><path d="M10 2.5l2.3 4.8 5.2.7-3.8 3.6.9 5.2L10 14.3l-4.6 2.5.9-5.2L2.5 8l5.2-.7z" fill="currentColor" /></svg>,
  hand: <svg viewBox="0 0 20 20"><path d="M7 10V4.5a1.25 1.25 0 0 1 2.5 0V9M9.5 8.5v-5a1.25 1.25 0 0 1 2.5 0v5M12 9V5a1.25 1.25 0 0 1 2.5 0v6.5c0 3.3-2.2 5.5-5 5.5-2 0-3.2-1-4.3-2.6L3.6 11.8a1.2 1.2 0 0 1 1.9-1.5L7 12" /></svg>,
};
const Icon = ({ i, className }: { i: ReactNode; className?: string }) => <span className={`ic ${className ?? ""}`}>{i}</span>;

/* ---------- data hooks ---------- */
function useDevices() {
  const [devices, setDevices] = useState<Device[]>([]);
  useEffect(() => {
    const load = () => api<Device[]>("/devices").then(setDevices).catch(() => setDevices([]));
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);
  return devices;
}

function useApps() {
  const [apps, setApps] = useState<App[]>([]);
  const load = () => api<App[]>("/apps").then(setApps).catch(console.error);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);
  return { apps, reload: load };
}

/** Follows one app's SSE stream while a job runs; returns the latest status and the technical log. */
function useJob(id: string, reload: () => void) {
  const [log, setLog] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  useEffect(() => {
    if (!id) return;
    setLog([]); setStatus("created");
    const es = new EventSource(`${API}/apps/${id}/events`);
    const add = (prefix: string) => (e: MessageEvent) => setLog((l) => [...l, prefix + e.data]);
    es.addEventListener("codex", add("agent  | "));
    es.addEventListener("build", add("build  | "));
    es.addEventListener("deploy", add("deploy | "));
    es.addEventListener("status", (e) => { setStatus(e.data); setLog((l) => [...l, `status | ${e.data}`]); reload(); });
    es.addEventListener("end", () => { es.close(); reload(); });
    es.onerror = () => es.close();
    return () => es.close();
  }, [id]);
  return { log, status };
}

/* ---------- small pieces ---------- */
function Badge({ status }: { status: string }) {
  const busy = BUSY.has(status) && status !== "waiting" && status !== "reviewing";
  return (
    <span className={`badge badge-${busy ? "busy" : status}`}>
      {status === "ready" ? <Icon i={I.check} /> : busy ? <span className="dot" /> : null}
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

function Progress({ status, log, inspired }: { status: string; log: string[]; inspired?: boolean }) {
  const [showLog, setShowLog] = useState(false);
  const logRef = useRef<HTMLPreElement>(null);
  useEffect(() => { if (showLog) logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [log, showLog]);
  const keys = ["preparing", ...(inspired ? ["inspiring"] : []), "checking", "coding", "building", "ready"];
  const label: Record<string, string> = {
    preparing: "Preparing project", inspiring: "Studying the original app",
    checking: status === "waiting" ? "Waiting for your answer" : status === "reviewing" ? "Waiting for your review" : "Understanding the features",
    coding: "Writing the code",
    building: status === "fixing" ? "Fixing the build" : "Building the app", ready: "Ready to install",
  };
  const steps = keys.map((k) => label[k]);
  const idx = keys.indexOf(status === "fixing" ? "building" : status === "waiting" || status === "reviewing" ? "checking" : status);
  return (
    <div className="progress">
      <ol className="steps">
        {steps.map((label, i) => (
          <li key={i} className={i < idx || status === "ready" ? "done" : i === idx ? "active" : ""}>
            <span className="step-dot">{i < idx || status === "ready" ? <Icon i={I.check} /> : i + 1}</span>{label}
          </li>
        ))}
      </ol>
      {status === "failed" && <p className="error">The build failed after several fix attempts. Open the app card for details.</p>}
      {status === "cancelled" && <p className="muted">You stopped this build.</p>}
      <button className="link" onClick={() => setShowLog((v) => !v)}>{showLog ? "Hide technical log" : "Show technical log"}</button>
      {showLog && <pre ref={logRef} className="log">{log.join("\n")}</pre>}
    </div>
  );
}

/** Shown while a job waits in "waiting": the app needs AI, and the user decides whether it gets a key. */
function AiQuestion({ app, reload, go }: { app: App; reload: () => void; go?: (v: View) => void }) {
  const [sending, setSending] = useState(false);
  const q = app.question;
  if (app.status !== "waiting" || !q) return null;
  const wanted = PROVIDER_LABEL[q.provider] ?? "AI";
  const answer = async (use_ai: boolean) => {
    setSending(true);
    try { await api(`/apps/${app.id}/answer`, { method: "POST", body: JSON.stringify({ use_ai }) }); }
    catch (e) { alert(String(e)); }
    setSending(false);
    reload();
  };
  return (
    <div className="ai-ask">
      <b><Icon i={I.bulb} />This app wants to use AI</b>
      {q.why && <p>It would use AI {q.why.replace(/\.$/, "")}.</p>}
      {q.key
        ? <p className="muted small">It will use your {PROVIDER_LABEL[q.key]} key. Each use is billed to your account, and the key is stored inside the app on your phone.</p>
        : <p className="muted small">You have no working {wanted} key yet. Add one in Settings and come back, or build the app without AI.</p>}
      <div className="row-end">
        <button className="outline" disabled={sending} onClick={() => answer(false)}>Build without AI</button>
        {q.key
          ? <button className="primary" disabled={sending} onClick={() => answer(true)}>Use AI</button>
          : go && <button className="primary" onClick={() => go("settings")}>Add a key in Settings</button>}
      </div>
    </div>
  );
}

/** "Stop and review features" while a new app is being made, and the review itself once the job waits in "reviewing". */
function Features({ app, reload }: { app: App; reload: () => void }) {
  const [sending, setSending] = useState(false);
  const creating = !app.history.some((h) => /^(codex|claude): create$/.test(h.message));
  const holdable = creating && (BEFORE_CODE.has(app.status) || (app.status === "coding" && !!app.plan));
  if (app.status === "reviewing" && app.plan) return <FeatureReview key={app.id} app={app} plan={app.plan} reload={reload} />;
  if (!holdable) return null;
  const hold = async () => {
    if (app.status === "coding" && !confirm("Pause writing the code to review the features? It starts again after your review.")) return;
    setSending(true);
    try { await api(`/apps/${app.id}/hold`, { method: "POST" }); }
    catch (e) { alert(String(e)); }
    setSending(false);
    reload();
  };
  const coding = app.status === "coding";
  return (
    <div className="features">
      <div className={`pause-card${app.held ? " on" : ""}`}>
        <Icon i={app.held ? I.check : I.pause} />
        <div className="grow">
          <b>{app.held ? "Pausing when the features are found" : coding ? "Pause to review the features" : "Pause when the features are found"}</b>
          <p>{app.held ? "You can review and change them before any code is written."
            : coding ? "Writing the code starts again after your review."
            : "If you don’t press it, your app is built automatically."}</p>
        </div>
        {!app.held && <button className="outline" disabled={sending} onClick={hold}>Pause</button>}
      </div>
      {app.plan && coding && (
        <details>
          <summary>{app.plan.features.length} features found</summary>
          <ul>{app.plan.features.map((f, i) => <li key={i}>{f}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

function FeatureReview({ app, plan, reload }: { app: App; plan: Plan; reload: () => void }) {
  const [name, setName] = useState(plan.name);
  const [features, setFeatures] = useState(plan.features.map((text) => ({ text, on: true })));
  const [extras, setExtras] = useState(plan.extras.map((text) => ({ text, on: false })));
  const [own, setOwn] = useState("");
  const [sending, setSending] = useState(false);
  const chosen = [...features, ...extras].filter((x) => x.on).map((x) => x.text);
  const add = () => {
    if (!own.trim()) return;
    setFeatures((l) => [...l, { text: own.trim(), on: true }]);
    setOwn("");
  };
  const build = async () => {
    setSending(true);
    try {
      await api(`/apps/${app.id}/plan`, { method: "POST", body: JSON.stringify({
        name, features: chosen, extras: [...features, ...extras].filter((x) => !x.on).map((x) => x.text) }) });
    } catch (e) { alert(String(e)); }
    setSending(false);
    reload();
  };
  const list = (items: { text: string; on: boolean }[], set: (f: (l: { text: string; on: boolean }[]) => { text: string; on: boolean }[]) => void) => (
    <ul className="checks">
      {items.map((x, i) => (
        <li key={i}><label>
          <input type="checkbox" checked={x.on} onChange={() => set((l) => l.map((y, j) => (j === i ? { ...y, on: !y.on } : y)))} />{x.text}
        </label></li>
      ))}
    </ul>
  );
  return (
    <div className="ai-ask features review">
      <b><Icon i={I.check} />Here is what your app will have</b>
      <p className="field-label">Name</p>
      <input className="name-input" value={name} maxLength={40} onChange={(e) => setName(e.target.value)} placeholder="Let the assistant pick" />
      <p className="field-label">Features</p>
      {list(features, setFeatures)}
      {extras.length > 0 && <>
        <p className="field-label">You could also add</p>
        {list(extras, setExtras)}
      </>}
      <div className="add-row">
        <input value={own} onChange={(e) => setOwn(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") add(); }} placeholder="Add your own feature…" maxLength={120} />
        <button className="outline" onClick={add} disabled={!own.trim()}>Add</button>
      </div>
      <div className="row-end">
        <button className="primary" disabled={sending || chosen.length === 0} onClick={build}>Build with these features <Icon i={I.arrow} /></button>
      </div>
    </div>
  );
}

function CancelButton({ app, reload }: { app: App; reload: () => void }) {
  const [stopping, setStopping] = useState(false);
  const revising = app.history.some((h) => /^(codex|claude): create$/.test(h.message));
  return (
    <button className="outline" disabled={stopping} onClick={async () => {
      const what = revising ? "Your app goes back to how it was before this change." : "The unfinished app stays in My apps.";
      if (!confirm(`Stop working on ${app.name}? ${what}`)) return;
      setStopping(true);
      try { await api(`/apps/${app.id}/cancel`, { method: "POST" }); }
      catch (e) { alert(String(e)); setStopping(false); }
      reload();
    }}>{stopping ? "Stopping…" : "Cancel build"}</button>
  );
}

function DeployButton({ app, devices, onDone, go }: { app: App; devices: Device[]; onDone: () => void; go?: (v: View) => void }) {
  const online = devices.filter((d) => d.state === "device" && d.platform === app.platform
    && (app.platform !== "ios" || d.kind === (app.ios_target || "device")));
  const [serial, setSerial] = useState("");
  const [busy, setBusy] = useState(false);
  const chosen = online.some((d) => d.serial === serial) ? serial : online[0]?.serial || "";
  const disabled = !app.artifact || BUSY.has(app.status) || online.length === 0 || busy;
  const title = BUSY.has(app.status) ? "Still building" : !app.artifact ? "Not built yet" : online.length === 0 ? "Plug in a device to install" : "";
  const installed = app.installed_on.includes(chosen);
  if (go && app.artifact && !BUSY.has(app.status) && online.length === 0 && app.platform === "android") {
    return <button className="outline" onClick={() => go("devices")}><Icon i={I.phone} />Connect a phone to install</button>;
  }
  return (
    <span className="deploy">
      {online.length > 1 && (
        <select value={chosen} onChange={(e) => setSerial(e.target.value)}>
          {online.map((d) => <option key={d.serial} value={d.serial}>{d.name || d.model || d.serial}</option>)}
        </select>
      )}
      <button className="ghost" disabled={disabled} title={title}
        onClick={async () => {
          setBusy(true);
          try { await api(`/apps/${app.id}/deploy`, { method: "POST", body: JSON.stringify({ serial: chosen }) }); }
          catch (e) { alert(String(e)); }
          setBusy(false);
          onDone();
        }}>
        <Icon i={I.download} />{busy ? "Installing…" : installed ? "Reinstall on device" : "Install on device"}
      </button>
    </span>
  );
}

function describeCommit(m: string) {
  if (m === "template") return "Started from the blank template";
  const who = m.startsWith("claude:") ? "Claude Code" : "Codex";
  if (/^(codex|claude): create$/.test(m)) return `First version written by ${who}`;
  const fix = m.match(/^(?:codex|claude): fix (\d+)/);
  if (fix) return `Build fix #${fix[1]}`;
  const rev = m.match(/^(?:codex|claude): revise: (.*)/);
  if (rev) return `Revised: ${rev[1]}`;
  return m;
}

/* ---------- app card ---------- */
function AppCard({ app, tone, devices, reload, onRevise, go }: {
  app: App; tone: string; devices: Device[]; reload: () => void; onRevise: (app: App) => void; go: (v: View) => void;
}) {
  const [history, setHistory] = useState(false);
  const [shotKey, setShotKey] = useState(0);
  const [details, setDetails] = useState(false);
  const [making, setMaking] = useState(false);
  const phones = app.installed_on.map((s) => devices.find((d) => d.serial === s)?.name || devices.find((d) => d.serial === s)?.model || s);
  const busy = BUSY.has(app.status);
  return (
    <article className={`app-card tone-${tone}`}>
      <div className="hero">
        <span className="spark" />
        <div className="frame clickable" onClick={() => setDetails(true)}>
          {app.screenshot
            ? <img src={`${API}/apps/${app.id}/screenshot.png?${shotKey || app.updated}`} alt={`${app.name} on the device`} />
            : <div className="frame-empty"><span className="glyph">{app.name[0]?.toUpperCase()}</span><small>{app.name}</small></div>}
        </div>
      </div>
      <div className="body">
        <div className="title-row">
          <span className="app-icon">{app.name[0]?.toUpperCase()}</span>
          <div className="title">
            <h3>{app.name}</h3>
            <div className="meta">{app.platform === "ios" ? "iOS" : "Android"}{app.platform === "ios" && app.ios_target === "simulator" ? " Simulator" : ""} · v{app.version} · {busy ? "Working now" : `Updated ${ago(app.updated)}`}</div>
          </div>
          <Badge status={app.status} />
        </div>
        <p className="desc">{app.summary || app.request}</p>
        <button className="link" onClick={() => setDetails(true)}>Details &amp; screenshot <Icon i={I.arrow} /></button>
        {app.inspiration && (
          <p className="inspired-by"><img src={storeImg(app.inspiration.icon, 64)} alt="" />Inspired by {app.inspiration.title}{app.inspiration.apk ? " (studied the original app)" : ""}</p>
        )}
        {app.ai_used.length > 0 && <p className="uses-ai" title="Each use is billed to your API key"><Icon i={I.bulb} />Uses AI · {app.ai_used.join(", ")}</p>}
        {app.online && <p className="uses-ai" title="Free public data, looked up over the internet"><Icon i={I.globe} />Uses internet · {app.online}</p>}
        {phones.length > 0 &&<p className="installed"><Icon i={I.check} />Installed on {phones.join(", ")}</p>}
        <AiQuestion app={app} reload={reload} go={go} />
        <Features app={app} reload={reload} />
        {app.status === "failed" && <details className="fail"><summary>Build failed, show details</summary><pre>{app.error}</pre></details>}
        <button className="link" onClick={() => setHistory((v) => !v)}>Version history <Icon i={I.arrow} /></button>
        {history && (
          <ol className="history">
            {app.history.map((h, i) => <li key={i}><span className="muted">{fmtDate(h.time)}</span>{describeCommit(h.message)}</li>)}
          </ol>
        )}
        <div className="card-actions">
          {busy
            ? <CancelButton app={app} reload={reload} />
            : <button className="outline" onClick={() => onRevise(app)}><Icon i={I.pencil} />Revise app</button>}
          <DeployButton app={app} devices={devices} go={go} onDone={() => { setShotKey(Date.now()); reload(); }} />
        </div>
      </div>
      {details && (
        <div className="modal-bg" onClick={() => setDetails(false)}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <p className="eyebrow">{app.name} · v{app.version}</p>
            <h2>About this app</h2>
            <p className="field-label">Try it</p>
            {app.preview ? (
              <div className="try-frame"><iframe src={`${API}/apps/${app.id}/preview/`} title={`${app.name} preview`} /></div>
            ) : (
              <button className="outline" disabled={making || !app.artifact} onClick={async () => {
                setMaking(true);
                try { await api(`/apps/${app.id}/preview`, { method: "POST" }); reload(); }
                catch (e) { alert(String(e)); }
                setMaking(false);
              }}>{making ? "Preparing preview (about 40 s)…" : "Make a preview you can try"}</button>
            )}
            <p className="muted small">A browser preview: close to the real app, but phone features like sensors may not work.</p>
            <p className="field-label">Screenshots</p>
            {app.screenshot || app.reference_shots.length > 0 ? (
              <div className="shots">
                {app.screenshot && <img src={`${API}/apps/${app.id}/screenshot.png?${shotKey || app.updated}`} alt={`${app.name} on the device`} />}
                {app.reference_shots.map((n) => <img key={n} src={`${API}/apps/${app.id}/reference/${n}`} alt="" loading="lazy" />)}
              </div>
            ) : (
              <p className="muted">{app.platform === "ios" && app.ios_target !== "simulator" ? "For an iPhone or iPad screenshot, capture it in Xcode." : "No screenshot yet. Install the app on your device and one is taken automatically."}</p>
            )}
            {app.screenshot && app.reference_shots.length > 0 && <p className="muted small">First: your app on the device. The rest: the original app's Play Store screenshots.</p>}
            <p className="field-label">What it does</p>
            <p className="full-desc">{app.summary || app.request}</p>
            {app.features && app.features.length > 0 && (<>
              <p className="field-label">Features</p>
              <ul className="feature-list">{app.features.map((f, i) => <li key={i}>{f}</li>)}</ul>
            </>)}
            {app.summary && app.request && (<>
              <p className="field-label">Your original request</p>
              <p className="full-desc">{app.request}</p>
            </>)}
            <p className="field-label">Version history</p>
            <ol className="history">
              {app.history.map((h, i) => <li key={i}><span className="muted">{fmtDate(h.time)}</span>{describeCommit(h.message)}</li>)}
            </ol>
            <div className="row-end"><button className="outline" onClick={() => setDetails(false)}>Close</button></div>
          </div>
        </div>
      )}
    </article>
  );
}

function ReviseDialog({ app, onClose, onStarted }: { app: App; onClose: () => void; onStarted: (id: string) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <p className="eyebrow">Revise {app.name}</p>
        <h2>What should change?</h2>
        <p className="sub">Describe the change in plain language. Your assistant updates the app and builds a new version.</p>
        <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} autoFocus
          placeholder="e.g. add a dark mode and make the buttons bigger" />
        <div className="row-end">
          <button className="outline" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!text.trim() || busy} onClick={async () => {
            setBusy(true);
            try {
              await api(`/apps/${app.id}/revise`, { method: "POST", body: JSON.stringify({ request: text }) });
              onStarted(app.id);
            } catch (e) { alert(String(e)); setBusy(false); }
          }}>{busy ? "Starting…" : "Update my app"}</button>
        </div>
      </div>
    </div>
  );
}

function AgentPicker({ agent, setAgent }: { agent: keyof typeof AGENTS; setAgent: (a: keyof typeof AGENTS) => void }) {
  return (
    <>
      <p className="field-label">Choose your coding assistant</p>
      <div className="agents">
        {(Object.keys(AGENTS) as (keyof typeof AGENTS)[]).map((k) => (
          <button key={k} className={`agent ${agent === k ? "on" : ""}`} onClick={() => setAgent(k)}>
            <span className={`agent-logo ${k}`}><Icon i={I[k]} /></span>
            <span className="grow"><b>{AGENTS[k].label}</b><small>{AGENTS[k].blurb}</small></span>
            <span className="radio" />
          </button>
        ))}
      </div>
    </>
  );
}


function TargetPicker({ target, setTarget, devices }: {
  target: BuildTarget; setTarget: (target: BuildTarget) => void; devices: Device[];
}) {
  const [hosts, setHosts] = useState({ android: true, ios: false, mac: false });
  useEffect(() => {
    api<{ android?: boolean; ios: { available: boolean; mac?: boolean } }>("/settings").then((s) => {
      const android = s.android !== false; // older backends do not report it
      setHosts({ android, ios: s.ios.available, mac: !!s.ios.mac });
      // An iPhone-only Mac (setup.sh --no-android) starts on iPhone / iPad.
      if (!android && s.ios.available && target.platform === "android") setTarget({ ...target, platform: "ios" });
    }).catch(() => {});
  }, []);
  const eligible = devices.filter((d) => d.platform === "ios" && d.kind === target.ios_target && d.state === "device");
  return <>
    <label className="field">Build for
      <select aria-label="Build for" value={target.platform} onChange={(e) => setTarget({ ...target, platform: e.target.value as Platform, ios_target: "device", ios_device: "" })}>
        <option value="android" disabled={!hosts.android}>Android{!hosts.android ? " (not set up on this computer)" : ""}</option>
        <option value="ios" disabled={!hosts.ios}>iPhone / iPad{hosts.ios ? "" : hosts.mac ? " (finish setup in Settings)" : " (requires a Mac)"}</option>
      </select>
    </label>
    {target.platform === "ios" && <>
      <label className="field">Install on
        <select aria-label="Install on" value={target.ios_target} onChange={(e) => setTarget({ ...target, ios_target: e.target.value as BuildTarget["ios_target"], ios_device: "" })}>
          <option value="device">iPhone / iPad</option><option value="simulator">iOS Simulator</option>
        </select>
      </label>
      {eligible.length > 0 && <label className="field">Device
        <select aria-label="Device" value={target.ios_device || eligible[0].serial} onChange={(e) => setTarget({ ...target, ios_device: e.target.value })}>
          {eligible.map((d) => <option key={d.serial} value={d.serial}>{d.name || d.model}</option>)}
        </select>
      </label>}
      <p className="muted small">{target.ios_target === "device"
        ? "Set your Apple signing team in Settings. Connect and unlock your iPhone, trust this Mac, and enable Developer Mode."
        : "Start an iOS Simulator in Xcode before installing. Simulator builds do not need an Apple signing team."}</p>
    </>}
  </>;
}

function targetBody(target: BuildTarget, devices: Device[]): BuildTarget {
  return { ...target, ios_device: target.ios_device || (target.platform === "ios"
    ? devices.find((d) => d.platform === "ios" && d.kind === target.ios_target && d.state === "device")?.serial || "" : "") };
}

/* ---------- Play Store inspiration ---------- */
function StoreCard({ app, onPick }: { app: StoreApp; onPick: (a: StoreApp) => void }) {
  return (
    <article className="store-card">
      <div className="store-head">
        <img className="store-icon" src={storeImg(app.icon, 128)} alt="" loading="lazy" />
        <div className="title">
          <h3>{app.title}</h3>
          <div className="meta">{app.developer}{app.genre ? ` · ${app.genre}` : ""}</div>
        </div>
      </div>
      <p className="desc">{app.summary}</p>
      <div className="store-foot">
        <span className="rating">{app.score ? <><Icon i={I.star} />{app.score.toFixed(1)}</> : null}{app.installs ? <span className="muted"> · {app.installs} installs</span> : null}</span>
        <button className="outline" onClick={() => onPick(app)}><Icon i={I.bulb} />Make my own version</button>
      </div>
    </article>
  );
}

function InspirePage({ onPick }: { onPick: (a: StoreApp) => void }) {
  const [categories, setCategories] = useState<string[]>(Object.keys(CATEGORY_LABEL));
  const [category, setCategory] = useState("PRODUCTIVITY");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [apps, setApps] = useState<StoreApp[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { api<{ categories: string[] }>("/inspire").then((i) => setCategories(i.categories)).catch(() => {}); }, []);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError("");
    const p = term ? api<StoreApp[]>(`/inspire/search?q=${encodeURIComponent(term)}`) : api<StoreApp[]>(`/inspire/top/${category}`);
    p.then((a) => { if (alive) setApps(a); })
      .catch((e) => { if (alive) { setApps([]); setError(String(e)); } })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [category, term]);
  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Borrow the idea, make it yours</p>
          <h1>Popular on the Play Store.</h1>
          <p className="sub">Pick an app you like and your assistant builds your own version of it, with the changes you want.</p>
        </div>
      </header>
      <div className="toolbar">
        <div className="chips">
          {categories.map((c) => (
            <button key={c} className={`chip ${!term && category === c ? "on" : ""}`} onClick={() => { setTerm(""); setQ(""); setCategory(c); }}>
              {CATEGORY_LABEL[c] ?? c}
            </button>
          ))}
        </div>
        <form className="search" onSubmit={(e) => { e.preventDefault(); setTerm(q.trim()); }}>
          <Icon i={I.search} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the Play Store…" />
          {term && <button type="button" className="link" onClick={() => { setQ(""); setTerm(""); }}>Clear</button>}
        </form>
      </div>
      {loading ? (
        <p className="foot-note"><span className="dot" />Looking at the Play Store…</p>
      ) : error ? (
        <div className="empty-card"><h2>The Play Store did not answer.</h2><p className="sub">Try again in a moment, or search for something else.</p><p className="muted small">{error}</p></div>
      ) : apps.length === 0 ? (
        <div className="empty-card"><h2>Nothing found.</h2><p className="sub">Try another search or category.</p></div>
      ) : (
        <div className="store-cards">{apps.map((a) => <StoreCard key={a.appId} app={a} onPick={onPick} />)}</div>
      )}
      <p className="foot-note"><Icon i={I.shield} />Only the idea is borrowed. Your app gets its own name, look and code, and nothing is copied from the original.</p>
    </>
  );
}

function InspireDialog({ app, devices, onClose, onStarted }: { app: StoreApp; devices: Device[]; onClose: () => void; onStarted: (id: string) => void }) {
  const [details, setDetails] = useState<StoreDetails | null>(null);
  const [apkReady, setApkReady] = useState(false);
  const [more, setMore] = useState(false);
  const [notes, setNotes] = useState("");
  const [agent, setAgent] = useState<keyof typeof AGENTS>("claude");
  const [apk, setApk] = useState(false);
  const [reviews, setReviews] = useState(true);
  const [target, setTarget] = useState<BuildTarget>(ANDROID_TARGET);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<StoreDetails>(`/inspire/app/${app.appId}`).then(setDetails).catch(() => setDetails(null));
    api<{ apk_ready: boolean }>("/inspire").then((i) => setApkReady(i.apk_ready)).catch(() => {});
  }, [app.appId]);
  const good = details?.reviews.filter((r) => r.score >= 4).length ?? 0;
  const bad = details?.reviews.filter((r) => r.score <= 2).length ?? 0;
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="store-head">
          <img className="store-icon" src={storeImg(app.icon, 128)} alt="" />
          <div className="title">
            <p className="eyebrow">Make my own version of</p>
            <h2>{app.title}</h2>
            <div className="meta">{app.developer}{app.score ? ` · ${app.score.toFixed(1)} stars` : ""}</div>
          </div>
        </div>
        {details && details.screenshots.length > 0 && (
          <div className="shots">{details.screenshots.slice(0, 6).map((s) => <img key={s} src={storeImg(s, 480)} alt="" loading="lazy" />)}</div>
        )}
        <p className={`store-desc ${more ? "open" : ""}`}>{details?.description ?? app.summary}</p>
        {details && details.description.length > 300 && (
          <button className="link" onClick={() => setMore((v) => !v)}>{more ? "Show less" : "Read the full description"}</button>
        )}
        <label className="field">What should be different in your version? <span className="muted">(optional)</span>
          <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. simpler, offline only, a calmer design, and add a weekly summary" />
        </label>
        <label className="check">
          <input type="checkbox" checked={reviews} onChange={(e) => setReviews(e.target.checked)} />
          <span>
            <b>Learn from user reviews</b>
            <small>{details ? `Your assistant reads ${details.reviews.length} user reviews (${good} happy, ${bad} unhappy)` : "Your assistant reads user reviews"} to keep what people love and fix what they complain about. Untick to build from the description and screenshots only.</small>
          </span>
        </label>
        <label className={`check ${apkReady ? "" : "off"}`}>
          <input type="checkbox" checked={apk} disabled={!apkReady} onChange={(e) => setApk(e.target.checked)} />
          <span>
            <b>Also study the original app itself</b>
            <small>{apkReady
              ? "Downloads the app and lets your assistant look at how it is built, for a closer match of screens and features. Adds roughly 5 extra minutes."
              : "Not set up on this laptop yet. Run scripts\\setup.ps1 again to enable it."}</small>
          </span>
        </label>
        <TargetPicker target={target} setTarget={setTarget} devices={devices} />
        <AgentPicker agent={agent} setAgent={setAgent} />
        <div className="row-end">
          <button className="outline" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={busy} onClick={async () => {
            setBusy(true);
            try {
              const r = await api<{ id: string }>("/apps", { method: "POST", body: JSON.stringify({ request: notes, agent, ...targetBody(target, devices), inspiration: { app_id: app.appId, apk, reviews } }) });
              onStarted(r.id);
            } catch (e) { alert(String(e)); setBusy(false); }
          }}>{busy ? "Starting…" : "Build my version"} <Icon i={I.arrow} /></button>
        </div>
      </div>
    </div>
  );
}

/* ---------- pages ---------- */
function AppsPage({ apps, devices, reload, go, job, onRevise }: {
  apps: App[]; devices: Device[]; reload: () => void; go: (v: View) => void; job: string; onRevise: (a: App) => void;
}) {
  const [filter, setFilter] = useState<"all" | "installed">("all");
  const [q, setQ] = useState("");
  const installed = apps.filter((a) => a.installed_on.length > 0);
  const shown = (filter === "all" ? apps : installed)
    .filter((a) => !q || (a.name + " " + a.request + " " + (a.summary ?? "")).toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Your personal app studio</p>
          <h1>My apps</h1>
        </div>
        <button className="primary big" onClick={() => go("new")}><Icon i={I.plus} />New app</button>
      </header>
      <div className="toolbar">
        <div className="segmented">
          <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>All apps ({apps.length})</button>
          <button className={filter === "installed" ? "on" : ""} onClick={() => setFilter("installed")}>Installed ({installed.length})</button>
        </div>
        <label className="search"><Icon i={I.search} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your apps…" /></label>
      </div>
      {shown.length === 0 ? (
        <div className="empty-card">
          <h2>{apps.length === 0 ? "No apps yet." : "Nothing matches."}</h2>
          <p className="sub">{apps.length === 0 ? "Describe an idea and your assistant turns it into a mobile app." : "Try another search or filter."}</p>
          {apps.length === 0 && <button className="primary big" onClick={() => go("new")}>Create your first app <Icon i={I.arrow} /></button>}
        </div>
      ) : (
        <div className="cards">
          {shown.map((a) => (
            <AppCard key={a.id} app={a} tone={TONES[apps.indexOf(a) % TONES.length]} devices={devices} reload={reload} onRevise={onRevise} go={go} />
          ))}
        </div>
      )}
      {job && apps.find((a) => a.id === job && BUSY.has(a.status)) && (
        <p className="foot-note"><span className="dot" />An app is being built. <button className="link" onClick={() => go("new")}>Follow the progress</button></p>
      )}
      <p className="foot-note"><Icon i={I.phone} />Your apps have a life of their own. Once installed, they run without your laptop.</p>
    </>
  );
}

function DeviceName({ d }: { d: Device }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [name, setName] = useState(d.name);  // shown right after saving, before the next poll brings it back
  useEffect(() => setName(d.name), [d.name]);
  const save = async () => {
    if (!editing) return;  // Enter then blur would save twice
    setEditing(false);
    const next = text.trim();
    if (next === name) return;
    setName(next);
    try { await api(`/devices/${encodeURIComponent(d.serial)}/name`, { method: "PUT", body: JSON.stringify({ name: next }) }); }
    catch { setName(d.name); }
  };
  if (editing) {
    return <input className="name-input" autoFocus value={text} maxLength={40} placeholder={d.model || "Name this device"}
      onChange={(e) => setText(e.target.value)} onBlur={save}
      onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEditing(false); }} />;
  }
  return (
    <b>{name || d.model || "Mobile device"}
      <button className="ghost rename" title="Rename" onClick={() => { setText(name); setEditing(true); }}><Icon i={I.pencil} /></button>
    </b>
  );
}

/* ---------- connecting a phone ---------- */
// Where "Build number" hides and where Developer options appear afterwards, per maker (Settings search finds both too).
const BRANDS: Record<string, { label: string; build: string; dev: string; extra?: string }> = {
  google: { label: "Pixel", build: "Settings → About phone → Build number", dev: "Settings → System → Developer options" },
  samsung: { label: "Samsung", build: "Settings → About phone → Software information → Build number", dev: "Settings → Developer options (at the very bottom)" },
  xiaomi: { label: "Xiaomi / Redmi / POCO", build: "Settings → About phone → OS version (or MIUI version)", dev: "Settings → Additional settings → Developer options",
    extra: "Also turn on “Install via USB” in the same list. Xiaomi asks for this once." },
  oneplus: { label: "OnePlus / OPPO / realme", build: "Settings → About device → Version → Build number", dev: "Settings → System settings → Developer options" },
  vivo: { label: "vivo", build: "Settings → About phone → Software version", dev: "Settings → System management → Developer options" },
  motorola: { label: "Motorola", build: "Settings → About phone → Build number", dev: "Settings → System → Developer options" },
  huawei: { label: "Huawei / Honor", build: "Settings → About phone → Build number", dev: "Settings → System & updates → Developer options" },
  other: { label: "Other", build: "Settings → About phone → Build number (sometimes under Software information)", dev: "Settings → System → Developer options" },
};
const BRAND_OF: Record<string, string> = { oppo: "oneplus", honor: "huawei" };
const NEEDS_SETUP = ["usb", "driver", "unauthorized"];

/** The phone the guide follows: a ready one wins, then the one closest to ready. */
function guidePhone(devices: Device[]) {
  const phones = devices.filter((d) => d.kind === "device");
  return ["device", "unauthorized", "driver", "usb"].map((s) => phones.find((d) => d.state === s)).find(Boolean);
}

function ConnectGuide({ devices, go }: { devices: Device[]; go: (v: View) => void }) {
  const phone = guidePhone(devices);
  const detected = phone?.brand ? BRAND_OF[phone.brand] ?? phone.brand : "";
  const [picked, setPicked] = useState("");
  const brand = picked || (detected in BRANDS ? detected : "") || "google";
  const b = BRANDS[brand];
  const [since, setSince] = useState(Date.now());
  const step = !phone ? 0 : phone.state === "usb" || phone.state === "driver" ? 1 : phone.state === "unauthorized" ? 2 : 3;
  useEffect(() => setSince(Date.now()), [step]);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const stuck = now - since > 20000;  // after 20 s on one step, offer troubleshooting
  const name = phone ? phone.name || phone.model || (detected && BRANDS[detected] ? `${BRANDS[detected].label} phone` : "phone") : "";

  if (phone?.platform === "ios" && phone.state !== "device") {
    return (
      <section className="panel connect">
        <h2>We found an iPhone or iPad.</h2>
        <p className="sub">iPhone apps can only be built and installed from a Mac with Xcode. On this computer, sayn builds Android apps. Plug in an Android phone to continue.</p>
      </section>
    );
  }
  const live = <span className="live"><span className="dot" />{step === 0 ? "Looking for your phone" : "Watching for the next step"}</span>;
  const steps: { title: string; done: string; body: ReactNode }[] = [
    {
      title: "Plug your phone into this computer", done: `Found your ${name}`,
      body: <>
        <p>Use a USB cable and unlock your phone. We’ll notice it right away.</p>
        {stuck && <div className="hint"><b>Nothing happening?</b><ul>
          <li>Try another cable. Some cables only charge and can’t carry data.</li>
          <li>On the phone, pull down the notifications, tap “Charging this device via USB” and choose <b>File transfer</b>.</li>
          <li>Try a different USB port on this computer.</li>
        </ul></div>}
      </>,
    },
    {
      title: "Turn on developer access", done: "Developer access is on",
      body: phone?.state === "driver" ? <>
        <p>Your phone is ready, but this computer is missing its USB driver.</p>
        <ol className="substeps">
          <li>Install the driver: {brand === "samsung"
            ? <a href="https://developer.samsung.com/android-usb-driver" target="_blank" rel="noreferrer">Samsung USB driver</a>
            : <a href="https://developer.android.com/studio/run/oem-usb" target="_blank" rel="noreferrer">USB driver for your phone</a>}</li>
          <li>Unplug the phone and plug it back in.</li>
        </ol>
      </> : <>
        <p>This is a one-time switch that lets sayn install your own apps. It’s hidden, so here’s exactly where to find it{detected ? ` on your ${BRANDS[detected]?.label ?? "phone"}` : ""}:</p>
        {!detected && <div className="chips brands">
          {Object.entries(BRANDS).map(([k, v]) => <button key={k} className={`chip ${brand === k ? "on" : ""}`} onClick={() => setPicked(k)}>{v.label}</button>)}
        </div>}
        <ol className="substeps">
          <li>Open <b>{b.build}</b> and tap it <b>7 times</b>. The phone may ask for your PIN, then says “You are now a developer!”</li>
          <li>Go to <b>{b.dev}</b>. <span className="muted">Can’t find it? Type “USB debugging” in the search bar at the top of Settings.</span></li>
          <li>Turn on <b>USB debugging</b> and tap OK.</li>
        </ol>
        {b.extra && <p className="muted small">{b.extra}</p>}
        {detected && <button className="link small-link" onClick={() => setPicked(picked ? "" : "other")}>{picked ? "Show steps for my phone" : "These steps don’t match my phone"}</button>}
        {stuck && <div className="hint"><b>Already did it?</b> Unplug the phone and plug it back in.</div>}
      </>,
    },
    {
      title: "Tap “Allow” on your phone", done: "This computer is allowed",
      body: <>
        <p>Your phone now shows <b>“Allow USB debugging?”</b>. Tick <b>Always allow from this computer</b>, then tap <b>Allow</b>.</p>
        {stuck && <div className="hint"><b>Don’t see it?</b> Unlock your phone and look again, or unplug it and plug it back in.</div>}
      </>,
    },
  ];
  return (
    <section className="panel connect">
      {step === 3 ? (
        <div className="connected">
          <span className="big-check"><Icon i={I.check} /></span>
          <h2>Your {name} is ready.</h2>
          <p className="sub">Apps you make install on it with one click. You can unplug it any time; your apps keep working.</p>
          <button className="primary big" onClick={() => go("new")}>Make an app <Icon i={I.arrow} /></button>
        </div>
      ) : <>
        <div className="connect-head"><h2>Connect your phone</h2>{live}</div>
        <p className="sub">Three short steps, done once. This page updates by itself as you go.</p>
        <ol className="stepper">
          {steps.map((s, i) => (
            <li key={i} className={i < step ? "done" : i === step ? "active" : ""}>
              <span className="step-dot">{i < step ? <Icon i={I.check} /> : <Icon i={[I.phone, I.gear, I.hand][i]} />}</span>
              <div className="grow">
                <b>{i < step ? s.done : s.title}</b>
                {i === step && <div className="step-body">{s.body}</div>}
              </div>
            </li>
          ))}
        </ol>
      </>}
    </section>
  );
}

/** Shown where a phone matters but none is ready; building works without one. */
function PhoneNotice({ devices, go }: { devices: Device[]; go: (v: View) => void }) {
  if (devices.some((d) => d.platform === "android" && d.state === "device")) return null;
  const phone = guidePhone(devices);
  return (
    <div className="phone-notice">
      <Icon i={I.phone} />
      <p className="grow">{phone && NEEDS_SETUP.includes(phone.state)
        ? <><b>Your phone is plugged in but not set up yet.</b> Finish it while your app builds.</>
        : <><b>No phone connected.</b> That’s fine: you can start now and connect your phone while the app builds.</>}</p>
      <button className="link" onClick={() => go("devices")}>Connect my phone <Icon i={I.arrow} /></button>
    </div>
  );
}

const DEVICE_LABEL: Record<string, string> = {
  device: "Connected", unauthorized: "Waiting for you to tap “Allow” on the phone",
  usb: "Plugged in, developer access is off", driver: "Plugged in, needs a USB driver",
};

function PhonesPage({ devices, apps, go }: { devices: Device[]; apps: App[]; go: (v: View) => void }) {
  const online = devices.filter((d) => d.state === "device");
  const waiting = devices.filter((d) => d.state !== "device" && d.state !== "offline");
  const past = devices.filter((d) => d.state === "offline");
  const row = (d: Device) => {
    const mine = apps.filter((a) => a.installed_on.includes(d.serial));
    const label = d.state === "offline" ? `Last seen ${ago(d.last_seen)}` : DEVICE_LABEL[d.state] ?? d.state;
    return (
      <li key={d.serial} className={`phone-row ${d.state}`}>
        <span className="phone-icon"><Icon i={I.phone} /></span>
        <div className="grow">
          {d.state === "usb" || d.state === "driver" ? <b>{d.model || "Phone"}</b> : <DeviceName d={d} />}
          <div className="meta">{d.platform === "ios" ? "iOS" : "Android"} · {label}{d.serial.startsWith("usb-") ? "" : ` · serial ${d.serial}`}</div>
          {d.state === "device" && (
            <div className="meta">{mine.length ? `Apps from here: ${mine.map((a) => a.name).join(", ")}` : "No sayn apps installed yet"}</div>
          )}
        </div>
        <span className={`badge badge-${d.state === "device" ? "ready" : d.state === "offline" ? "unknown" : "failed"}`}>
          {d.state === "device" ? <><Icon i={I.check} />Online</> : d.state === "offline" ? "Not connected" : "Needs attention"}
        </span>
      </li>
    );
  };
  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">The last step is the best one</p>
          <h1>Your apps. In your pocket.</h1>
          <p className="sub">Connect an Android device, iPhone, or iPad and take your creations with you.</p>
        </div>
      </header>
      <div className="two-col">
        <ConnectGuide devices={devices} go={go} />
        <aside className="panel">
          {online.length + waiting.length > 0 && (
            <>
              <h2 className="panel-title">Connected now</h2>
              <ul className="phone-list">{[...online, ...waiting].map(row)}</ul>
            </>
          )}
          {past.length > 0 && (
            <>
              <h2 className="panel-title">Previously connected</h2>
              <ul className="phone-list">{past.map(row)}</ul>
            </>
          )}
          {devices.length === 0 && (
            <div className="empty-phone">
              <div className="phone-art"><Icon i={I.phone} /><span className="plus-bubble"><Icon i={I.plus} /></span></div>
              <p className="muted">Your phones will show up here.</p>
            </div>
          )}
          <p className="muted small ios-note">Using an iPhone or iPad? That needs a Mac with Xcode; see Settings → iPhone and iPad.</p>
        </aside>
      </div>
      <p className="foot-note bar"><Icon i={I.shield} />Your apps stay yours. Installed apps run independently of your laptop.</p>
    </>
  );
}

function NewAppPage({ apps, devices, reload, job, setJob, go, onRevise }: {
  apps: App[]; devices: Device[]; reload: () => void; job: string; setJob: (id: string) => void; go: (v: View) => void; onRevise: (a: App) => void;
}) {
  const [name, setName] = useState("");
  const [request, setRequest] = useState("");
  const [target, setTarget] = useState<BuildTarget>(ANDROID_TARGET);
  const [agent, setAgent] = useState<keyof typeof AGENTS>("claude");
  const [submitting, setSubmitting] = useState(false);
  const { log, status } = useJob(job, reload);
  const app = apps.find((a) => a.id === job);
  const running = BUSY.has(status);

  const submit = async () => {
    setSubmitting(true);
    try {
      const r = await api<{ id: string }>("/apps", { method: "POST", body: JSON.stringify({ request, name, agent, ...targetBody(target, devices) }) });
      setJob(r.id);
      setName(""); setRequest("");
      reload();
    } catch (e) { alert(String(e)); }
    setSubmitting(false);
  };

  return (
    <div className="two-col new">
      <section className="panel form">
        <p className="eyebrow">From an idea to your home screen</p>
        <h1>What would you like to make?</h1>
        <p className="sub">Start with something you wish your phone could do.</p>
        <label className="field">Give it a name <span className="muted">(optional)</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Little Journal" maxLength={40} />
        </label>
        <label className="field">Describe your app
          <textarea rows={4} value={request} onChange={(e) => setRequest(e.target.value)}
            placeholder="A private offline journal with a daily prompt, mood tracker, and a calendar of past entries." />
        </label>
        <p className="field-label">Or try one of these ideas</p>
        <div className="chips">
          {IDEAS.map((i) => <button key={i.label} className="chip" onClick={() => { setRequest(i.text); if (!name) setName(i.label); }}>{i.label}</button>)}
        </div>
        <hr />
        <TargetPicker target={target} setTarget={setTarget} devices={devices} />
        {target.platform === "android" && <PhoneNotice devices={devices} go={go} />}
        <AgentPicker agent={agent} setAgent={setAgent} />
        <p className="muted small">Uses your local assistant and its usage allowance. Takes 5 to 10 minutes.</p>
        <button className="primary big wide" onClick={submit} disabled={!request.trim() || submitting || running}>
          {running ? "Working on your app…" : "Create my app"} <Icon i={I.arrow} />
        </button>
      </section>

      <aside className="side">
        {job ? (
          <section className="panel">
            <div className="title-row">
              <div className="title"><h2>{app?.name && app.name !== "New app" ? app.name : "Your new app"}</h2>
                <div className="meta">{app?.agent === "claude" ? "Claude Code" : "Codex"}{app?.model ? ` (${app.model})` : ""} is on it · {app?.platform === "ios" ? "iPhone / iPad" : "Android"}</div></div>
              <Badge status={status || app?.status || "created"} />
            </div>
            <Progress status={status || app?.status || "created"} log={log} inspired={!!app?.inspiration} />
            {app && <AiQuestion app={app} reload={reload} go={go} />}
            {app && <Features app={app} reload={reload} />}
            {app && running && <div className="row-end"><CancelButton app={app} reload={reload} /></div>}
            {app && !BUSY.has(app.status) && (
              <div className="row-end">
                <button className="outline" onClick={() => setJob("")}>Start another</button>
                <button className="primary" onClick={() => go("apps")}>See all apps <Icon i={I.arrow} /></button>
              </div>
            )}
          </section>
        ) : (
          <>
            <h2 className="pitch">You imagine it.<br />Your assistant builds it.</h2>
            <ol className="guide">
              <li><span className="num">1</span><div><b>Describe what you need</b><p>Tell us your idea in plain language. The more detail, the better.</p></div></li>
              <li><span className="num">2</span><div><b>Make it feel like you</b><p>Your assistant turns your idea into a real mobile app, tailored to your style and needs.</p></div></li>
              <li><span className="num">3</span><div><b>Take it with you</b><p>Build, refine, and install it on your phone. Your ideas, right on your home screen.</p></div></li>
            </ol>
            <div className="tip"><Icon i={I.sprout} /><div><b>Start small. Make it yours.</b><p>You don’t need to be a developer. Just bring an idea, and we’ll help you turn it into something real.</p></div></div>
          </>
        )}
        {app && app.status === "ready" && (
          <div className="cards one"><AppCard app={app} tone={TONES[apps.indexOf(app) % TONES.length]} devices={devices} reload={reload} onRevise={onRevise} go={go} /></div>
        )}
      </aside>
    </div>
  );
}

/* ---------- shell ---------- */
function SettingsPage() {
  const [iosSettings, setIosSettings] = useState<{ available: boolean; mac: boolean; team: string } | null>(null);
  const [team, setTeam] = useState("");
  const [iosChecks, setIosChecks] = useState<{ checks: IosCheck[]; teams: IosTeam[] } | null>(null);
  const checkIos = () => { setIosChecks(null); api<{ checks: IosCheck[]; teams: IosTeam[] }>("/settings/ios/checks").then(setIosChecks).catch(() => setIosChecks({ checks: [], teams: [] })); };
  useEffect(() => { if (iosSettings?.mac) checkIos(); }, [iosSettings?.mac]);
  const [subs, setSubs] = useState<Subscription[] | null>(null);
  const [keys, setKeys] = useState<KeyInfo[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const checkSubs = () => { setSubs(null); api<Subscription[]>("/settings/subscriptions").then(setSubs).catch(() => setSubs([])); };
  useEffect(() => { checkSubs(); api<{ keys: KeyInfo[]; ios: { available: boolean; mac: boolean; team: string } }>("/settings").then((r) => { setKeys(r.keys); setIosSettings(r.ios); setTeam(r.ios.team); }).catch((e) => setError(String(e))); }, []);
  const call = async (id: string, path: string, init: RequestInit) => {
    setBusy(id); setError("");
    try { setKeys((await api<{ keys: KeyInfo[] }>(path, init)).keys); }
    catch (e) { setError(String(e)); }
    setBusy("");
  };
  const post = (body: unknown) => ({ method: "POST", body: JSON.stringify(body) });
  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>Accounts and keys</h1>
          <p className="sub">Check who builds your apps, and add the keys your apps can use for AI.</p>
        </div>
      </header>
      <section className="panel">
        <div className="panel-row">
          <h2 className="panel-title">Your assistants</h2>
          <button className="ghost" onClick={checkSubs} disabled={subs === null}>Check again</button>
        </div>
        <ul className="phone-list">
          {(subs ?? []).map((s) => (
            <li key={s.id} className="phone-row">
              <span className="phone-icon"><Icon i={s.id === "claude" ? I.claude : I.codex} /></span>
              <div className="grow"><b>{s.label}</b><div className="meta">{s.detail}</div></div>
              <span className={`badge badge-${s.ok ? "ready" : "failed"}`}>{s.ok ? <><Icon i={I.check} />Signed in</> : "Not signed in"}</span>
            </li>
          ))}
          {subs === null && <li className="muted small">Checking your subscriptions…</li>}
        </ul>
        <p className="muted small">Assistants use your ChatGPT or Claude subscription, so they never need an API key here.</p>
      </section>
      {iosSettings?.mac && <section className="panel" style={{ marginTop: 20 }}>
        <div className="panel-row">
          <h2 className="panel-title">iPhone and iPad</h2>
          <button className="ghost" onClick={checkIos} disabled={iosChecks === null}>Check again</button>
        </div>
        <p className="sub">Only needed for iPhone and iPad apps. Work through the steps in order; the iOS Simulator needs only the first two.</p>
        <ul className="phone-list">
          {(iosChecks?.checks ?? []).map((c, i) => (
            <li key={c.id} className="phone-row">
              <span className="phone-icon">{i + 1}</span>
              <div className="grow"><b>{c.label}</b>{!c.ok && <div className="meta">{c.hint}</div>}</div>
              <span className={`badge badge-${c.ok ? "ready" : "failed"}`}>{c.ok ? <><Icon i={I.check} />Done</> : "To do"}</span>
            </li>
          ))}
          {iosChecks === null && <li className="muted small">Checking this Mac and your iPhone…</li>}
        </ul>
        <label className="field">Apple team ID
          <input value={team} maxLength={10} list="ios-teams" onChange={(e) => setTeam(e.target.value.toUpperCase())} placeholder="Your 10-character team ID" />
          <datalist id="ios-teams">
            {(iosChecks?.teams ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}{t.personal ? " (Personal Team)" : ""}</option>)}
          </datalist>
        </label>
        <button className="outline" disabled={busy === "ios"} onClick={async () => {
          setBusy("ios"); setError("");
          try { const result = await api<{ team: string }>("/settings/ios", { method: "PUT", body: JSON.stringify({ team }) }); setTeam(result.team); checkIos(); }
          catch (e) { setError(String(e)); }
          setBusy("");
        }}>Save signing team</button>
        <p className="muted small">A free Personal Team works; its installs expire after seven days and need rebuilding. If the first launch is blocked, trust your profile on the iPhone in Settings → General → VPN &amp; Device Management.</p>
      </section>}
      <section className="panel" style={{ marginTop: 20 }}>
        <h2 className="panel-title">API keys for your apps</h2>
        <ul className="phone-list">
          {keys.map((k) => (
            <li key={k.id} className="phone-row key-row">
              <div className="grow">
                <b>{k.label}</b>
                {k.saved ? (
                  <div className="meta">{k.hint} · {k.message}</div>
                ) : (
                  <div className="key-form">
                    <input type="password" autoComplete="off" placeholder="Paste your key" value={drafts[k.id] ?? ""}
                      onChange={(e) => setDrafts({ ...drafts, [k.id]: e.target.value })} />
                    <button className="primary" disabled={!drafts[k.id]?.trim() || busy === k.id}
                      onClick={async () => { await call(k.id, `/settings/keys/${k.id}`, { method: "PUT", body: JSON.stringify({ value: drafts[k.id] }) }); setDrafts({ ...drafts, [k.id]: "" }); }}>
                      {busy === k.id ? "Checking…" : "Save and check"}
                    </button>
                  </div>
                )}
              </div>
              {k.saved && (
                <>
                  <span className={`badge badge-${k.valid ? "ready" : "failed"}`}>{k.valid ? <><Icon i={I.check} />Works</> : "Not working"}</span>
                  <button className="ghost" disabled={busy === k.id} onClick={() => call(k.id, `/settings/keys/${k.id}/check`, post({}))}>Recheck</button>
                  <button className="ghost" disabled={busy === k.id} onClick={() => call(k.id, `/settings/keys/${k.id}`, { method: "DELETE" })}>Remove</button>
                </>
              )}
            </li>
          ))}
        </ul>
        {error && <p className="muted small">{error}</p>}
        <p className="muted small">Keys are stored only on this laptop. When an app needs AI, you are asked first; only an app you say yes to gets a key, and it ends up inside the installed app. Use keys with a spending limit.</p>
      </section>
    </>
  );
}

export default function Root() {
  const [view, setView] = useState<View>("apps");
  const [job, setJob] = useState("");          // id of the app currently being created or revised
  const [revising, setRevising] = useState<App | null>(null);
  const [inspiring, setInspiring] = useState<StoreApp | null>(null);
  const devices = useDevices();
  const { apps, reload } = useApps();
  const online = devices.filter((d) => d.state === "device").length;
  const setup = devices.some((d) => NEEDS_SETUP.includes(d.state));
  useEffect(() => {
    // First run: no phone was ever connected, so start by connecting one.
    api<Device[]>("/devices").then((d) => { if (d.length === 0) setView("devices"); }).catch(() => {});
  }, []);
  const nav: { v: View; label: ReactNode; icon: ReactNode }[] = [
    { v: "apps", label: `My apps (${apps.length})`, icon: I.grid },
    { v: "devices", label: <>Devices ({online}){online > 0 ? <span className="nav-dot ok" title="Phone connected" />
      : setup ? <span className="nav-dot warn" title="A phone needs setting up" /> : null}</>, icon: I.phone },
    { v: "inspire", label: "Get inspired", icon: I.bulb },
    { v: "new", label: "New app", icon: I.newfile },
    { v: "settings", label: "Settings", icon: I.gear },
  ];
  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="logo"><span className="logo-mark">s</span>sayn</div>
        {nav.map((n) => (
          <button key={n.v} className={view === n.v ? "on" : ""} onClick={() => setView(n.v)}><Icon i={n.icon} />{n.label}</button>
        ))}
        <div className="grow" />
        <div className="workspace"><span className="avatar">E</span>Personal workspace</div>
      </nav>
      <main>
        {view === "apps" && <AppsPage apps={apps} devices={devices} reload={reload} go={setView} job={job} onRevise={setRevising} />}
        {view === "devices" && <PhonesPage devices={devices} apps={apps} go={setView} />}
        {view === "inspire" && <InspirePage onPick={setInspiring} />}
        {view === "settings" && <SettingsPage />}
        {view === "new" && <NewAppPage apps={apps} devices={devices} reload={reload} job={job} setJob={setJob} go={setView} onRevise={setRevising} />}
      </main>
      {revising && (
        <ReviseDialog app={revising} onClose={() => setRevising(null)}
          onStarted={(id) => { setRevising(null); setJob(id); setView("new"); reload(); }} />
      )}
      {inspiring && (
        <InspireDialog app={inspiring} devices={devices} onClose={() => setInspiring(null)}
          onStarted={(id) => { setInspiring(null); setJob(id); setView("new"); reload(); }} />
      )}
    </div>
  );
}
