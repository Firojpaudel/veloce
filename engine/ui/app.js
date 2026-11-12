/**
 * Veloce desktop dashboard — served by the local engine at http://127.0.0.1:9229/
 * Same-origin calls to the engine API. All remote/page text is rendered with textContent.
 */
(() => {
  // ---------------------------------------------------------------- icons (Lucide-style, MIT)
  const ICONS = {
    plus: ["M12 5v14", "M5 12h14"],
    inbox: ["M22 12h-6l-2 3h-4l-2-3H2", "M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"],
    download: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"],
    "check-circle": ["M22 11.08V12a10 10 0 1 1-5.93-9.14", "M22 4 12 14.01l-3-3"],
    check: ["M20 6 9 17l-5-5"],
    alert: ["M12 9v4", "M12 17h.01", "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"],
    film: ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M7 3v18", "M17 3v18", "M3 12h18", "M3 7.5h4", "M3 16.5h4", "M17 7.5h4", "M17 16.5h4"],
    music: ["M9 18V5l12-2v13", "M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z", "M21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"],
    document: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6", "M16 13H8", "M16 17H8", "M10 9H8"],
    archive: ["M21 8v13H3V8", "M1 3h22v5H1z", "M10 12h4"],
    app: ["M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z", "M3.27 6.96 12 12.01l8.73-5.05", "M12 22.08V12"],
    image: ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z", "M21 15l-5-5L5 21"],
    file: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6"],
    settings: ["M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"],
    search: ["M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z", "M21 21l-4.3-4.3"],
    folder: ["M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"],
    sweep: ["M3 6h18", "M8 6V4h8v2", "M6 6l1 14h10l1-14", "M10 11v6", "M14 11v6"],
    x: ["M18 6 6 18", "M6 6l12 12"],
    link: ["M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71", "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"],
    pause: ["M8 5v14", "M16 5v14"],
    play: ["M7 4l13 8-13 8V4z"],
    retry: ["M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", "M3 3v5h5"],
    copy: ["M8 8h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z", "M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"],
    trash: ["M3 6h18", "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6", "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"],
    zap: ["M13 2 3 14h9l-1 8 10-12h-9l1-8z"],
    arrow: ["M5 12h14", "M12 5l7 7-7 7"],
    sun: ["M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z", "M12 2v2", "M12 20v2", "M4.93 4.93l1.41 1.41", "M17.66 17.66l1.41 1.41", "M2 12h2", "M20 12h2", "M6.34 17.66l-1.41 1.41", "M19.07 4.93l-1.41 1.41"],
  moon: ["M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"],
  wifi: ["M5 12.55a11 11 0 0 1 14.08 0", "M1.42 9a16 16 0 0 1 21.16 0", "M8.53 16.11a6 6 0 0 1 6.95 0", "M12 20h.01"],
  sidebar: ["M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z", "M9 3v18"],
  power: ["M12 2v10", "M18.4 6.6a9 9 0 1 1-12.77.04"],
  refresh: ["M21 12a9 9 0 0 1-15.5 6.2L3 16", "M3 12a9 9 0 0 1 15.5-6.2L21 8", "M21 3v5h-5", "M3 21v-5h5"],
  puzzle: ["M15.4 4.5a2.5 2.5 0 1 0-4.8 0H6a1 1 0 0 0-1 1v4.1a2.5 2.5 0 1 1 0 4.8V19a1 1 0 0 0 1 1h4.6a2.5 2.5 0 1 1 4.8 0H19a1 1 0 0 0 1-1v-4.6a2.5 2.5 0 1 0 0-4.8V5.5a1 1 0 0 0-1-1z"],
  monitor: ["M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", "M8 21h8", "M12 17v4"],
  };
  function icon(name, size = 16) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor",
      "stroke-width": 1.75, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(k, v);
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

  // ---------------------------------------------------------------- collapsible sidebar
  const shell = document.querySelector(".shell");
  const sideBtn = document.getElementById("btn-sidebar");
  function setCollapsed(c) {
    shell.classList.toggle("collapsed", c);
    sideBtn.setAttribute("aria-expanded", String(!c));
    sideBtn.title = c ? "Expand sidebar ([)" : "Collapse sidebar ([)";
    sideBtn.setAttribute("aria-label", c ? "Expand sidebar" : "Collapse sidebar");
    try { localStorage.setItem("veloce-sidebar", c ? "collapsed" : "open"); } catch {}
  }
  let startCollapsed = false;
  try { startCollapsed = localStorage.getItem("veloce-sidebar") === "collapsed"; } catch {}
  setCollapsed(startCollapsed || window.innerWidth < 760);
  sideBtn.addEventListener("click", () => setCollapsed(!shell.classList.contains("collapsed")));
  document.querySelectorAll(".sidebar .nav-item, .sidebar .quick-btn").forEach((b) => {
    const label = b.querySelector("span:not([data-icon]):not(.nav-count)");
    if (label && !b.title) b.title = label.textContent;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "[" && !e.ctrlKey && !e.metaKey && !e.altKey && !/INPUT|TEXTAREA/.test(document.activeElement?.tagName || "")) {
      setCollapsed(!shell.classList.contains("collapsed"));
    }
  });

  const isMac = /mac/i.test(navigator.userAgentData?.platform || navigator.platform || "");
  if (isMac) document.getElementById("palette-kbd").textContent = "⌘K";

  // ---------------------------------------------------------------- utilities
  const $ = (id) => document.getElementById(id);
  async function api(path, body) {
    const resp = await fetch(`/api${path}`, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    let data = {};
    try { data = await resp.json(); } catch { /* empty */ }
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
  }
  const fmtBytes = (b) => {
    if (!b || b < 0) return "—";
    const u = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.min(Math.floor(Math.log(b) / Math.log(1024)), u.length - 1);
    return `${(b / 1024 ** i).toFixed(i >= 2 ? 1 : 0)} ${u[i]}`;
  };
  const fmtEta = (s) => {
    if (!s || s <= 0 || !isFinite(s)) return "";
    s = Math.round(s);
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  };
  const fmtTime = (ts) => {
    if (!ts) return "";
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    const d = new Date(ts * 1000);
    if (s < 86400 * 2) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  };
  const fmtDuration = (s) => {
    if (!s) return "";
    s = Math.round(s);
    const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
    return hh ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}` : `${mm}:${String(ss).padStart(2, "0")}`;
  };
  const hostOf = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };

  // ---------------------------------------------------------------- search: every word must match name, site or type
  const tokens = (q) => q.toLowerCase().split(/\s+/).filter(Boolean);
  function haystack(t) {
    return [t.filename, t.title, hostOf(t.url || ""), typeOf(t), TITLES[stateOf(t.status)] || ""].join(" ").toLowerCase();
  }
  const searchHit = (t, words) => !words.length || words.every((w) => haystack(t).includes(w));
  /** Text with matching words wrapped in <mark> — built from text nodes only, never HTML. */
  function highlighted(text, words) {
    text = text || "";
    if (!words.length) return [text];
    const lower = text.toLowerCase();
    const marks = new Array(text.length).fill(false);
    for (const w of words) for (let i = lower.indexOf(w); i !== -1; i = lower.indexOf(w, i + 1)) marks.fill(true, i, i + w.length);
    const out = [];
    let i = 0;
    while (i < text.length) {
      let j = i;
      while (j < text.length && marks[j] === marks[i]) j++;
      out.push(marks[i] ? h("mark", { text: text.slice(i, j) }) : text.slice(i, j));
      i = j;
    }
    return out;
  }
  const isHttp = (u) => /^https?:\/\/\S+$/i.test((u || "").trim());
  const store = {
    get: (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };

  function toast(text, kind = "") {
    const el = h("div", { class: `toast ${kind}`, role: "status" }, icon(kind === "error" ? "alert" : "check", 15), h("span", { text }));
    $("toasts").append(el);
    setTimeout(() => el.remove(), 3200);
  }

  const EXT_TYPES = {
    video: ["mp4", "mkv", "webm", "mov", "avi", "m4v", "flv", "wmv"],
    audio: ["mp3", "m4a", "aac", "flac", "wav", "ogg", "opus", "wma"],
    archive: ["zip", "rar", "7z", "tar", "gz", "xz", "bz2", "zst", "iso", "dmg", "tgz"],
    document: ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "epub", "md", "odt"],
    image: ["jpg", "jpeg", "png", "gif", "webp", "svg", "heic", "avif"],
    app: ["exe", "msi", "apk", "deb", "rpm", "appimage", "pkg", "bin", "run"],
  };
  const TYPE_ICON = { video: "film", audio: "music", archive: "archive", document: "document", image: "image", app: "app", other: "file" };
  function typeOf(t) {
    if (t.kind === "media") return t.extract_audio ? "audio" : "video";
    const ext = (t.filename || "").split(".").pop().toLowerCase();
    for (const [type, exts] of Object.entries(EXT_TYPES)) if (exts.includes(ext)) return type;
    const ct = t.content_type || "";
    if (ct.startsWith("video/")) return "video";
    if (ct.startsWith("audio/")) return "audio";
    if (ct.startsWith("image/")) return "image";
    return "other";
  }
  const ACTIVE = new Set(["QUEUED", "INITIALIZING", "DOWNLOADING"]);
  const stateOf = (s) => (ACTIVE.has(s) ? "active" : s === "COMPLETED" ? "done" : s === "PAUSED" ? "paused" : "failed");

  const MEDIA_SITES = ["youtube.com", "youtu.be", "tiktok.com", "instagram.com", "x.com", "twitter.com", "facebook.com", "fb.watch",
    "vimeo.com", "dailymotion.com", "twitch.tv", "reddit.com", "soundcloud.com", "bandcamp.com", "bilibili.com", "streamable.com"];
  const isMediaSite = (u) => { const host = hostOf(u); return MEDIA_SITES.some((d) => host === d || host.endsWith("." + d)); };

  // ---------------------------------------------------------------- state & navigation
  const state = { tasks: [], filter: "all", search: "", selected: null, online: null, settings: null };
  const TITLES = {
    all: "All downloads", active: "In progress", done: "Completed", failed: "Needs attention", video: "Videos",
    audio: "Audio", document: "Documents", archive: "Archives", app: "Programs", other: "Other", settings: "Settings",
  };

  function matches(t, filter) {
    if (filter === "all") return true;
    if (filter === "active") return ACTIVE.has(t.status) || t.status === "PAUSED";
    if (filter === "done") return t.status === "COMPLETED";
    if (filter === "failed") return ["ERROR", "CANCELLED", "FILE_REMOVED"].includes(t.status);
    return typeOf(t) === filter;
  }

  document.querySelectorAll(".nav-item").forEach((b) => b.addEventListener("click", () => go(b.dataset.filter)));
  function go(filter) {
    state.filter = filter;
    document.querySelectorAll(".nav-item").forEach((b) => {
      if (b.dataset.filter === filter) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    $("view-title").textContent = TITLES[filter];
    const settings = filter === "settings";
    $("settings-view").hidden = !settings;
    $("list-view").hidden = settings;
    $("list-tools").hidden = settings;
    $("view-count").hidden = settings;
    if (settings) loadSettings();
    else render();
  }

  // ---------------------------------------------------------------- data
  async function refresh() {
    try {
      const { tasks } = await api("/tasks");
      state.tasks = tasks || [];
      setOnline(true);
    } catch {
      setOnline(false);
    }
    if (state.filter !== "settings") render();
  }

  function setOnline(online) {
    if (state.online === online) return;
    state.online = online;
    const pill = $("engine-pill");
    pill.classList.toggle("online", online);
    pill.classList.toggle("offline", !online);
    pill.title = online ? `Engine running${state.settings ? ` · v${state.settings.version}` : ""}` : "Engine stopped — start Veloce to resume downloads";
    $("engine-text").textContent = online ? "Online" : "Offline";
  }

  // ---------------------------------------------------------------- list rendering
  const rows = new Map();
  const heads = new Map();

  function dayGroup(ts) {
    if (!ts) return "Earlier";
    const d = new Date(ts * 1000), now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
    if (ts >= start) return "Today";
    if (ts >= start - 86400) return "Yesterday";
    if (ts >= start - 6 * 86400) return d.toLocaleDateString([], { weekday: "long" });
    return "Earlier";
  }

  function render() {
    const list = $("rows");
    const counts = { all: 0, active: 0, done: 0, failed: 0, video: 0, audio: 0, document: 0, archive: 0, app: 0, other: 0 };
    for (const t of state.tasks) for (const k of Object.keys(counts)) if (matches(t, k)) counts[k]++;
    document.querySelectorAll("[data-count]").forEach((el) => { el.textContent = counts[el.dataset.count] || ""; });

    const running = state.tasks.filter((t) => t.status === "DOWNLOADING");
    const speed = running.reduce((s, t) => s + (t.speed || 0), 0);
    $("live").hidden = !running.length;
    $("live-text").textContent = `${running.length} downloading · ${fmtBytes(speed)}/s`;
    document.title = running.length ? `↓ ${fmtBytes(speed)}/s · Veloce` : "Veloce";

    const words = tokens(state.search);
    const q = words.length > 0;
    const visible = state.tasks.filter((t) => matches(t, state.filter) && searchHit(t, words));
    $("view-count").textContent = visible.length ? String(visible.length) : "";

    if (state.online === false) {
      rows.clear();
      list.replaceChildren(emptyView("alert", "Veloce isn't running", "Start Veloce from your apps menu or desktop, then reload this page."));
      return;
    }
    if (!visible.length) {
      rows.clear();
      list.replaceChildren(q ? noMatchesView(words)
        : state.filter === "all" ? emptyView("download", "No downloads yet", "Paste a link anywhere in this window, or press Download on any video with the browser extension.", true)
          : emptyView(TYPE_ICON[state.filter] || "inbox", `Nothing in ${TITLES[state.filter].toLowerCase()}`, ""));
      return;
    }

    const ids = new Set(visible.map((t) => t.id));
    for (const id of [...rows.keys()]) if (!ids.has(id)) rows.delete(id);

    const desired = [];
    let lastGroup = null;
    for (const t of visible) {
      const group = dayGroup(t.created_at);
      if (group !== lastGroup) {
        if (!heads.has(group)) heads.set(group, h("div", { class: "group-head", text: group }));
        desired.push(heads.get(group));
        lastGroup = group;
      }
      let row = rows.get(t.id);
      if (!row) { row = buildRow(t); rows.set(t.id, row); }
      updateRow(row, t);
      desired.push(row.el);
    }
    // Only touch the DOM order when it actually changed (keeps hover/focus stable during live updates)
    const current = [...list.children];
    if (current.length !== desired.length || current.some((el, i) => el !== desired[i])) list.replaceChildren(...desired);
  }

  function noMatchesView(words) {
    const elsewhere = state.filter !== "all" ? state.tasks.filter((t) => searchHit(t, words)).length : 0;
    const link = isHttp(state.search) ? state.search : null;
    const where = state.filter === "all" ? "your downloads" : TITLES[state.filter].toLowerCase();
    const clear = () => { $("search").value = ""; state.search = ""; syncSearch(); render(); $("search").focus(); };
    return h("div", { class: "empty no-match" },
      h("div", { class: "empty-art search-art" }, icon("search", 22), h("span", { class: "art-x" }, icon("x", 10))),
      h("strong", {}, "No results for ", h("q", { text: state.search })),
      h("span", { text: link ? "That looks like a link. Download it instead?" : `Nothing in ${where} matches. Try fewer or different words, or search by site (e.g. “youtube”) or type (e.g. “video”).` }),
      h("div", { class: "empty-actions" },
        link ? h("button", { class: "btn primary small", type: "button", onclick: () => { clear(); openAdd(link); } }, icon("download", 14), "Download link") : null,
        elsewhere ? h("button", { class: "btn small", type: "button", onclick: () => go("all") }, `Show ${elsewhere} in All downloads`) : null,
        h("button", { class: "btn small ghost", type: "button", onclick: clear }, "Clear search", h("kbd", { text: "Esc" }))));
  }

  function emptyView(iconName, title, text, withKeys = false) {
    return h("div", { class: "empty" },
      h("div", { class: "empty-art" }, icon(iconName, 20)),
      h("strong", { text: title }),
      text ? h("span", { text }) : null,
      withKeys ? h("div", { class: "empty-keys" },
        h("span", {}, h("kbd", { text: "N" }), "New download"),
        h("span", {}, h("kbd", { text: isMac ? "⌘V" : "Ctrl V" }), "Paste a link"),
        h("span", {}, h("kbd", { text: isMac ? "⌘K" : "Ctrl K" }), "Search")) : null);
  }

  function buildRow(t) {
    const r = {};
    r.tile = h("div", { class: "tile" });
    r.name = h("div", { class: "name" });
    r.meta = h("div", { class: "meta" });
    r.statusText = h("span", {});
    r.statusRight = h("span", { class: "right" });
    r.bar = h("div", { class: "bar" }, h("b", {}));
    r.size = h("div", { class: "size" });
    r.actions = h("div", { class: "actions" });
    r.el = h("div", { class: "row", role: "listitem", tabindex: "0" },
      r.tile,
      h("div", { class: "name-cell" }, r.name, r.meta),
      h("div", { class: "status" }, h("div", { class: "status-line" }, h("span", { class: "sdot" }), r.statusText, r.statusRight), r.bar),
      r.size,
      r.actions);
    r.el.addEventListener("click", () => select(t.id));
    r.el.addEventListener("dblclick", () => { if (r.task?.status === "COMPLETED") act(t.id, "open"); });
    r.sig = "";
    return r;
  }

  function select(id) {
    state.selected = id;
    rows.forEach((r, rid) => r.el.classList.toggle("selected", rid === id));
  }

  function updateRow(r, t) {
    r.task = t;
    const st = stateOf(t.status);
    r.el.dataset.state = st;
    r.el.classList.toggle("selected", state.selected === t.id);
    const type = typeOf(t);
    if (r.tile.dataset.type !== type) { r.tile.dataset.type = type; r.tile.replaceChildren(icon(TYPE_ICON[type], 15)); }
    r.name.replaceChildren(...highlighted(t.filename || t.title || t.url, tokens(state.search)));
    r.name.title = t.file_path || t.url;
    r.name.classList.toggle("missing", t.status === "FILE_REMOVED");

    if (t.status === "ERROR" && t.error) r.meta.replaceChildren(h("span", { class: "err", text: t.error }));
    else r.meta.textContent = [t.playlist ? `${t.playlist}` : hostOf(t.page_url || t.url), fmtTime(t.created_at)].filter(Boolean).join(" · ");

    const pct = Math.floor(t.percent || 0);
    const label = {
      QUEUED: "Queued", INITIALIZING: t.note || "Starting…", PAUSED: `Paused · ${pct}%`, COMPLETED: "Done",
      ERROR: "Failed", CANCELLED: "Cancelled", FILE_REMOVED: "File deleted",
      DOWNLOADING: t.total_size ? `${pct}%` : fmtBytes(t.downloaded),
    }[t.status] || t.status;
    r.statusText.textContent = label;
    r.statusRight.textContent = t.status === "DOWNLOADING"
      ? [t.speed ? `${fmtBytes(t.speed)}/s` : "", fmtEta(t.eta)].filter(Boolean).join(" · ") : "";

    const showBar = ACTIVE.has(t.status) || t.status === "PAUSED";
    r.bar.hidden = !showBar;
    if (showBar) {
      const segs = t.segments || [];
      if (t.status === "DOWNLOADING" && segs.length > 1 && t.total_size) {
        r.bar.classList.remove("indeterminate");
        r.bar.replaceChildren(...segs.map((s) => {
          const i = document.createElement("i");
          i.style.left = `${(s.start / t.total_size) * 100}%`;
          i.style.width = `${Math.max(0.4, ((s.current - s.start) / t.total_size) * 100)}%`;
          return i;
        }));
        r.bar.title = `${segs.filter((s) => s.active).length} connections`;
      } else {
        if (!r.bar.querySelector("b")) r.bar.replaceChildren(h("b", {}));
        r.bar.classList.toggle("indeterminate", ACTIVE.has(t.status) && !t.total_size);
        r.bar.firstChild.style.width = `${Math.min(100, t.percent || 0)}%`;
        r.bar.title = "";
      }
    }

    r.size.textContent = t.total_size ? fmtBytes(t.total_size) : t.downloaded ? fmtBytes(t.downloaded) : "—";

    const actions = [];
    if (ACTIVE.has(t.status)) {
      if (t.kind !== "media" && t.status === "DOWNLOADING") actions.push(["pause", "Pause (Space)", "pause"]);
      actions.push(["x", "Cancel", "remove", "danger"]);
    } else if (t.status === "PAUSED") {
      actions.push(["play", "Resume (Space)", "resume"], ["x", "Cancel", "remove", "danger"]);
    } else if (t.status === "COMPLETED") {
      actions.push(["folder", "Show in folder (Enter)", "open"], ["copy", "Copy link", "copy"], ["trash", "Remove from list — keeps the file", "remove"]);
    } else {
      actions.push(["retry", "Try again", "resume"], ["copy", "Copy link", "copy"], ["trash", "Remove from list", "remove"]);
    }
    const sig = actions.map((a) => a[2]).join();
    if (r.sig !== sig) {
      r.sig = sig;
      r.actions.replaceChildren(...actions.map(([ic, title, action, cls]) => h("button", {
        class: `icon-btn${cls ? " " + cls : ""}`, type: "button", title, "aria-label": title,
        onclick: (e) => { e.stopPropagation(); act(t.id, action); },
      }, icon(ic, 15))));
    }
  }

  async function act(id, action) {
    const t = state.tasks.find((x) => x.id === id);
    if (action === "copy") {
      try { await navigator.clipboard.writeText(t.page_url || t.url); toast("Link copied"); } catch { toast("Couldn't copy the link", "error"); }
      return;
    }
    try {
      await api(`/tasks/${encodeURIComponent(id)}/${action}`, {});
      if (action === "remove" && t?.status === "COMPLETED") toast("Removed from list — the file is still on disk");
    } catch (e) {
      toast(e.message, "error");
    }
    refresh();
  }

  // ---------------------------------------------------------------- toolbar
  function syncSearch() { $("search-clear").hidden = !state.search; }
  $("search").addEventListener("input", (e) => { state.search = e.target.value.trim(); syncSearch(); render(); });
  $("search").addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); if (state.search) { e.target.value = ""; state.search = ""; syncSearch(); render(); } else e.target.blur(); }
    if (e.key === "ArrowDown" || e.key === "Enter") { e.preventDefault(); e.target.blur(); const first = $("rows").querySelector(".row"); first?.click(); first?.focus(); }
  });
  $("search-clear").addEventListener("click", () => { $("search").value = ""; state.search = ""; syncSearch(); render(); $("search").focus(); });
  const openFolder = () => api("/open-folder", {}).catch((e) => toast(e.message, "error"));
  async function clearFinished() {
    try {
      const res = await api("/tasks/clear-completed", {});
      toast(res.cleared ? `Cleared ${res.cleared} finished item${res.cleared === 1 ? "" : "s"} — files stay on disk` : "Nothing to clear");
    } catch (e) { toast(e.message, "error"); }
    refresh();
  }
  $("btn-folder").addEventListener("click", openFolder);
  $("btn-clear").addEventListener("click", clearFinished);

  // ---------------------------------------------------------------- keyboard & paste-anywhere
  const anyDialogOpen = () => $("add-dialog").open || $("palette").open;
  document.addEventListener("keydown", (e) => {
    const typing = e.target.closest("input, textarea, [contenteditable]");
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
    if (typing || anyDialogOpen()) return;
    if (e.key === "/") { e.preventDefault(); $("search").focus(); return; }
    if (e.key.toLowerCase() === "n" && !e.metaKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); openAdd(); return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "j" || e.key === "k") {
      e.preventDefault();
      const order = [...$("rows").querySelectorAll(".row")].map((el) => [...rows].find(([, r]) => r.el === el)?.[0]).filter(Boolean);
      if (!order.length) return;
      const i = order.indexOf(state.selected);
      const next = order[Math.max(0, Math.min(order.length - 1, i + ((e.key === "ArrowDown" || e.key === "j") ? 1 : -1)))] || order[0];
      select(next);
      rows.get(next)?.el.scrollIntoView({ block: "nearest" });
      return;
    }
    const sel = state.tasks.find((t) => t.id === state.selected);
    if (!sel) return;
    if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); act(sel.id, "remove"); }
    if (e.key === "Enter" && sel.status === "COMPLETED") act(sel.id, "open");
    if (e.key === " " && sel.status === "DOWNLOADING" && sel.kind !== "media") { e.preventDefault(); act(sel.id, "pause"); }
    if (e.key === " " && sel.status === "PAUSED") { e.preventDefault(); act(sel.id, "resume"); }
  });
  document.addEventListener("paste", (e) => {
    if (e.target.closest("input, textarea") || anyDialogOpen()) return;
    const text = (e.clipboardData?.getData("text") || "").trim();
    if (isHttp(text)) { e.preventDefault(); openAdd(text); }
  });

  // ---------------------------------------------------------------- command palette
  const palette = $("palette");
  const pInput = $("palette-input");
  const pList = $("palette-list");
  let pItems = [];
  let pIndex = 0;
  $("btn-palette").addEventListener("click", () => openPalette());

  function commands() {
    return [
      { label: "New download", icon: "plus", hint: "N", run: () => openAdd() },
      { label: "Open downloads folder", icon: "folder", run: openFolder },
      { label: "Clear finished downloads", icon: "sweep", run: clearFinished },
      { label: "Theme: light", icon: "sun", run: () => setTheme("light") },
      { label: "Theme: dark", icon: "moon", run: () => setTheme("dark") },
      { label: "Pause all", icon: "pause", run: () => bulk("pause", (t) => t.status === "DOWNLOADING" && t.kind !== "media") },
      { label: "Resume all", icon: "play", run: () => bulk("resume", (t) => t.status === "PAUSED") },
      { label: "Retry failed downloads", icon: "retry", run: () => bulk("resume", (t) => t.status === "ERROR") },
      ...Object.entries(TITLES).map(([key, title]) => ({ label: `Go to ${title}`, icon: key === "settings" ? "settings" : "arrow", run: () => go(key) })),
    ];
  }
  async function bulk(action, pick) {
    const targets = state.tasks.filter(pick);
    await Promise.all(targets.map((t) => api(`/tasks/${encodeURIComponent(t.id)}/${action}`, {}).catch(() => {})));
    toast(targets.length ? `${targets.length} download${targets.length === 1 ? "" : "s"} updated` : "Nothing to do");
    refresh();
  }

  function openPalette() {
    if ($("add-dialog").open) return;
    pInput.value = "";
    drawPalette();
    palette.showModal();
    pInput.focus();
  }
  function drawPalette() {
    const raw = pInput.value.trim();
    const words = tokens(raw);
    const cmds = commands().filter((c) => words.every((w) => c.label.toLowerCase().includes(w)));
    const files = words.length ? state.tasks.filter((t) => searchHit(t, words)).slice(0, 8) : state.tasks.slice(0, 4);
    const fileItems = files.map((t) => ({
      group: words.length ? "Downloads" : "Recent", icon: TYPE_ICON[typeOf(t)], label: t.filename || t.title || t.url,
      sub: [hostOf(t.url || ""), t.status === "COMPLETED" ? "Open" : TITLES[stateOf(t.status)] || ""].filter(Boolean).join(" · "),
      run: () => { go("all"); select(t.id); if (t.status === "COMPLETED") act(t.id, "open"); },
    }));
    const cmdItems = cmds.map((c) => ({ ...c, group: "Commands" }));
    pItems = words.length ? [...fileItems, ...cmdItems] : [...fileItems, ...cmdItems.slice(0, 6)];
    if (isHttp(pInput.value.trim())) pItems.unshift({ group: "Link", icon: "download", label: `Download ${pInput.value.trim()}`, run: () => openAdd(pInput.value.trim()) });
    pIndex = 0;
    const nodes = [];
    let last = null;
    pItems.forEach((item, i) => {
      if (item.group !== last) { nodes.push(h("div", { class: "palette-group", text: item.group })); last = item.group; }
      const el = h("div", { class: "palette-item", role: "option", "aria-selected": String(i === pIndex) },
        h("span", { class: "palette-icon" }, icon(item.icon, 15)), h("span", { class: "label" }, ...highlighted(item.label, words)),
        item.sub ? h("span", { class: "sub", text: item.sub }) : null, item.hint ? h("kbd", { text: item.hint }) : null);
      el.addEventListener("mousemove", () => highlight(i));
      el.addEventListener("click", () => runPalette(i));
      nodes.push(el);
    });
    pList.replaceChildren(...(nodes.length ? nodes : [h("div", { class: "palette-empty" },
      h("div", { class: "empty-art search-art" }, icon("search", 20), h("span", { class: "art-x" }, icon("x", 9))),
      h("strong", {}, "No results for ", h("q", { text: raw })),
      h("span", { text: "Try a file name, a site like “youtube”, or a command like “theme”." }))]));
    $("palette-count").textContent = pItems.length ? `${pItems.length} result${pItems.length === 1 ? "" : "s"}` : "";
  }
  function highlight(i) {
    pIndex = i;
    pList.querySelectorAll(".palette-item").forEach((el, j) => el.setAttribute("aria-selected", String(j === i)));
    pList.querySelectorAll(".palette-item")[i]?.scrollIntoView({ block: "nearest" });
  }
  function runPalette(i) {
    const item = pItems[i];
    palette.close();
    item?.run();
  }
  pInput.addEventListener("input", drawPalette);
  pInput.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); highlight(Math.min(pItems.length - 1, pIndex + 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); highlight(Math.max(0, pIndex - 1)); }
    if (e.key === "Enter") { e.preventDefault(); runPalette(pIndex); }
  });
  palette.addEventListener("click", (e) => { if (e.target === palette) palette.close(); });

  // ---------------------------------------------------------------- new download sheet
  const dialog = $("add-dialog");
  const urlInput = $("add-url");
  const preview = $("add-preview");
  const goBtn = $("add-go");
  let primary = null;
  let seq = 0;
  let debounce = 0;

  $("btn-new").addEventListener("click", () => openAdd());
  $("add-cancel").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { seq++; primary = null; });
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });

  function openAdd(url = "") {
    if (palette.open) palette.close();
    urlInput.value = url;
    resetPreview();
    dialog.showModal();
    urlInput.focus();
    if (url) analyze(url);
  }
  function resetPreview() {
    setPrimary(null);
    preview.replaceChildren(h("p", { class: "hint", text: "Veloce checks the link first and shows the real file name, size and — for video pages — every quality and playlist." }));
  }
  urlInput.addEventListener("input", () => {
    clearTimeout(debounce);
    const url = urlInput.value.trim();
    if (!isHttp(url)) { resetPreview(); return; }
    debounce = setTimeout(() => analyze(url), 350);
  });
  $("add-form").addEventListener("submit", (e) => { e.preventDefault(); primary?.(); });

  function setPrimary(fn, label = "Download") {
    primary = fn;
    goBtn.disabled = !fn;
    goBtn.firstElementChild.textContent = label;
  }

  async function analyze(url) {
    const my = ++seq;
    setPrimary(null);
    preview.replaceChildren(h("div", { class: "loading" }, h("span", { class: "spinner" }), h("span", { text: `Checking ${hostOf(url)}…` })));
    if (isMediaSite(url)) return analyzeMedia(url, my);
    let info;
    try { info = await api("/inspect", { url }); } catch (e) {
      if (my !== seq) return;
      preview.replaceChildren(h("p", { class: "note", text: `Couldn't check this link: ${e.message}. You can still try downloading it.` }));
      setPrimary(() => startFile(url), "Try anyway");
      return;
    }
    if (my !== seq) return;
    if (info.is_page) return analyzeMedia(url, my, info);
    renderFile(url, info);
  }

  function renderFile(url, info) {
    const type = typeOf({ filename: info.filename, content_type: info.content_type });
    const name = h("input", { class: "name-input", value: info.filename, "aria-label": "File name", spellcheck: "false" });
    preview.replaceChildren(
      h("div", { class: "file-head" }, h("div", { class: "tile", "data-type": type }, icon(TYPE_ICON[type], 17)), name),
      h("div", { class: "pills" },
        h("span", { class: "pill", text: info.total_size ? fmtBytes(info.total_size) : "Unknown size" }),
        info.content_type ? h("span", { class: "pill", text: info.content_type }) : null,
        info.resumable ? h("span", { class: "pill ok" }, icon("zap", 12), "Multi-connection · resumable")
          : h("span", { class: "pill warn", text: "Single connection — server doesn't allow splitting" })));
    setPrimary(() => startFile(url, name.value.trim() || info.filename));
  }

  async function analyzeMedia(url, my, inspectInfo = null) {
    preview.replaceChildren(h("div", { class: "loading" }, h("span", { class: "spinner" }), h("span", { text: "Finding video & audio formats…" })));
    let info = null;
    try { info = (await api("/media/probe", { url })).result; } catch { info = null; }
    if (my !== seq) return;
    const videos = info?.video_formats || [];
    const pl = info?.playlist;
    const found = info && (pl || info.extractor !== "direct");
    if (!found) {
      if (inspectInfo) {
        renderFile(url, inspectInfo);
        preview.prepend(h("p", { class: "note", text: "This link is a web page — no video was found on it." }));
      } else {
        preview.replaceChildren(h("p", { class: "note", text: "No downloadable video found. Private or login-only videos work through the browser extension, which uses your browser's login." }));
      }
      return;
    }

    const heights = [...new Set(videos.map((v) => v.height).filter(Boolean))].sort((a, b) => b - a);
    let mode = videos.length ? "video" : "audio";
    let quality = heights.find((x) => x <= 1080) ? `${heights.find((x) => x <= 1080)}p` : "best";
    let audioFmt = "mp3";
    let whole = !!pl && !videos.length;

    const options = h("div", {});
    const seg = h("div", { class: "segmented", role: "radiogroup", "aria-label": "Type" });
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
        const items = [["best", "Best"], ...heights.map((x) => {
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

    let plRow = null;
    if (pl) {
      const sw = h("input", { type: "checkbox", class: "switch" });
      sw.checked = whole;
      sw.disabled = !videos.length;
      sw.addEventListener("change", () => { whole = sw.checked; setPrimary(go, whole ? `Download ${pl.entries.length} videos` : "Download"); });
      plRow = h("label", { class: "toggle-row" },
        h("span", { class: "setting-text" }, h("strong", { text: `Whole playlist · ${pl.count} videos` }), h("span", { text: pl.title })), sw);
    }

    async function go() {
      goBtn.disabled = true;
      const audio = mode === "audio";
      const base = { extract_audio: audio, audio_format: audioFmt, format_id: audio ? "bestaudio" : quality, page_url: url };
      const payload = whole && pl
        ? { ...base, entries: pl.entries.map((e) => ({ url: e.url, title: e.title })), playlist_title: pl.title }
        : { ...base, url, title: info.title };
      try {
        await api("/media/download", payload);
        toast(whole && pl ? `${pl.entries.length} videos queued — 3 at a time` : "Download started");
        dialog.close();
        refresh();
      } catch (e) {
        goBtn.disabled = false;
        toast(e.message, "error");
      }
    }

    preview.replaceChildren(
      h("div", { class: "media-head" },
        info.thumbnail ? h("img", { class: "thumb", src: info.thumbnail, alt: "", referrerpolicy: "no-referrer" })
          : h("div", { class: "tile", "data-type": "video" }, icon("film", 17)),
        h("div", { style: "min-width:0" },
          h("div", { class: "media-title", text: info.title }),
          h("div", { class: "media-sub", text: [info.uploader, fmtDuration(info.duration), info.extractor].filter(Boolean).join(" · ") }))),
      videos.length ? seg : null,
      options,
      plRow);
    setPrimary(go, whole && pl ? `Download ${pl.entries.length} videos` : "Download");
  }

  async function startFile(url, filename) {
    goBtn.disabled = true;
    try {
      await api("/download", { url, filename, connections: store.get("connections", 16) });
      toast("Download started");
      dialog.close();
      refresh();
    } catch (e) {
      goBtn.disabled = false;
      toast(e.message, "error");
    }
  }

  // ---------------------------------------------------------------- settings
  async function loadSettings() {
    try { state.settings = await api("/settings"); } catch { return; }
    const s = state.settings;
    $("set-autostart").checked = s.autostart;
    $("set-folder").textContent = s.download_dir;
    const conns = store.get("connections", 16);
    $("set-connections").max = s.max_connections;
    $("set-connections").value = conns;
    $("out-connections").textContent = conns;
    const yt = s.media_support || {};
    $("set-ytdlp").textContent = yt.yt_dlp
      ? `${yt.yt_dlp_version || "Installed"}${s.auto_update ? " · updates itself daily" : " · automatic updates off"}`
      : "Not installed — video and audio grabbing is unavailable";
    $("set-ffmpeg").textContent = yt.ffmpeg ? "Installed — merges HD video with audio and converts to MP3"
      : "Not found — some HD formats and MP3 conversion are unavailable";
    $("about").textContent = `Veloce ${s.version} · MIT License · ${location.host}`;
    $("tool-ytdlp").className = `tool-dot ${yt.yt_dlp ? "ok" : "missing"}`;
    $("tool-ffmpeg").className = `tool-dot ${yt.ffmpeg ? "ok" : "missing"}`;
    $("engine-pill").title = `Engine running · v${s.version}`;
    $("welcome").hidden = s.autostart || store.get("welcomeDismissed", false);
  }

  $("set-autostart").addEventListener("change", async (e) => {
    try {
      state.settings = await api("/settings", { autostart: e.target.checked });
      toast(e.target.checked ? "Veloce will start when you log in" : "Start at login turned off");
      $("welcome").hidden = true;
    } catch (err) {
      e.target.checked = !e.target.checked;
      toast(err.message, "error");
    }
  });
  $("set-open-folder").addEventListener("click", openFolder);
  $("set-connections").addEventListener("input", (e) => { $("out-connections").textContent = e.target.value; });
  $("set-connections").addEventListener("change", (e) => { store.set("connections", Number(e.target.value)); toast("Saved"); });
  $("set-update").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      const res = await api("/ytdlp/update", {});
      toast(res.updated_to ? `Updated yt-dlp to ${res.updated_to}` : "yt-dlp is up to date");
      loadSettings();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      btn.disabled = false;
    }
  });

  $("welcome-enable").addEventListener("click", async () => {
    try {
      state.settings = await api("/settings", { autostart: true });
      toast("Veloce will start when you log in");
    } catch (e) { toast(e.message, "error"); }
    $("welcome").hidden = true;
  });
  $("welcome-dismiss").addEventListener("click", () => { store.set("welcomeDismissed", true); $("welcome").hidden = true; });

  // ---------------------------------------------------------------- theme: Light or Dark (starts from the system's)
  const osDark = matchMedia("(prefers-color-scheme: dark)");
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const saved = () => { const v = store.get("veloce-theme-choice", ""); return v === "light" || v === "dark" ? v : ""; };
  const current = () => saved() || (osDark.matches ? "dark" : "light");

  function drawTheme() {
    const value = current();
    document.querySelectorAll("#set-theme button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.themeValue === value)));
    $("set-theme").style.setProperty("--idx", value === "dark" ? "1" : "0");
    const tb = $("btn-theme");
    const svg = icon(value === "dark" ? "moon" : "sun", 16);
    if (tb.dataset.value && tb.dataset.value !== value) svg.classList.add("icon-swap");
    tb.replaceChildren(svg);
    const next = value === "dark" ? "light" : "dark";
    tb.title = `Switch to ${next} theme`;
    tb.setAttribute("aria-label", `Switch to ${next} theme`);
    tb.dataset.value = value;
  }
  /** Applies a theme with a short crossfade (instant when reduced motion is on). */
  function setTheme(value) {
    if (value === current() && saved()) return;
    const apply = () => {
      document.documentElement.dataset.theme = value;
      store.set("veloce-theme-choice", value);
      try { localStorage.setItem("veloce-theme", value); } catch { /* blocked */ }
      drawTheme();
    };
    if (document.startViewTransition && !reduceMotion.matches) document.startViewTransition(apply);
    else apply();
  }
  $("btn-theme").addEventListener("click", () => setTheme(current() === "dark" ? "light" : "dark"));
  document.querySelectorAll("#set-theme button").forEach((b) => b.addEventListener("click", () => setTheme(b.dataset.themeValue)));
  osDark.addEventListener("change", () => { if (!saved()) drawTheme(); });
  if (saved()) document.documentElement.dataset.theme = saved();
  drawTheme();

  // ---------------------------------------------------------------- home-network sharing
  function drawShare(s) {
    const on = !!s?.enabled;
    $("set-share").checked = on;
    $("share-panel").hidden = !on;
    $("btn-sharing").hidden = !on;
    if (!on) return;
    $("share-url").textContent = s.url;
    $("share-code").textContent = s.code;
    $("share-copy").dataset.link = s.link;
    $("share-devices").textContent = s.devices ? `${s.devices} device${s.devices === 1 ? "" : "s"} connected` : "No devices connected yet";
  }
  async function refreshShare() {
    try { drawShare(await api("/share")); } catch { /* engine offline */ }
  }
  $("set-share").addEventListener("change", async (e) => {
    const want = e.target.checked;
    e.target.disabled = true;
    try {
      drawShare(await api("/share", { enabled: want }));
      toast(want ? "Sharing on your home network" : "Sharing turned off — connected devices lost access");
    } catch (err) {
      e.target.checked = !want;
      toast(err.message, "error");
    } finally { e.target.disabled = false; }
  });
  $("share-copy").addEventListener("click", async (e) => {
    try { await navigator.clipboard.writeText(e.currentTarget.dataset.link); toast("Link copied — it includes the access code"); }
    catch { toast("Couldn't copy", "error"); }
  });
  $("btn-sharing").addEventListener("click", () => go("settings"));
  $("share-new-code").addEventListener("click", async () => {
    try { drawShare(await api("/share", { new_code: true })); toast("New code made — connected devices need to enter it"); }
    catch (err) { toast(err.message, "error"); }
  });
  refreshShare();
  setInterval(() => { if (!document.hidden) refreshShare(); }, 10000);

  // ---------------------------------------------------------------- app updates
  async function refreshUpdate(force = false) {
    let u;
    try { u = force ? await api("/update/check", {}) : await api("/status"); } catch { return; }
    const available = force ? u.available : u.update_available;
    const latest = force ? u.latest : u.latest_version;
    const busy = force ? u.installing : u.updating;
    $("update-banner").hidden = !available;
    $("update-title").textContent = busy ? `Updating to Veloce ${latest}…` : `Veloce ${latest} is ready`;
    $("update-now").disabled = !!busy;
    $("set-version").textContent = `Veloce ${state.settings?.version || ""}`;
    $("set-update-text").textContent = busy ? `Updating to ${latest}…` : available ? `Version ${latest} is available` : "You're on the latest version";
    $("set-update-app").textContent = available ? "Update" : "Check now";
    if (u.extension_dir) $("set-ext-dir").textContent = u.extension_dir;
    if (!force) {
      const stale = !!u.extension_outdated;
      $("ext-banner").hidden = !stale || !!available;
      $("ext-title").textContent = `Browser extension ${u.extension_running || ""} is out of date (${u.extension_version} is ready)`;
      $("set-ext-status").textContent = stale
        ? `Chrome is running ${u.extension_running} from another folder, so it can't update. Remove it in chrome://extensions, then Load unpacked this folder once. After that it updates itself.`
        : u.extension_running ? `Version ${u.extension_running} is connected and up to date. It updates itself with the app.`
          : "Load this folder once at chrome://extensions (Developer mode → Load unpacked). Veloce keeps it up to date.";
      $("set-ext-status").classList.toggle("warn-text", stale);
      $("ext-setup").hidden = !!u.extension_running || !u.extension_dir || !!store.get("extSetupDismissed", false);
    }
  }
  async function startUpdate() {
    $("update-now").disabled = true;
    try {
      const r = await api("/update/install", {});
      toast(r.message);
    } catch (e) { toast(e.message, "error"); $("update-now").disabled = false; }
  }
  $("update-now").addEventListener("click", startUpdate);
  $("ext-fix").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("set-ext-dir").textContent); toast("Folder path copied — now Load unpacked it in chrome://extensions"); } catch { /* fall through */ }
    go("settings");
  });
  $("set-update-app").addEventListener("click", async () => {
    if ($("set-update-app").textContent === "Update") return startUpdate();
    await refreshUpdate(true);
    toast($("set-update-text").textContent);
  });
  const openExtFolder = () => api("/extension/open-folder", {})
    .then((r) => toast(r.success ? "In Chrome: Load unpacked → choose this folder" : "Couldn't open the folder", r.success ? "" : "error"))
    .catch((e) => toast(e.message, "error"));
  $("ext-open").addEventListener("click", openExtFolder);
  $("set-open-ext").addEventListener("click", openExtFolder);
  $("ext-copy").addEventListener("click", () => $("set-copy-ext").click());
  $("ext-dismiss").addEventListener("click", () => { store.set("extSetupDismissed", true); $("ext-setup").hidden = true; });
  $("set-copy-ext").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("set-ext-dir").textContent); toast("Folder path copied"); } catch { toast("Couldn't copy", "error"); }
  });
  refreshUpdate();
  setInterval(() => { if (!document.hidden) refreshUpdate(); }, 60000);

  // ---------------------------------------------------------------- boot
  loadSettings();
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  if (location.hash === "#new") openAdd();
  if (location.hash === "#settings") go("settings");
  if (location.hash === "#search") setTimeout(openPalette, 50);
})();
