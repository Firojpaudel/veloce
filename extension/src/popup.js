/* global chrome */
/**
 * Veloce popup — browser-first.
 * Order of importance: (1) the page you're on (download its video), (2) paste a link, (3) recent downloads.
 * Talks to the engine through the background worker (which adds cookies/referrers).
 * All page/remote text is rendered with textContent — never innerHTML.
 */

// ------------------------------------------------------------------ theme: apply before anything paints
const THEME_KEY = "veloce-theme";
function applyTheme(value) {
  if (value === "light" || value === "dark") document.documentElement.dataset.theme = value;
  else delete document.documentElement.dataset.theme;
}
try { applyTheme(localStorage.getItem(THEME_KEY) || "system"); } catch { /* storage blocked */ }

// ------------------------------------------------------------------ icons (Lucide-style, MIT)
const ICONS = {
  download: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"],
  folder: ["M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"],
  settings: ["M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"],
  "app-window": ["M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", "M2 9h20", "M6 6.5h.01", "M9 6.5h.01"],
  back: ["M15 18l-6-6 6-6"],
  sun: ["M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z", "M12 2v2", "M12 20v2", "M4.93 4.93l1.41 1.41", "M17.66 17.66l1.41 1.41", "M2 12h2", "M20 12h2", "M6.34 17.66l-1.41 1.41", "M19.07 4.93l-1.41 1.41"],
  moon: ["M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"],
  monitor: ["M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", "M8 21h8", "M12 17v4"],
  link: ["M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71", "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"],
  clipboard: ["M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2", "M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"],
  copy: ["M8 8h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z", "M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"],
  power: ["M12 2v10", "M18.36 6.64a9 9 0 1 1-12.73 0"],
  pause: ["M8 5v14", "M16 5v14"],
  play: ["M7 4l13 8-13 8V4z"],
  retry: ["M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", "M3 3v5h5"],
  x: ["M18 6 6 18", "M6 6l12 12"],
  trash: ["M3 6h18", "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6", "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"],
  film: ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M7 3v18", "M17 3v18", "M3 12h18", "M3 7.5h4", "M3 16.5h4", "M17 7.5h4", "M17 16.5h4"],
  music: ["M9 18V5l12-2v13", "M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z", "M21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"],
  archive: ["M21 8v13H3V8", "M1 3h22v5H1z", "M10 12h4"],
  document: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6", "M16 13H8", "M16 17H8", "M10 9H8"],
  image: ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z", "M21 15l-5-5L5 21"],
  app: ["M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z", "M3.27 6.96 12 12.01l8.73-5.05", "M12 22.08V12"],
  file: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6"],
  check: ["M20 6 9 17l-5-5"],
  alert: ["M12 9v4", "M12 17h.01", "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"],
  signal: ["M2 20h.01", "M7 20v-4", "M12 20v-8", "M17 20V8", "M22 4v16"],
};
function icon(name, size = 16) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor",
    "stroke-width": 1.8, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(k, v);
  for (const d of ICONS[name] || ICONS.file) {
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}
function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c != null && c !== false) el.append(c instanceof Node ? c : String(c));
  return el;
}
document.querySelectorAll("[data-icon]").forEach((el) => el.prepend(icon(el.dataset.icon, 16)));

// ------------------------------------------------------------------ utilities
const $ = (id) => document.getElementById(id);
const msg = (type, data = {}) => new Promise((resolve) => {
  chrome.runtime.sendMessage({ type, ...data }, (resp) => {
    void chrome.runtime.lastError;
    resolve(resp || { ok: false, error: "Veloce didn't respond" });
  });
});
function fmtBytes(b) {
  if (!b || b < 0) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(b) / Math.log(1024)), u.length - 1);
  return `${(b / 1024 ** i).toFixed(i >= 2 ? 1 : 0)} ${u[i]}`;
}
function fmtEta(s) {
  if (!s || s <= 0 || !isFinite(s)) return "";
  s = Math.round(s);
  if (s < 60) return `${s}s left`;
  if (s < 3600) return `${Math.floor(s / 60)}m left`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m left`;
}
function fmtAgo(ts) {
  if (!ts) return "";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
function fmtDuration(s) {
  if (!s) return "";
  s = Math.round(s);
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  return hh ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}` : `${mm}:${String(ss).padStart(2, "0")}`;
}
const hostOf = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; } };
const isHttp = (url) => /^https?:\/\/\S+$/i.test((url || "").trim());

