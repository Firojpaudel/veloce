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
    x: ["M18 6 6 18", "M6 6l12 12"],
    link: ["M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71", "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"],
    refresh: ["M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8", "M21 3v5h-5", "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16", "M8 16H3v5"],
    pause: ["M6 4h4v16H6z", "M14 4h4v16h-4z"],
    play: ["M6 3l14 9-14 9V3z"],
    retry: ["M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8", "M3 3v5h5"],
    copy: ["M8 8h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z", "M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"],
    trash: ["M3 6h18", "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6", "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"],
    zap: ["M13 2 3 14h9l-1 8 10-12h-9l1-8z"],
  };
  function icon(name, size = 16) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor",
      "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(k, v);
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
  document.querySelectorAll("[data-icon]").forEach((el) => el.prepend(icon(el.dataset.icon, el.closest(".nav") ? 17 : 16)));

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
    if (s < 60) return `${s}s left`;
    if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s left`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m left`;
  };
  const fmtAgo = (ts) => {
    if (!ts) return "";
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
    return new Date(ts * 1000).toLocaleDateString();
  };
  const fmtDuration = (s) => {
    if (!s) return "";
    s = Math.round(s);
    const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
    return hh ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}` : `${mm}:${String(ss).padStart(2, "0")}`;
  };
  const hostOf = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };
  const isHttp = (u) => /^https?:\/\/\S+$/i.test((u || "").trim());
  const store = {
    get: (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };

  let toastTimer = 0;
  function toast(text, kind = "") {
    const el = $("toast");
    el.className = `toast ${kind}`;
    el.replaceChildren(icon(kind === "error" ? "alert" : "check-circle", 16), h("span", { text }));
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 2800);
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
    all: "All downloads", active: "Downloading", done: "Completed", failed: "Needs attention", video: "Videos",
    audio: "Music & audio", document: "Documents", archive: "Archives", app: "Programs", other: "Other", settings: "Settings",
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
    document.querySelectorAll(".nav-item").forEach((b) => b.toggleAttribute("aria-current", b.dataset.filter === filter));
    document.querySelectorAll(".nav-item[aria-current]").forEach((b) => b.setAttribute("aria-current", "page"));
    $("view-title").textContent = TITLES[filter];
    const settings = filter === "settings";
    $("settings-view").hidden = !settings;
    $("list-view").hidden = settings;
    $("list-tools").hidden = settings;
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
    $("engine-text").textContent = online ? `Running${state.settings ? ` · v${state.settings.version}` : ""}` : "Engine stopped";
  }

  // ---------------------------------------------------------------- list rendering
  const rows = new Map();

  function render() {
    const list = $("rows");
    const counts = { all: 0, active: 0, done: 0, failed: 0, video: 0, audio: 0, document: 0, archive: 0, app: 0, other: 0 };
    for (const t of state.tasks) for (const k of Object.keys(counts)) if (matches(t, k)) counts[k]++;
    document.querySelectorAll("[data-count]").forEach((el) => { el.textContent = counts[el.dataset.count] || ""; });

    const q = state.search.toLowerCase();
    const visible = state.tasks.filter((t) => matches(t, state.filter) && (!q || (t.filename || t.url || "").toLowerCase().includes(q)));
    document.title = counts.active ? `(${counts.active}) Veloce` : "Veloce";

    if (state.online === false) {
      rows.clear();
      list.replaceChildren(emptyView("alert", "The Veloce engine stopped", "Start Veloce again from your apps menu or desktop, then reload this page."));
      return;
    }
    if (!visible.length) {
      rows.clear();
      list.replaceChildren(q
        ? emptyView("search", "No matches", `Nothing in ${TITLES[state.filter].toLowerCase()} matches “${state.search}”.`)
        : state.filter === "all"
          ? emptyView("download", "Your downloads will appear here", "Paste a link with Ctrl+V, use New download, or click Download on any video with the browser extension.", true)
          : emptyView(TYPE_ICON[state.filter] || "inbox", `Nothing in ${TITLES[state.filter].toLowerCase()}`, ""));
      return;
    }

    const ids = new Set(visible.map((t) => t.id));
    for (const id of [...rows.keys()]) if (!ids.has(id)) { rows.get(id).el.remove(); rows.delete(id); }
    list.querySelector(".empty")?.remove();
    visible.forEach((t, i) => {
      let row = rows.get(t.id);
      if (!row) { row = buildRow(t); rows.set(t.id, row); }
      updateRow(row, t);
      if (list.children[i] !== row.el) list.insertBefore(row.el, list.children[i] || null);
    });
  }

  function emptyView(iconName, title, text, withButton = false) {
    return h("div", { class: "empty" },
      h("div", { class: "empty-art" }, icon(iconName, 28)),
      h("strong", { text: title }),
      text ? h("span", { text }) : null,
      withButton ? h("button", { class: "btn primary", type: "button", onclick: () => openAdd() }, icon("plus"), "New download") : null);
  }

  function buildRow(t) {
    const r = {};
    r.tile = h("div", { class: "tile" });
    r.name = h("div", { class: "name" });
    r.sub = h("div", { class: "sub" });
    r.size = h("div", { class: "size" });
    r.state = h("span", { class: "state" });
    r.pct = h("span", {});
    r.bar = h("div", { class: "bar" }, h("b", {}));
    r.speed = h("div", { class: "speed" });
    r.actions = h("div", { class: "actions" });
    r.el = h("div", { class: "row", role: "listitem", tabindex: "0" },
      r.tile,
      h("div", { class: "name-cell" }, r.name, r.sub),
      r.size,
      h("div", { class: "prog" }, h("div", { class: "prog-label" }, r.state, r.pct), r.bar),
      r.speed,
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
    if (r.tile.dataset.type !== type) { r.tile.dataset.type = type; r.tile.replaceChildren(icon(TYPE_ICON[type], 18)); }
    r.name.textContent = t.filename || t.title || t.url;
    r.name.title = t.file_path || t.url;
    r.name.classList.toggle("missing", t.status === "FILE_REMOVED");

    const subParts = [t.playlist ? `Playlist · ${t.playlist}` : hostOf(t.page_url || t.url), fmtAgo(t.created_at)];
    if (t.status === "ERROR" && t.error) r.sub.replaceChildren(h("span", { class: "err", text: t.error }));
    else r.sub.textContent = subParts.filter(Boolean).join(" · ");

    r.size.textContent = t.total_size ? fmtBytes(t.total_size) : t.downloaded ? fmtBytes(t.downloaded) : "—";

    r.state.textContent = {
      QUEUED: "Queued", INITIALIZING: "Starting", DOWNLOADING: t.total_size ? `${fmtBytes(t.downloaded)} of ${fmtBytes(t.total_size)}` : "Downloading",
      PAUSED: "Paused", COMPLETED: "Completed", ERROR: "Failed", CANCELLED: "Cancelled", FILE_REMOVED: "File deleted",
    }[t.status] || t.status;
    r.pct.textContent = ACTIVE.has(t.status) || t.status === "PAUSED" ? (t.total_size ? `${Math.floor(t.percent || 0)}%` : "") : "";

    const segs = t.segments || [];
    if (t.status === "DOWNLOADING" && segs.length > 1 && t.total_size) {
      r.bar.classList.remove("indeterminate");
      r.bar.replaceChildren(...segs.map((s) => {
        const i = document.createElement("i");
        i.style.left = `${(s.start / t.total_size) * 100}%`;
        i.style.width = `${Math.max(0.4, ((s.current - s.start) / t.total_size) * 100)}%`;
        return i;
      }));
      r.bar.title = `${segs.filter((s) => s.active).length} connections working`;
    } else {
      if (!r.bar.querySelector("b")) r.bar.replaceChildren(h("b", {}));
      r.bar.classList.toggle("indeterminate", ACTIVE.has(t.status) && !t.total_size);
      r.bar.firstChild.style.width = `${t.status === "COMPLETED" ? 100 : Math.min(100, t.percent || 0)}%`;
      r.bar.title = "";
    }

    r.speed.replaceChildren(...(t.status === "DOWNLOADING"
      ? [h("span", { text: t.speed ? `${fmtBytes(t.speed)}/s` : "…" }), h("small", { text: fmtEta(t.eta) })]
      : [h("span", { text: "" })]));

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
    const sig = actions.map((a) => a[2]).join();
    if (r.sig !== sig) {
      r.sig = sig;
      r.actions.replaceChildren(...actions.map(([ic, title, action, cls]) => h("button", {
        class: `icon-btn${cls ? " " + cls : ""}`, type: "button", title, "aria-label": title,
        onclick: (e) => { e.stopPropagation(); act(t.id, action); },
      }, icon(ic, 16))));
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
      if (action === "remove" && t?.status === "COMPLETED") toast("Removed from list — the file is still in your folder");
    } catch (e) {
      toast(e.message, "error");
    }
    refresh();
  }

  // ---------------------------------------------------------------- toolbar
  $("search").addEventListener("input", (e) => { state.search = e.target.value.trim(); render(); });
  $("btn-folder").addEventListener("click", () => api("/open-folder", {}).catch((e) => toast(e.message, "error")));
  $("btn-clear").addEventListener("click", async () => {
    const res = await api("/tasks/clear-completed", {}).catch((e) => ({ error: e.message }));
    if (res.error) toast(res.error, "error");
    else toast(res.cleared ? `Cleared ${res.cleared} finished item${res.cleared === 1 ? "" : "s"} — files stay on disk` : "Nothing to clear");
    refresh();
  });

  // ---------------------------------------------------------------- keyboard & paste-anywhere
  document.addEventListener("keydown", (e) => {
    const typing = e.target.closest("input, textarea, [contenteditable]");
    if (e.key === "/" && !typing) { e.preventDefault(); $("search").focus(); return; }
    if (typing || $("add-dialog").open) return;
    const sel = state.tasks.find((t) => t.id === state.selected);
    if (!sel) return;
    if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); act(sel.id, "remove"); }
    if (e.key === "Enter" && sel.status === "COMPLETED") act(sel.id, "open");
    if (e.key === " " && sel.status === "DOWNLOADING" && sel.kind !== "media") { e.preventDefault(); act(sel.id, "pause"); }
    if (e.key === " " && sel.status === "PAUSED") { e.preventDefault(); act(sel.id, "resume"); }
  });
  document.addEventListener("paste", (e) => {
    if (e.target.closest("input, textarea") || $("add-dialog").open) return;
    const text = (e.clipboardData?.getData("text") || "").trim();
    if (isHttp(text)) { e.preventDefault(); openAdd(text); }
  });

  // ---------------------------------------------------------------- new download dialog
  const dialog = $("add-dialog");
  const urlInput = $("add-url");
  const preview = $("add-preview");
  const goBtn = $("add-go");
  let primary = null;
  let seq = 0;
  let debounce = 0;

  $("btn-new").addEventListener("click", () => openAdd());
  $("add-close").addEventListener("click", () => dialog.close());
  $("add-cancel").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { seq++; primary = null; });
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });

  function openAdd(url = "") {
    urlInput.value = url;
    resetPreview();
    dialog.showModal();
    urlInput.focus();
    if (url) analyze(url);
  }
  function resetPreview() {
    primary = null;
    goBtn.disabled = true;
    preview.replaceChildren(h("p", { class: "hint" }, "Tip: press ", h("kbd", { text: "Ctrl" }), "+", h("kbd", { text: "V" }), " anywhere in Veloce to start a download from your clipboard."));
  }
  urlInput.addEventListener("input", () => {
    clearTimeout(debounce);
    const url = urlInput.value.trim();
    if (!isHttp(url)) { resetPreview(); return; }
    debounce = setTimeout(() => analyze(url), 400);
  });
  $("add-form").addEventListener("submit", (e) => { e.preventDefault(); primary?.(); });

  function setPrimary(fn, label = "Download") {
    primary = fn;
    goBtn.disabled = !fn;
    goBtn.replaceChildren(icon("download"), label);
  }

  async function analyze(url) {
    const my = ++seq;
    setPrimary(null);
    preview.replaceChildren(h("div", { class: "loading" }, h("span", { class: "spinner" }), h("span", { text: `Checking ${hostOf(url)}…` })));
    if (isMediaSite(url)) return analyzeMedia(url, my);
    let info;
    try { info = await api("/inspect", { url }); } catch (e) {
      if (my !== seq) return;
      preview.replaceChildren(h("p", { class: "note", text: `Couldn't check this link: ${e.message}. You can still try to download it.` }));
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
      h("div", { class: "file-head" }, h("div", { class: "tile", "data-type": type }, icon(TYPE_ICON[type], 18)), name),
      h("div", { class: "pills" },
        h("span", { class: "pill", text: info.total_size ? fmtBytes(info.total_size) : "Unknown size" }),
        info.content_type ? h("span", { class: "pill", text: info.content_type }) : null,
        info.resumable ? h("span", { class: "pill ok" }, icon("zap", 13), "Multi-connection · resumable")
          : h("span", { class: "pill warn", text: "Single connection — the server doesn't allow splitting" })));
    setPrimary(() => startFile(url, name.value.trim() || info.filename));
  }

  async function analyzeMedia(url, my, inspectInfo = null) {
    preview.replaceChildren(h("div", { class: "loading" }, h("span", { class: "spinner" }), h("span", { text: "Finding video & audio formats…" })));
    let info = null;
    try { info = (await api("/media/probe", { url })).result; } catch (e) { info = null; }
    if (my !== seq) return;
    const videos = info?.video_formats || [];
    const pl = info?.playlist;
    const found = info && (pl || info.extractor !== "direct");
    if (!found) {
      if (inspectInfo) {
        renderFile(url, inspectInfo);
        preview.prepend(h("p", { class: "note", text: "This link is a web page and no video was found on it." }));
      } else {
        preview.replaceChildren(h("p", { class: "note", text: "No downloadable video was found. Private or login-only videos work through the browser extension, which uses your browser's login." }));
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
        toast(whole && pl ? `${pl.entries.length} videos queued — 3 download at a time` : "Download started");
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
          : h("div", { class: "tile", "data-type": "video" }, icon("film", 18)),
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
      ? `${yt.yt_dlp_version || "Installed"}${s.auto_update ? " · updates automatically every day" : " · automatic updates off"}`
      : "Not installed — video and audio grabbing is unavailable";
    $("set-ffmpeg").textContent = yt.ffmpeg ? "Installed — merges HD video with audio and converts to MP3"
      : "Not found — some HD formats and MP3 conversion are unavailable";
    $("about").textContent = `Veloce ${s.version} · MIT License · engine at ${location.host}`;
    $("engine-text").textContent = `Running · v${s.version}`;
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
  $("set-open-folder").addEventListener("click", () => api("/open-folder", {}));
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
      toast("Done — Veloce will start when you log in");
    } catch (e) { toast(e.message, "error"); }
    $("welcome").hidden = true;
  });
  $("welcome-dismiss").addEventListener("click", () => { store.set("welcomeDismissed", true); $("welcome").hidden = true; });

  // ---------------------------------------------------------------- boot
  loadSettings();
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  if (location.hash === "#new") openAdd();
})();
