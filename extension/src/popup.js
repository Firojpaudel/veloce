/* global chrome */
/**
 * Veloce popup controller.
 * Talks to the engine through the background service worker (which adds cookies/referrers).
 * All page/remote text is rendered with textContent — never innerHTML.
 */

// ------------------------------------------------------------------ icons (Lucide-style, MIT)
const ICONS = {
  download: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"],
  folder: ["M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"],
  globe: ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z", "M2 12h20", "M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"],
  settings: ["M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"],
  link: ["M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71", "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"],
  clipboard: ["M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2", "M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"],
  copy: ["M8 8h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z", "M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"],
  refresh: ["M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", "M21 3v5h-5", "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", "M8 16H3v5"],
  power: ["M12 2v10", "M18.36 6.64a9 9 0 1 1-12.73 0"],
  zap: ["M13 2 3 14h9l-1 8 10-12h-9l1-8z"],
  pause: ["M6 4h4v16H6z", "M14 4h4v16h-4z"],
  play: ["M6 3l14 9-14 9V3z"],
  retry: ["M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", "M3 3v5h5"],
  x: ["M18 6 6 18", "M6 6l12 12"],
  trash: ["M3 6h18", "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6", "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"],
  film: ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M7 3v18", "M17 3v18", "M3 12h18", "M3 7.5h4", "M3 16.5h4", "M17 7.5h4", "M17 16.5h4"],
  music: ["M9 18V5l12-2v13", "M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z", "M21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"],
  archive: ["M21 8v13H3V8", "M1 3h22v5H1z", "M10 12h4"],
  document: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6", "M16 13H8", "M16 17H8", "M10 9H8"],
  image: ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z", "M21 15l-5-5L5 21"],
  app: ["M16.5 9.4 7.55 4.24", "M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z", "M3.27 6.96 12 12.01l8.73-5.05", "M12 22.08V12"],
  file: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6"],
  list: ["M8 6h13", "M8 12h13", "M8 18h13", "M3 6h.01", "M3 12h.01", "M3 18h.01"],
  check: ["M20 6 9 17l-5-5"],
  alert: ["M12 9v4", "M12 17h.01", "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"],
  inbox: ["M22 12h-6l-2 3h-4l-2-3H2", "M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"],
  signal: ["M2 20h.01", "M7 20v-4", "M12 20v-8", "M17 20V8", "M22 4v16"],
};

function icon(name, size = 16) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor",
    "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(k, v);
  for (const d of ICONS[name] || ICONS.file) {
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}

const TYPE_ICONS = { video: "film", audio: "music", archive: "archive", document: "document", image: "image", app: "app", file: "file", alert: "alert" };
const typeIcon = (type, size = 18) => icon(TYPE_ICONS[type] || "file", size);

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

document.querySelectorAll("[data-icon]").forEach((el) => el.prepend(icon(el.dataset.icon, el.classList.contains("offline-icon") ? 20 : 16)));