let toastTimer = 0;
function toast(text, kind = "") {
  const el = $("toast");
  el.className = `toast ${kind}`;
  el.replaceChildren(icon(kind === "error" ? "alert" : "check", 15), h("span", { text }));
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2600);
}

const EXT_TYPES = {
  video: ["mp4", "mkv", "webm", "mov", "avi", "m4v", "flv", "wmv"],
  audio: ["mp3", "m4a", "aac", "flac", "wav", "ogg", "opus", "wma"],
  archive: ["zip", "rar", "7z", "tar", "gz", "xz", "bz2", "zst", "iso", "dmg", "tgz"],
  document: ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "epub", "md"],
  image: ["jpg", "jpeg", "png", "gif", "webp", "svg", "heic", "avif"],
  app: ["exe", "msi", "apk", "deb", "rpm", "appimage", "pkg", "bin", "run"],
};
const TYPE_ICON = { video: "film", audio: "music", archive: "archive", document: "document", image: "image", app: "app", file: "file" };
function typeOf(t) {
  if (t.kind === "media") return t.extract_audio ? "audio" : "video";
  const ext = (t.filename || "").split(".").pop().toLowerCase();
  for (const [type, exts] of Object.entries(EXT_TYPES)) if (exts.includes(ext)) return type;
  const ct = t.content_type || "";
  if (ct.startsWith("video/")) return "video";
  if (ct.startsWith("audio/")) return "audio";
  if (ct.startsWith("image/")) return "image";
  return "file";
}
const typeTile = (type) => h("div", { class: "type", "data-type": type }, icon(TYPE_ICON[type] || "file", 16));

// ------------------------------------------------------------------ state
const state = { engine: undefined, tasks: [], view: "home", preview: null, tab: null };
const ACTIVE = new Set(["QUEUED", "INITIALIZING", "DOWNLOADING"]);
const stateOf = (s) => (ACTIVE.has(s) ? "active" : s === "COMPLETED" ? "done" : s === "PAUSED" ? "paused" : "failed");
const LIST_LIMIT = 8;

// ------------------------------------------------------------------ navigation
function showView(view) {
  state.view = view;
  $("view-home").hidden = view !== "home";
  $("view-settings").hidden = view !== "settings";
  if (view === "settings") renderEngineInfo();
}
$("btn-settings").addEventListener("click", () => showView(state.view === "settings" ? "home" : "settings"));
$("btn-back").addEventListener("click", () => showView("home"));
$("btn-home").addEventListener("click", () => showView("home"));
$("btn-app").addEventListener("click", () => {
  if (state.engine) chrome.tabs.create({ url: "http://127.0.0.1:9229/" });
  else toast("Start the Veloce app first", "error");
});

// ------------------------------------------------------------------ engine status
async function refreshEngine() {
  const res = await msg("ENGINE_STATUS");
  const was = state.engine;
  state.engine = res.ok ? res.status : null;
  const el = $("engine");
  el.classList.toggle("is-on", !!state.engine);
  el.classList.toggle("is-off", !state.engine);
  el.querySelector(".engine-label").textContent = state.engine ? "Ready" : "Off";
  el.title = state.engine ? `Veloce ${state.engine.version} is running` : "The Veloce app isn't running — downloads go through Chrome";
  $("offline").hidden = !!state.engine;
  const keys = document.querySelector(".foot-keys");
  if (state.engine?.update_available && keys && !keys.dataset.update) {
    keys.dataset.update = "1";
    keys.replaceChildren(h("button", { class: "link", type: "button", text: `Update to ${state.engine.latest_version} →`,
      onclick: () => chrome.tabs.create({ url: "http://127.0.0.1:9229/#settings" }) }));
  }
  if (was !== undefined && !!was !== !!state.engine) renderHere();
}

$("btn-retry-engine").addEventListener("click", async () => {
  await refreshEngine();
  toast(state.engine ? "Connected to Veloce" : "Still not running", state.engine ? "" : "error");
});
$("btn-copy-start").addEventListener("click", async () => {
  const p = (navigator.userAgentData?.platform || navigator.platform || "").toLowerCase();
  const cmd = p.includes("win") ? "veloce-windows-x64.exe" : p.includes("mac") ? "./veloce-macos-arm64" : "./veloce-linux-x86_64";
  try { await navigator.clipboard.writeText(cmd); toast("Copied — run it once, then turn on Start at login"); } catch { toast(cmd); }
});

// ------------------------------------------------------------------ "this page" card (browser-first primary action)
async function renderHere() {
  const card = $("here");
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  state.tab = tab;
  if (!tab || !isHttp(tab.url || "")) { card.hidden = true; return; }
  const [{ mediaSite }, streamsRes] = await Promise.all([msg("IS_MEDIA_SITE", { url: tab.url }), msg("GET_TAB_STREAMS", { tabId: tab.id })]);
  const streams = (streamsRes.ok ? streamsRes.streams : []).filter((s) => s.type !== "Subtitle");
  if (!mediaSite && !streams.length) { card.hidden = true; return; }
  if (mediaSite && state.engine) msg("PREFETCH_MEDIA", { url: tab.url, pageUrl: tab.url }); // ready by the time it's clicked

  const title = tab.title || hostOf(tab.url);
  const head = h("div", { class: "here-head" },
    h("div", { class: "here-icon" }, icon("film", 18)),
    h("div", { class: "here-text" },
      h("div", { class: "here-title", text: title }),
      h("div", { class: "here-sub", text: mediaSite ? `Video on ${hostOf(tab.url)}` : `${streams.length} media stream${streams.length === 1 ? "" : "s"} found on this page` })));

  if (!state.engine) {
    card.replaceChildren(head, h("div", { class: "pv-note", text: "Open the Veloce app to download videos from this page." }));
    card.hidden = false;
    return;
  }
  const findBtn = h("button", { class: "btn primary", type: "button" }, icon("download", 15), "Download this video");
  findBtn.addEventListener("click", () => {
    card.replaceChildren(head);
    const target = h("div", { style: "display:flex;flex-direction:column;gap:10px" });
    card.append(target);
    analyzeMedia(tab.url, 0, target, null, { compact: true });
  });
  card.replaceChildren(head, h("div", { class: "here-actions" }, findBtn));
  card.hidden = false;
}

// ------------------------------------------------------------------ downloads list
const cards = new Map();

async function refreshTasks() {
  if (!state.engine) {
    chrome.downloads.search({ limit: LIST_LIMIT, orderBy: ["-startTime"] }, (items) => renderChromeDownloads(items || []));
    return;
  }
  const res = await msg("LIST_TASKS");
  state.tasks = res.ok ? res.tasks || [] : [];
  renderTasks();
}

function renderTasks() {
  const list = $("tasks");
  const active = state.tasks.filter((t) => ACTIVE.has(t.status));
  const speed = active.reduce((s, t) => s + (t.speed || 0), 0);
  $("list-meta").textContent = active.length ? `${active.length} active` : state.tasks.length ? `${state.tasks.length}` : "";
  $("foot-speed").textContent = active.length ? `↓ ${fmtBytes(speed)}/s` : "";
  chrome.action?.setBadgeText?.({ text: active.length ? String(active.length) : "" });

  const tasks = state.tasks.slice(0, LIST_LIMIT);
  if (!tasks.length) {
    cards.clear();
    list.replaceChildren();
    if (!list.nextElementSibling?.classList?.contains("empty")) list.after(emptyState());
    return;
  }
  list.nextElementSibling?.classList?.contains("empty") && list.nextElementSibling.remove();
  const ids = new Set(tasks.map((t) => t.id));
  for (const id of [...cards.keys()]) if (!ids.has(id)) { cards.get(id).el.remove(); cards.delete(id); }
  tasks.forEach((t, i) => {
    let c = cards.get(t.id);
    if (!c) { c = buildCard(t); cards.set(t.id, c); }
    updateCard(c, t);
    if (list.children[i] !== c.el) list.insertBefore(c.el, list.children[i] || null);
  });
}