// ------------------------------------------------------------------ utilities
const $ = (id) => document.getElementById(id);
const msg = (type, data = {}) => new Promise((resolve) => {
  chrome.runtime.sendMessage({ type, ...data }, (resp) => {
    void chrome.runtime.lastError;
    resolve(resp || { ok: false, error: "No response from Veloce" });
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
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s left`;
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
  video: ["mp4", "mkv", "webm", "mov", "avi", "m4v", "flv", "wmv", "ts", "m3u8"],
  audio: ["mp3", "m4a", "aac", "flac", "wav", "ogg", "opus", "wma"],
  archive: ["zip", "rar", "7z", "tar", "gz", "xz", "bz2", "zst", "iso", "dmg"],
  document: ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "epub", "md"],
  image: ["jpg", "jpeg", "png", "gif", "webp", "svg", "heic", "avif"],
  app: ["exe", "msi", "apk", "deb", "rpm", "appimage", "pkg", "bin", "run"],
};
function typeOf(task) {
  if (task.kind === "media") return task.extract_audio ? "audio" : "video";
  const ext = (task.filename || "").split(".").pop().toLowerCase();
  for (const [type, exts] of Object.entries(EXT_TYPES)) if (exts.includes(ext)) return type;
  const ct = task.content_type || "";
  if (ct.startsWith("video/")) return "video";
  if (ct.startsWith("audio/")) return "audio";
  if (ct.startsWith("image/")) return "image";
  return "file";
}

// ------------------------------------------------------------------ state
const state = {
  engine: null,
  tasks: [],
  filter: "all",
  view: "downloads",
  preview: null, // { kind, ... }
};

const ACTIVE = new Set(["QUEUED", "INITIALIZING", "DOWNLOADING"]);
const stateOf = (s) => (ACTIVE.has(s) ? "active" : s === "COMPLETED" ? "done" : s === "PAUSED" ? "paused" : "failed");

// ------------------------------------------------------------------ tabs
document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => showView(tab.dataset.view)));
function showView(view) {
  state.view = view;
  document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.view === view)));
  for (const v of ["downloads", "page", "settings"]) $(`view-${v}`).hidden = v !== view;
  if (view === "page") renderPageView();
  if (view === "settings") renderEngineInfo();
}

// ------------------------------------------------------------------ engine status
async function refreshEngine() {
  const res = await msg("ENGINE_STATUS");
  const was = !!state.engine;
  state.engine = res.ok ? res.status : null;
  const el = $("engine-status");
  el.classList.toggle("online", !!state.engine);
  el.classList.toggle("offline", !state.engine);
  el.querySelector(".status-label").textContent = state.engine ? "Connected" : "Engine off";
  el.title = state.engine ? `Veloce engine ${state.engine.version} is running` : "Engine is not running — downloads use Chrome";
  $("offline-card").hidden = !!state.engine;
  if (was !== !!state.engine && state.preview?.url) analyze(state.preview.url);
}

$("engine-status").addEventListener("click", () => showView("settings"));
$("btn-retry-engine").addEventListener("click", async () => {
  await refreshEngine();
  toast(state.engine ? "Engine connected" : "Engine still not running", state.engine ? "" : "error");
});
$("btn-copy-start").addEventListener("click", async () => {
  const p = (navigator.userAgentData?.platform || navigator.platform || "").toLowerCase();
  const cmd = p.includes("win") ? "veloce-windows-x64.exe autostart enable"
    : p.includes("mac") ? "./veloce-macos autostart enable" : "./veloce-linux-x86_64 autostart enable";
  try { await navigator.clipboard.writeText(cmd); toast("Copied — run it once in a terminal"); }
  catch { toast(cmd); }
});

// ------------------------------------------------------------------ tasks list
const cards = new Map(); // id -> { el, refs }

async function refreshTasks() {
  if (!state.engine) {
    chrome.downloads.search({ limit: 12, orderBy: ["-startTime"] }, (items) => renderChromeDownloads(items || []));
    return;
  }
  const res = await msg("LIST_TASKS");
  state.tasks = res.ok ? res.tasks || [] : [];
  renderTasks();
}

function visibleTasks() {
  return state.tasks.filter((t) => state.filter === "all" || stateOf(t.status) === state.filter ||
    (state.filter === "failed" && ["ERROR", "CANCELLED", "FILE_REMOVED"].includes(t.status)));
}

function renderTasks() {
  const list = $("tasks");
  const tasks = visibleTasks();
  const active = state.tasks.filter((t) => ACTIVE.has(t.status));
  const countEl = $("count-active");
  countEl.hidden = !active.length;
  countEl.textContent = active.length;
  $("total-speed").textContent = `${fmtBytes(active.reduce((s, t) => s + (t.speed || 0), 0))}/s`;

  if (!tasks.length) {
    cards.clear();
    list.replaceChildren(emptyState());
    return;
  }
  const ids = new Set(tasks.map((t) => t.id));
  for (const id of [...cards.keys()]) if (!ids.has(id)) { cards.get(id).el.remove(); cards.delete(id); }
  list.querySelector(".empty")?.remove();

  tasks.forEach((task, index) => {
    let card = cards.get(task.id);
    if (!card) {
      card = buildCard(task);
      cards.set(task.id, card);
    }
    updateCard(card, task);
    if (list.children[index] !== card.el) list.insertBefore(card.el, list.children[index] || null);
  });
}

function emptyState() {
  const copy = {
    all: ["No downloads yet", "Paste a link above, or hover any video and press Download."],
    active: ["Nothing downloading", "Active downloads show up here."],
    done: ["Nothing finished yet", "Completed downloads show up here."],
    failed: ["No failed downloads", "Nice."],
  }[state.filter];
  return h("div", { class: "empty" }, h("div", { class: "empty-icon" }, icon("inbox", 22)), h("strong", { text: copy[0] }), h("span", { text: copy[1] }));
}

function buildCard(task) {
  const refs = {};
  refs.tile = h("div", { class: "type-tile" });
  refs.name = h("div", { class: "task-name" });
  refs.tag = h("span", { class: "task-tag", hidden: true });
  refs.actions = h("div", { class: "task-actions" });
  refs.bar = h("div", { class: "progress" }, h("div", { class: "progress-fill" }));
  refs.segments = h("div", { class: "segments", hidden: true, title: "Each block is one connection" });
  refs.status = h("span", { class: "status-text" });
  refs.right = h("span", {});
  refs.error = h("div", { class: "task-error", hidden: true });
  refs.name.addEventListener("click", () => { if (refs.name.classList.contains("clickable")) taskAction(task.id, "open"); });
  const el = h("div", { class: "task", role: "listitem" },
    refs.tile,
    h("div", { class: "task-main" },
      h("div", { class: "task-top" }, refs.name, refs.tag, refs.actions),
      refs.bar, refs.segments,
      h("div", { class: "task-sub" }, refs.status, refs.right),
      refs.error));
  return { el, refs, sig: "" };
}

function updateCard(card, t) {
  const { refs } = card;
  const st = stateOf(t.status);
  card.el.dataset.state = st;

  const type = typeOf(t);
  if (refs.tile.dataset.type !== type) {
    refs.tile.dataset.type = type;
    refs.tile.replaceChildren(typeIcon(type));
  }
  refs.name.textContent = t.filename || t.title || t.url;
  refs.name.title = t.file_path || t.url;
  refs.name.classList.toggle("clickable", t.status === "COMPLETED");
  refs.name.classList.toggle("struck", t.status === "FILE_REMOVED");
  refs.tag.hidden = !t.playlist;
  refs.tag.textContent = t.playlist ? "playlist" : "";

  // progress: per-connection segments while a multi-connection transfer runs
  const segs = t.segments || [];
  const showSegments = t.status === "DOWNLOADING" && segs.length > 1 && t.total_size > 0;
  refs.segments.hidden = !showSegments;
  refs.bar.hidden = showSegments;
  if (showSegments) {
    const blocks = segs.map((s) => {
      const i = document.createElement("i");
      i.style.left = `${(s.start / t.total_size) * 100}%`;
      i.style.width = `${Math.max(0.3, ((s.current - s.start) / t.total_size) * 100)}%`;
      i.className = s.completed ? "complete" : s.active ? "active" : "";
      return i;
    });
    refs.segments.replaceChildren(...blocks);
  } else {
    const indeterminate = ACTIVE.has(t.status) && !t.total_size;
    refs.bar.classList.toggle("indeterminate", indeterminate);
    refs.bar.firstChild.style.width = `${t.status === "COMPLETED" ? 100 : Math.min(100, t.percent || 0)}%`;
  }

  // status line
  const sizeText = t.total_size ? `${fmtBytes(t.downloaded)} of ${fmtBytes(t.total_size)}` : t.downloaded ? fmtBytes(t.downloaded) : "";
  const label = {
    QUEUED: "Queued", INITIALIZING: "Starting…", DOWNLOADING: `${Math.floor(t.percent || 0)}%`, PAUSED: "Paused",
    COMPLETED: "Completed", ERROR: "Failed", CANCELLED: "Cancelled", FILE_REMOVED: "File deleted",
  }[t.status] || t.status;
  refs.status.textContent = st === "done" || st === "failed" ? label : [label, sizeText].filter(Boolean).join(" · ");
  refs.right.textContent = t.status === "DOWNLOADING"
    ? [t.speed ? `${fmtBytes(t.speed)}/s` : "", fmtEta(t.eta)].filter(Boolean).join(" · ")
    : st === "done" ? [fmtBytes(t.total_size || t.downloaded), fmtAgo(t.created_at)].filter(Boolean).join(" · ")
      : t.status === "PAUSED" && t.resumable === false ? "restarts from 0" : "";
  refs.error.hidden = !(t.status === "ERROR" && t.error);
  refs.error.textContent = t.error || "";

  // actions (rebuilt only when the set changes)
  const actions = [];
  if (ACTIVE.has(t.status)) {
    if (t.kind !== "media" && t.status === "DOWNLOADING") actions.push(["pause", "Pause", "pause"]);
    actions.push(["x", "Cancel", "remove", "danger"]);
  } else if (t.status === "PAUSED") {
    actions.push(["play", "Resume", "resume"], ["x", "Cancel", "remove", "danger"]);
  } else if (t.status === "COMPLETED") {
    actions.push(["folder", "Show in folder", "open"], ["copy", "Copy link", "copy"], ["trash", "Remove from list (keeps the file)", "remove"]);
  } else {
    actions.push(["retry", "Try again", "resume"], ["copy", "Copy link", "copy"], ["trash", "Remove from list", "remove"]);
  }
  const sig = actions.map((a) => a[2]).join(",");
  if (card.sig !== sig) {
    card.sig = sig;
    refs.actions.replaceChildren(...actions.map(([ic, title, action, cls]) =>
      h("button", { class: `icon-btn${cls ? " " + cls : ""}`, type: "button", title, "aria-label": title,
        onclick: () => taskAction(t.id, action, t) }, icon(ic, 15))));
  }
}

async function taskAction(id, action, task) {
  if (action === "copy") {
    const t = task || state.tasks.find((x) => x.id === id);
    try { await navigator.clipboard.writeText(t.page_url || t.url); toast("Link copied"); } catch { toast("Couldn't copy", "error"); }
    return;
  }
  const res = await msg("TASK_ACTION", { id, action });
  if (!res.ok) toast(res.error || "Action failed", "error");
  refreshTasks();
}

function renderChromeDownloads(items) {
  cards.clear();
  const list = $("tasks");
  const rows = items.filter((i) => i.state !== "interrupted" || i.error !== "USER_CANCELED").slice(0, 10);
  $("count-active").hidden = true;
  $("total-speed").textContent = `${rows.filter((i) => i.state === "in_progress").length} in Chrome`;
  if (!rows.length) { list.replaceChildren(emptyState()); return; }
  list.replaceChildren(...rows.map((item) => {
    const name = (item.filename || item.url).split(/[\\/]/).pop();
    const fake = { filename: name, kind: "file", content_type: item.mime };
    const pct = item.totalBytes > 0 ? (item.bytesReceived / item.totalBytes) * 100 : 0;
    const st = item.state === "complete" ? "done" : item.state === "in_progress" ? "active" : "failed";
    return h("div", { class: "task", role: "listitem", "data-state": st },
      h("div", { class: "type-tile", "data-type": typeOf(fake) }, typeIcon(typeOf(fake))),
      h("div", { class: "task-main" },
        h("div", { class: "task-top" }, h("div", { class: "task-name", text: name, title: item.filename }), h("span", { class: "task-tag", text: "chrome" })),
        h("div", { class: "progress" }, h("div", { class: "progress-fill", style: `width:${st === "done" ? 100 : pct}%` })),
        h("div", { class: "task-sub" },
          h("span", { class: "status-text", text: st === "done" ? "Completed" : st === "active" ? `${Math.floor(pct)}%` : "Interrupted" }),
          h("span", { text: item.totalBytes > 0 ? fmtBytes(item.totalBytes) : fmtBytes(item.bytesReceived) }))));
  }));
}

document.querySelectorAll(".filter").forEach((f) => f.addEventListener("click", () => {
  state.filter = f.dataset.filter;
  document.querySelectorAll(".filter").forEach((x) => x.setAttribute("aria-checked", String(x === f)));
  cards.clear();
  $("tasks").replaceChildren();
  refreshTasks();
}));

$("btn-clear-done").addEventListener("click", async () => {
  if (state.engine) {
    const res = await msg("CLEAR_COMPLETED");
    toast(res.ok ? `Cleared ${res.cleared} item${res.cleared === 1 ? "" : "s"} (files stay on disk)` : res.error, res.ok ? "" : "error");
  } else {
    chrome.downloads.erase({ state: "complete" }, () => toast("Cleared Chrome's finished downloads"));
  }
  refreshTasks();
});

$("btn-open-folder").addEventListener("click", async () => {
  if (state.engine) await msg("OPEN_FOLDER");
  else chrome.downloads.showDefaultFolder();
});

// ------------------------------------------------------------------ composer + smart preview
const input = $("url-input");
const preview = $("preview");
let analyzeTimer = 0;
let analyzeSeq = 0;

input.addEventListener("input", () => {
  clearTimeout(analyzeTimer);
  const url = input.value.trim();
  if (!isHttp(url)) { hidePreview(); return; }
  analyzeTimer = setTimeout(() => analyze(url), 450);
});
input.addEventListener("paste", () => setTimeout(() => { if (isHttp(input.value.trim())) analyze(input.value.trim()); }, 0));

$("btn-paste").addEventListener("click", async () => {
  try {
    const text = (await navigator.clipboard.readText()).trim();
    if (!isHttp(text)) { toast("Clipboard doesn't contain a link", "error"); return; }
    input.value = text;
    analyze(text);
  } catch {
    toast("Allow clipboard access, or paste with Ctrl+V", "error");
  }
});

$("composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = input.value.trim();
  if (!isHttp(url)) { toast("Enter a full link starting with http(s)://", "error"); input.focus(); return; }
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

async function analyze(url) {
  const seq = ++analyzeSeq;
  state.preview = { url, loading: true };
  setPreview(h("div", { class: "loading" }, h("span", { class: "spinner" }), h("span", { text: `Checking ${hostOf(url)}…` })));

  if (!state.engine) {
    const name = decodeURIComponent(new URL(url).pathname.split("/").pop() || "") || hostOf(url);
    const go = () => startFile(url, name);
    state.preview = { url, primary: go };
    setPreview(
      h("div", { class: "preview-row" }, tile("file"), h("div", { class: "preview-name", text: name })),
      h("div", { class: "preview-note", text: "Engine is off — this will use Chrome's normal downloader. Videos and playlists need the engine." }),
      h("div", { class: "preview-actions" }, h("button", { class: "btn primary small", type: "button", onclick: go }, icon("download", 14), "Download with Chrome")));
    return;
  }

  const { mediaSite } = await msg("IS_MEDIA_SITE", { url });
  if (mediaSite) return analyzeMedia(url, seq, preview);

  const res = await msg("INSPECT", { url });
  if (seq !== analyzeSeq) return;
  if (!res.ok) {
    state.preview = { url, primary: () => startFile(url) };
    setPreview(h("div", { class: "preview-row" }, tile("alert"), h("div", { class: "preview-name", text: hostOf(url) })),
      h("div", { class: "preview-note", text: `Couldn't check this link (${res.error}). You can still try downloading it.` }),
      h("div", { class: "preview-actions" }, h("button", { class: "btn primary small", type: "button", onclick: state.preview.primary }, icon("download", 14), "Try anyway")));
    return;
  }
  if (res.is_page) return analyzeMedia(url, seq, preview, res);
  renderFilePreview(url, res);
}

function tile(type) {
  return h("div", { class: "type-tile", "data-type": type }, typeIcon(type));
}

function renderFilePreview(url, info) {
  const nameInput = h("input", { class: "preview-name", value: info.filename, "aria-label": "File name", spellcheck: "false" });
  const go = () => startFile(url, nameInput.value.trim() || info.filename);
  nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go(); } });
  state.preview = { url, primary: go };
  const type = typeOf({ filename: info.filename, content_type: info.content_type });
  setPreview(
    h("div", { class: "preview-row" }, tile(type), nameInput),
    h("div", { class: "preview-meta" },
      h("span", { class: "pill", text: info.total_size ? fmtBytes(info.total_size) : "Unknown size" }),
      info.content_type ? h("span", { class: "pill", text: info.content_type }) : null,
      info.resumable
        ? h("span", { class: "pill ok" }, icon("zap", 12), "Multi-connection · resumable")
        : h("span", { class: "pill warn", text: "Single connection (server doesn't allow splitting)" })),
    h("div", { class: "preview-actions" },
      h("button", { class: "btn ghost small", type: "button", onclick: hidePreview, text: "Cancel" }),
      h("button", { class: "btn primary small", type: "button", onclick: go }, icon("download", 14), "Download")));
}