function emptyState() {
  return h("div", { class: "empty" },
    h("strong", { text: "Nothing downloaded yet" }),
    h("span", { text: "Paste a link above, or hover any video and press Download." }));
}

function buildCard(t) {
  const r = {};
  r.tile = h("div", { class: "type" });
  r.name = h("div", { class: "task-name" });
  r.actions = h("div", { class: "task-actions" });
  r.lanes = h("div", { class: "lanes" }, h("b", {}));
  r.st = h("span", { class: "st" });
  r.right = h("span", {});
  r.name.addEventListener("click", () => { if (r.name.classList.contains("clickable")) taskAction(t.id, "open"); });
  r.el = h("div", { class: "task", role: "listitem" }, r.tile,
    h("div", { class: "task-main" }, h("div", { class: "task-top" }, r.name, r.actions), r.lanes, h("div", { class: "task-sub" }, r.st, r.right)));
  r.sig = "";
  return r;
}

function updateCard(r, t) {
  const st = stateOf(t.status);
  r.el.dataset.state = st;
  const type = typeOf(t);
  if (r.tile.dataset.type !== type) { r.tile.dataset.type = type; r.tile.replaceChildren(icon(TYPE_ICON[type], 16)); }
  r.name.textContent = t.filename || t.title || t.url;
  r.name.title = t.file_path || t.url;
  r.name.classList.toggle("clickable", t.status === "COMPLETED");
  r.name.classList.toggle("gone", t.status === "FILE_REMOVED");

  // Connection lanes: only while there is progress to show
  const showLanes = ACTIVE.has(t.status) || t.status === "PAUSED";
  r.lanes.hidden = !showLanes;
  if (showLanes) {
    const segs = t.segments || [];
    if (t.status === "DOWNLOADING" && segs.length > 1 && t.total_size) {
      r.lanes.classList.remove("indeterminate");
      r.lanes.replaceChildren(...segs.map((s) => {
        const i = document.createElement("i");
        i.style.left = `${(s.start / t.total_size) * 100}%`;
        i.style.width = `${Math.max(0.5, ((s.current - s.start) / t.total_size) * 100)}%`;
        return i;
      }));
      r.lanes.title = `${segs.filter((s) => s.active).length} connections`;
    } else {
      if (!r.lanes.querySelector("b")) r.lanes.replaceChildren(h("b", {}));
      r.lanes.classList.toggle("indeterminate", ACTIVE.has(t.status) && !t.total_size);
      r.lanes.firstChild.style.width = `${Math.min(100, t.percent || 0)}%`;
    }
  }

  const pct = Math.floor(t.percent || 0);
  const size = t.total_size ? fmtBytes(t.total_size) : t.downloaded ? fmtBytes(t.downloaded) : "";
  if (t.status === "DOWNLOADING") {
    const conns = (t.segments || []).filter((s) => s.active).length;
    r.st.textContent = t.total_size ? `${pct}% · ${fmtBytes(t.downloaded)} of ${size}` : fmtBytes(t.downloaded);
    r.right.textContent = [t.speed ? `${fmtBytes(t.speed)}/s` : "", conns > 1 ? `${conns} lanes` : fmtEta(t.eta)].filter(Boolean).join(" · ");
  } else if (t.status === "ERROR") {
    r.st.textContent = t.error || "Failed";
    r.st.title = t.error || "";
    r.right.textContent = "";
  } else {
    r.st.textContent = { QUEUED: "Queued", INITIALIZING: t.note || "Starting…", PAUSED: `Paused · ${pct}%`, COMPLETED: size || "Done",
      CANCELLED: "Cancelled", FILE_REMOVED: "File was deleted" }[t.status] || t.status;
    r.right.textContent = st === "done" ? fmtAgo(t.created_at) : "";
  }

  const actions = [];
  if (ACTIVE.has(t.status)) {
    if (t.kind !== "media" && t.status === "DOWNLOADING") actions.push(["pause", "Pause", "pause"]);
    actions.push(["x", "Cancel", "remove", "danger"]);
  } else if (t.status === "PAUSED") {
    actions.push(["play", "Resume", "resume"], ["x", "Cancel", "remove", "danger"]);
  } else if (t.status === "COMPLETED") {
    actions.push(["folder", "Show in folder", "open"], ["trash", "Remove from list (keeps the file)", "remove"]);
  } else {
    actions.push(["retry", "Try again", "resume"], ["trash", "Remove from list", "remove"]);
  }
  const sig = actions.map((a) => a[2]).join();
  if (r.sig !== sig) {
    r.sig = sig;
    r.actions.replaceChildren(...actions.map(([ic, title, action, cls]) =>
      h("button", { class: `icon-btn${cls ? " " + cls : ""}`, type: "button", title, "aria-label": title,
        onclick: () => taskAction(t.id, action) }, icon(ic, 14))));
  }
}

async function taskAction(id, action) {
  const res = await msg("TASK_ACTION", { id, action });
  if (!res.ok) toast(res.error || "That didn't work", "error");
  refreshTasks();
}

function renderChromeDownloads(items) {
  cards.clear();
  const list = $("tasks");
  const rows = items.filter((i) => i.state !== "interrupted" || i.error !== "USER_CANCELED").slice(0, LIST_LIMIT);
  $("list-meta").textContent = "in Chrome";
  $("foot-speed").textContent = "";
  list.nextElementSibling?.classList?.contains("empty") && list.nextElementSibling.remove();
  if (!rows.length) { list.replaceChildren(); list.after(emptyState()); return; }
  list.replaceChildren(...rows.map((item) => {
    const name = (item.filename || item.url).split(/[\\/]/).pop();
    const type = typeOf({ filename: name, content_type: item.mime });
    const pct = item.totalBytes > 0 ? (item.bytesReceived / item.totalBytes) * 100 : 0;
    const st = item.state === "complete" ? "done" : item.state === "in_progress" ? "active" : "failed";
    const lanes = h("div", { class: "lanes" }, h("b", { style: `width:${pct}%` }));
    lanes.hidden = st !== "active";
    return h("div", { class: "task", role: "listitem", "data-state": st }, typeTile(type),
      h("div", { class: "task-main" },
        h("div", { class: "task-top" }, h("div", { class: "task-name", text: name, title: item.filename })),
        lanes,
        h("div", { class: "task-sub" },
          h("span", { class: "st", text: st === "done" ? fmtBytes(item.totalBytes || item.bytesReceived) : st === "active" ? `${Math.floor(pct)}%` : "Interrupted" }),
          h("span", { text: "" }))));
  }));
}

$("btn-clear-done").addEventListener("click", async () => {
  if (state.engine) {
    const res = await msg("CLEAR_COMPLETED");
    toast(res.ok ? (res.cleared ? `Cleared ${res.cleared} — files stay on disk` : "Nothing to clear") : res.error, res.ok ? "" : "error");
  } else {
    chrome.downloads.erase({ state: "complete" }, () => toast("Cleared Chrome's finished downloads"));
  }
  refreshTasks();
});

// ------------------------------------------------------------------ link box + smart preview
const input = $("url-input");
const preview = $("preview");
let analyzeTimer = 0;
let analyzeSeq = 0;

input.addEventListener("input", () => {
  clearTimeout(analyzeTimer);
  const url = input.value.trim();
  if (!isHttp(url)) { hidePreview(); return; }
  analyzeTimer = setTimeout(() => analyze(url), 400);
});
input.addEventListener("paste", () => setTimeout(() => { if (isHttp(input.value.trim())) analyze(input.value.trim()); }, 0));
$("btn-paste").addEventListener("click", async () => {
  try {
    const text = (await navigator.clipboard.readText()).trim();
    if (!isHttp(text)) { toast("Your clipboard doesn't have a link", "error"); return; }
    input.value = text;
    analyze(text);
  } catch {
    toast("Paste with Ctrl+V instead", "error");
  }
});
$("composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = input.value.trim();
  if (!isHttp(url)) { toast("That doesn't look like a link", "error"); return; }
  if (!state.preview || state.preview.url !== url || state.preview.loading) await analyze(url);
  state.preview?.primary?.();
});