/** Video/audio/playlist picker rendered into `target` (the composer preview or the page card). */
async function analyzeMedia(url, seq, target, inspectInfo = null) {
  const loading = h("div", { class: "loading" }, h("span", { class: "spinner" }), h("span", { text: "Finding video & audio formats…" }));
  target.hidden = false;
  target.replaceChildren(loading);
  const res = await msg("PROBE_MEDIA", { url, pageUrl: url });
  if (target === preview && seq !== analyzeSeq) return;

  const info = res.ok ? res.result : null;
  const hasMedia = info && ((info.video_formats || []).some((f) => f.format_id !== "best") || info.playlist || info.extractor !== "direct");
  if (!hasMedia) {
    if (inspectInfo) {
      // A plain web page with no video: still allow saving the page itself
      renderFilePreview(url, inspectInfo);
      preview.prepend(h("div", { class: "preview-note", text: "This link is a web page and no video was found on it." }));
      return;
    }
    target.replaceChildren(h("div", { class: "preview-row" }, tile("alert"), h("div", { class: "preview-name", text: "No video found" })),
      h("div", { class: "preview-note", text: res.error || "This page has no downloadable media, or it needs you to be logged in on this site." }));
    if (target === preview) state.preview = { url, primary: () => {} };
    return;
  }

  const videos = info.video_formats || [];
  const pl = info.playlist;
  const heights = [...new Set(videos.map((v) => v.height).filter(Boolean))].sort((a, b) => b - a);
  let mode = videos.length ? "video" : "audio";
  let quality = heights.find((x) => x <= 1080) ? `${heights.find((x) => x <= 1080)}p` : "best";
  let audioFmt = "mp3";
  let wholePlaylist = !!pl && !videos.length;

  const options = h("div", {});
  const modeSeg = h("div", { class: "segmented", role: "radiogroup", "aria-label": "Download type" });
  const addMode = (key, label) => {
    const b = h("button", { class: "chip", type: "button", role: "radio", "aria-checked": String(mode === key), text: label });
    b.addEventListener("click", () => { mode = key; modeSeg.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-checked", String(c === b))); renderOptions(); });
    modeSeg.append(b);
  };
  addMode("video", "Video");
  addMode("audio", "Audio only");

  function chipGroup(items, current, onPick) {
    const group = h("div", { class: "chips", role: "radiogroup" });
    for (const [key, label, small] of items) {
      const c = h("button", { class: "chip", type: "button", role: "radio", "aria-checked": String(key === current) }, label, small ? h("small", { text: small }) : null);
      c.addEventListener("click", () => { onPick(key); group.querySelectorAll(".chip").forEach((x) => x.setAttribute("aria-checked", String(x === c))); });
      group.append(c);
    }
    return group;
  }

  function renderOptions() {
    if (mode === "video") {
      const items = [["best", "Best"], ...heights.map((x) => {
        const f = videos.find((v) => v.height === x);
        return [`${x}p`, `${x}p`, f?.filesize ? fmtBytes(f.filesize) : ""];
      })];
      if (!items.some((i) => i[0] === quality)) quality = "best";
      options.replaceChildren(chipGroup(items, quality, (k) => { quality = k; }));
    } else {
      options.replaceChildren(chipGroup([["mp3", "MP3"], ["m4a", "M4A"], ["opus", "Opus"], ["flac", "FLAC"]], audioFmt, (k) => { audioFmt = k; }));
    }
  }
  renderOptions();

  const plToggle = pl ? h("label", { class: "setting", style: "padding:0" },
    h("span", { class: "setting-text" }, h("strong", { text: `Whole playlist · ${pl.count} videos` }), h("span", { text: pl.title })),
    (() => { const cb = h("input", { type: "checkbox", class: "switch" }); cb.checked = wholePlaylist; cb.disabled = !videos.length; cb.addEventListener("change", () => { wholePlaylist = cb.checked; }); return cb; })()) : null;

  const startBtn = h("button", { class: "btn primary small", type: "button" }, icon("download", 14), "Download");
  const go = async () => {
    startBtn.disabled = true;
    const audio = mode === "audio";
    const base = { extract_audio: audio, audio_format: audioFmt, format_id: audio ? "bestaudio" : quality, page_url: url };
    const payload = wholePlaylist && pl
      ? { ...base, entries: pl.entries.map((e) => ({ url: e.url, title: e.title })), playlist_title: pl.title }
      : { ...base, url, title: info.title };
    const r = await msg("DOWNLOAD_MEDIA", { payload });
    startBtn.disabled = false;
    if (!r.ok || r.success === false) { toast(r.error || "Couldn't start the download", "error"); return; }
    toast(wholePlaylist && pl ? `${pl.entries.length} videos queued` : "Download started");
    if (target === preview) { input.value = ""; hidePreview(); showView("downloads"); }
    refreshTasks();
  };
  startBtn.addEventListener("click", go);
  if (target === preview) state.preview = { url, primary: go };

  target.replaceChildren(
    h("div", { class: "media-head" },
      info.thumbnail ? h("img", { class: "thumb", src: info.thumbnail, alt: "", referrerpolicy: "no-referrer" }) : tile("video"),
      h("div", { style: "min-width:0" },
        h("div", { class: "media-title", text: info.title }),
        h("div", { class: "media-sub", text: [info.uploader, fmtDuration(info.duration), info.extractor].filter(Boolean).join(" · ") }))),
    videos.length ? modeSeg : null,
    options,
    plToggle,
    h("div", { class: "preview-actions" },
      target === preview ? h("button", { class: "btn ghost small", type: "button", onclick: hidePreview, text: "Cancel" }) : null,
      startBtn));
}

async function startFile(url, filename) {
  const res = await msg("DOWNLOAD_FILE", { url, filename });
  if (!res.ok || res.success === false) { toast(res.error || "Couldn't start the download", "error"); return; }
  toast(res.direct ? "Downloading with Chrome" : "Download started");
  input.value = "";
  hidePreview();
  refreshTasks();
}

// ------------------------------------------------------------------ this page
async function renderPageView() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const card = $("page-card");
  if (!tab || !isHttp(tab.url || "")) {
    card.replaceChildren(h("div", { class: "preview-note", text: "Open a web page to find its videos and media." }));
    $("streams").replaceChildren();
    return;
  }
  const findBtn = h("button", { class: "btn primary small", type: "button" }, icon("film", 14), "Find video & audio on this page");
  const result = h("div", { class: "preview", hidden: true, style: "border:none;padding:0;background:none" });
  findBtn.addEventListener("click", () => {
    if (!state.engine) { toast("Start the Veloce engine to grab videos", "error"); return; }
    findBtn.hidden = true;
    analyzeMedia(tab.url, 0, result);
  });
  card.replaceChildren(
    h("div", { class: "page-site" },
      tab.favIconUrl && /^https?:|^data:image/.test(tab.favIconUrl) ? h("img", { src: tab.favIconUrl, alt: "" }) : icon("globe", 18),
      h("div", { style: "min-width:0" }, h("div", { class: "page-title", text: tab.title || hostOf(tab.url) }), h("div", { class: "page-host", text: hostOf(tab.url) }))),
    findBtn, result);

  const res = await msg("GET_TAB_STREAMS", { tabId: tab.id });
  const streams = res.ok ? res.streams : [];
  const count = $("count-page");
  count.hidden = !streams.length;
  count.textContent = streams.length;
  const list = $("streams");
  if (!streams.length) {
    list.replaceChildren(h("div", { class: "empty" }, h("div", { class: "empty-icon" }, icon("signal", 22)),
      h("strong", { text: "No streams detected yet" }), h("span", { text: "Play the video on the page and its streams will appear here." })));
    return;
  }
  list.replaceChildren(...streams.map((s) => {
    let name = s.url;
    try { const u = new URL(s.url); name = decodeURIComponent(u.pathname.split("/").pop() || u.hostname); } catch { /* keep */ }
    const btn = h("button", { class: "icon-btn", type: "button", title: "Download", "aria-label": "Download stream" }, icon("download", 15));
    btn.addEventListener("click", async () => {
      const r = s.type === "File"
        ? await msg("DOWNLOAD_FILE", { url: s.url, referrer: tab.url })
        : await msg("DOWNLOAD_MEDIA", { payload: { url: s.url, page_url: tab.url, title: tab.title, format_id: "best", headers: { Referer: tab.url } } });
      toast(r.ok && r.success !== false ? "Download started" : r.error || r.reason || "Failed", r.ok && r.success !== false ? "" : "error");
    });
    return h("div", { class: "task", role: "listitem" },
      h("div", { class: "type-tile", "data-type": s.type === "File" ? "video" : "document" }, h("span", { style: "font:700 10px var(--mono)", text: s.type })),
      h("div", { class: "task-main" },
        h("div", { class: "task-top" }, h("div", { class: "task-name", text: name, title: s.url }), h("div", { class: "task-actions" }, btn)),
        h("div", { class: "task-sub" }, h("span", { text: s.contentType || "stream" }), h("span", { text: s.size ? fmtBytes(s.size) : "" }))));
  }));
}

// ------------------------------------------------------------------ settings
const DEFAULTS = { interceptEnabled: true, minInterceptMB: 1, connections: 16, excludedHosts: [], notifyOnComplete: true, sendCookies: true };

async function loadSettings() {
  const s = await chrome.storage.local.get(DEFAULTS);
  $("set-intercept").checked = s.interceptEnabled;
  $("set-min-size").value = s.minInterceptMB;
  $("set-connections").value = s.connections;
  $("out-connections").textContent = s.connections;
  $("set-excluded").value = (s.excludedHosts || []).join("\n");
  $("set-cookies").checked = s.sendCookies;
  $("set-notify").checked = s.notifyOnComplete;
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

function renderEngineInfo() {
  const dl = $("engine-info");
  const e = state.engine;
  const rows = e ? [
    ["Status", "Running"],
    ["Version", e.version],
    ["Saves to", e.default_download_dir],
    ["yt-dlp", e.media_support?.yt_dlp ? (e.media_support.yt_dlp_version || "available") + " · auto-updates" : "missing — videos unavailable"],
    ["ffmpeg", e.media_support?.ffmpeg ? "available" : "missing — no merging/MP3"],
  ] : [["Status", "Not running"]];
  dl.replaceChildren(...rows.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", { text: v })]));
}

// ------------------------------------------------------------------ boot
(async () => {
  await loadSettings();
  await refreshEngine();
  await refreshTasks();
  input.focus();
  setInterval(async () => {
    await refreshEngine();
    if (state.view === "downloads") refreshTasks();
  }, 1000);
})();