function hidePreview() {
  analyzeSeq++;
  state.preview = null;
  preview.hidden = true;
  preview.replaceChildren();
}
function setPreview(...children) {
  preview.hidden = false;
  preview.replaceChildren(...children);
}
const loadingRow = (text) => h("div", { class: "loading" }, h("span", { class: "spinner" }), h("span", { text }));

async function analyze(url) {
  const seq = ++analyzeSeq;
  state.preview = { url, loading: true };
  setPreview(loadingRow(`Checking ${hostOf(url)}…`));

  if (!state.engine) {
    let name = hostOf(url);
    try { name = decodeURIComponent(new URL(url).pathname.split("/").pop() || "") || name; } catch { /* keep */ }
    const go = () => startFile(url, name);
    state.preview = { url, primary: go };
    setPreview(
      h("div", { class: "pv-row" }, typeTile(typeOf({ filename: name })), h("div", { class: "pv-name", text: name })),
      h("div", { class: "pv-note", text: "The Veloce app is off, so this downloads through Chrome. Videos need the app." }),
      h("div", { class: "pv-actions" }, h("button", { class: "btn primary small", type: "button", onclick: go }, "Download with Chrome")));
    return;
  }

  const { mediaSite } = await msg("IS_MEDIA_SITE", { url });
  if (mediaSite) return analyzeMedia(url, seq, preview, null, {});

  const res = await msg("INSPECT", { url });
  if (seq !== analyzeSeq) return;
  if (!res.ok) {
    state.preview = { url, primary: () => startFile(url) };
    setPreview(h("div", { class: "pv-note", text: `Couldn't check this link — ${res.error}. You can still try.` }),
      h("div", { class: "pv-actions" }, h("button", { class: "btn primary small", type: "button", onclick: state.preview.primary }, "Try anyway")));
    return;
  }
  if (res.is_page) return analyzeMedia(url, seq, preview, res, {});
  renderFilePreview(url, res);
}

function renderFilePreview(url, info) {
  const nameInput = h("input", { class: "pv-name", value: info.filename, "aria-label": "File name", spellcheck: "false" });
  const go = () => startFile(url, nameInput.value.trim() || info.filename);
  nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go(); } });
  state.preview = { url, primary: go };
  setPreview(
    h("div", { class: "pv-row" }, typeTile(typeOf({ filename: info.filename, content_type: info.content_type })), nameInput),
    h("div", { class: "pv-meta" },
      h("span", { class: "tag", text: info.total_size ? fmtBytes(info.total_size) : "Size unknown" }),
      info.resumable ? h("span", { class: "tag good", text: "Fast · resumable" }) : h("span", { class: "tag warn", text: "Single connection" })),
    h("div", { class: "pv-actions" },
      h("button", { class: "btn quiet small", type: "button", onclick: hidePreview, text: "Cancel" }),
      h("button", { class: "btn primary small", type: "button", onclick: go }, icon("download", 14), "Download")));
}

/** Video / audio / playlist options, rendered into `target` (the preview or the "this page" card). */
async function analyzeMedia(url, seq, target, inspectInfo, { compact = false }) {
  target.hidden = false;
  target.replaceChildren(loadingRow("Finding qualities…"));
  const res = await msg("PROBE_MEDIA", { url, pageUrl: url });
  if (target === preview && seq !== analyzeSeq) return;

  const info = res.ok ? res.result : null;
  const videos = info?.video_formats || [];
  const pl = info?.playlist;
  const found = info && (pl || info.extractor !== "direct");
  if (!found) {
    if (inspectInfo) { renderFilePreview(url, inspectInfo); preview.prepend(h("div", { class: "pv-note", text: "This is a web page — no video found on it." })); return; }
    target.replaceChildren(h("div", { class: "pv-note", text: res.error || "No video found. If it's private, sign in to the site in this browser and try again." }));
    return;
  }

  const heights = [...new Set(videos.map((v) => v.height).filter(Boolean))].sort((a, b) => b - a);
  let mode = videos.length ? "video" : "audio";
  let quality = heights.find((x) => x <= 1080) ? `${heights.find((x) => x <= 1080)}p` : "best";
  let audioFmt = "mp3";
  let whole = !!pl && !videos.length;

  const options = h("div", {});
  const seg = h("div", { class: "seg", role: "radiogroup", "aria-label": "Download type" });
  for (const [key, label] of [["video", "Video"], ["audio", "Audio only"]]) {
    const b = h("button", { type: "button", role: "radio", "aria-checked": String(mode === key), text: label });
    b.addEventListener("click", () => { mode = key; seg.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b))); drawOptions(); });
    seg.append(b);
  }
  function chips(items, current, pick) {
    const g = h("div", { class: "chips", role: "radiogroup" });
    for (const [key, label, small] of items) {
      const c = h("button", { class: "chip", type: "button", role: "radio", "aria-checked": String(key === current) }, label, small ? h("small", { text: small }) : null);
      c.addEventListener("click", () => { pick(key); g.querySelectorAll(".chip").forEach((x) => x.setAttribute("aria-checked", String(x === c))); });
      g.append(c);
    }
    return g;
  }
  function drawOptions() {
    if (mode === "video") {
      const items = [["best", "Best"], ...heights.slice(0, 5).map((x) => {
        const f = videos.find((v) => v.height === x);
        return [`${x}p`, `${x}p`, f?.filesize ? fmtBytes(f.filesize) : ""];
      })];
      if (!items.some((i) => i[0] === quality)) quality = "best";
      options.replaceChildren(chips(items, quality, (k) => { quality = k; }));
    } else {
      options.replaceChildren(chips([["mp3", "MP3"], ["m4a", "M4A"], ["opus", "Opus"], ["flac", "FLAC"]], audioFmt, (k) => { audioFmt = k; }));
    }
  }
  drawOptions();

  const startBtn = h("button", { class: "btn primary small", type: "button" }, icon("download", 14), h("span", { text: "Download" }));
  const setLabel = () => { startBtn.lastChild.textContent = whole && pl ? `Download ${pl.entries.length} videos` : "Download"; };
  let plRow = null;
  if (pl) {
    const sw = h("input", { type: "checkbox", class: "switch" });
    sw.checked = whole;
    sw.disabled = !videos.length;
    sw.addEventListener("change", () => { whole = sw.checked; setLabel(); });
    plRow = h("label", { class: "pl-row" },
      h("span", { class: "setting-text" }, h("strong", { text: `Whole playlist · ${pl.count} videos` }), h("span", { text: pl.title })), sw);
  }
  setLabel();

  const go = async () => {
    startBtn.disabled = true;
    const audio = mode === "audio";
    const base = { extract_audio: audio, audio_format: audioFmt, format_id: audio ? "bestaudio" : quality, page_url: url };
    const payload = whole && pl
      ? { ...base, entries: pl.entries.map((e) => ({ url: e.url, title: e.title })), playlist_title: pl.title }
      : { ...base, url, title: info.title };
    const r = await msg("DOWNLOAD_MEDIA", { payload });
    startBtn.disabled = false;
    if (!r.ok || r.success === false) { toast(r.error || "Couldn't start the download", "error"); return; }
    toast(whole && pl ? `${pl.entries.length} videos queued` : "Downloading");
    if (target === preview) { input.value = ""; hidePreview(); } else renderHere();
    refreshTasks();
  };
  startBtn.addEventListener("click", go);
  if (target === preview) state.preview = { url, primary: go };

  const headRow = compact ? null : h("div", { class: "pv-row" },
    info.thumbnail ? h("img", { class: "thumb", src: info.thumbnail, alt: "", referrerpolicy: "no-referrer" }) : typeTile("video"),
    h("div", { style: "min-width:0" },
      h("div", { class: "media-title", text: info.title }),
      h("div", { class: "media-sub", text: [info.uploader, fmtDuration(info.duration)].filter(Boolean).join(" · ") })));

  target.replaceChildren(...[headRow, videos.length ? seg : null, options, plRow,
    h("div", { class: "pv-actions" }, target === preview ? h("button", { class: "btn quiet small", type: "button", onclick: hidePreview, text: "Cancel" }) : null, startBtn)].filter(Boolean));
}

async function startFile(url, filename) {
  const res = await msg("DOWNLOAD_FILE", { url, filename });
  if (!res.ok || res.success === false) { toast(res.error || "Couldn't start the download", "error"); return; }
  toast(res.direct ? "Downloading with Chrome" : "Downloading");
  input.value = "";
  hidePreview();
  refreshTasks();
}

// ------------------------------------------------------------------ settings
const DEFAULTS = { interceptEnabled: true, minInterceptMB: 1, connections: 16, excludedHosts: [], notifyOnComplete: true, sendCookies: true, theme: "system" };

async function loadSettings() {
  const s = await chrome.storage.local.get(DEFAULTS);
  $("set-intercept").checked = s.interceptEnabled;
  $("set-min-size").value = s.minInterceptMB;
  $("set-connections").value = s.connections;
  $("out-connections").textContent = s.connections;
  $("set-excluded").value = (s.excludedHosts || []).join("\n");
  $("set-cookies").checked = s.sendCookies;
  $("set-notify").checked = s.notifyOnComplete;
  setThemeChoice(s.theme);
}
function bindSetting(id, key, read) {
  $(id).addEventListener("change", () => chrome.storage.local.set({ [key]: read($(id)) }).then(() => toast("Saved")));
}
bindSetting("set-intercept", "interceptEnabled", (el) => el.checked);
bindSetting("set-min-size", "minInterceptMB", (el) => Math.max(0, Number(el.value) || 0));
bindSetting("set-connections", "connections", (el) => Number(el.value));
bindSetting("set-excluded", "excludedHosts", (el) => el.value.split(/\s+/).map((x) => x.trim().replace(/^https?:\/\//, "").replace(/\/.*$/, "")).filter(Boolean));
bindSetting("set-cookies", "sendCookies", (el) => el.checked);
bindSetting("set-notify", "notifyOnComplete", (el) => el.checked);
$("set-connections").addEventListener("input", (e) => { $("out-connections").textContent = e.target.value; });

const THEME_ORDER = ["system", "light", "dark"];
const THEME_ICON = { system: "monitor", light: "sun", dark: "moon" };
const THEME_LABEL = { system: "System", light: "Light", dark: "Dark" };
function setThemeChoice(value) {
  applyTheme(value);
  const tb = $("btn-theme");
  tb.replaceChildren(icon(THEME_ICON[value] || "monitor", 16));
  tb.title = `Theme: ${THEME_LABEL[value]} — click to change`;
  tb.setAttribute("aria-label", `Theme: ${THEME_LABEL[value]}`);
  tb.dataset.value = value;
  try { localStorage.setItem(THEME_KEY, value); } catch { /* storage blocked */ }
  document.querySelectorAll("#set-theme button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.themeValue === value)));
}
$("btn-theme").addEventListener("click", () => {
  const next = THEME_ORDER[(THEME_ORDER.indexOf($("btn-theme").dataset.value || "system") + 1) % 3];
  setThemeChoice(next);
  chrome.storage.local.set({ theme: next });
  toast(`Theme: ${THEME_LABEL[next]}`);
});
document.querySelectorAll("#set-theme button").forEach((b) => b.addEventListener("click", () => {
  setThemeChoice(b.dataset.themeValue);
  chrome.storage.local.set({ theme: b.dataset.themeValue });
}));

function renderEngineInfo() {
  const dl = $("engine-info");
  const e = state.engine;
  const rows = e ? [
    ["App", `Veloce ${e.version}`],
    ["Saves to", e.default_download_dir],
    ["Video", e.media_support?.yt_dlp ? `yt-dlp ${e.media_support.yt_dlp_version || ""} · updates itself` : "yt-dlp missing"],
    ["Merging", e.media_support?.ffmpeg ? "ffmpeg ready" : "ffmpeg missing — some HD formats unavailable"],
  ] : [["App", "Not running"]];
  dl.replaceChildren(...rows.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", { text: v })]));
}

// ------------------------------------------------------------------ boot
(async () => {
  await loadSettings();
  await refreshEngine();
  await Promise.all([refreshTasks(), renderHere()]);
  setInterval(async () => {
    await refreshEngine();
    if (state.view === "home") refreshTasks();
  }, 1000);
})();
