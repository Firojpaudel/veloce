/* global chrome */
/**
 * Veloce content script
 *  - A floating "Download" button appears over the video you hover (YouTube incl. Shorts, TikTok,
 *    Instagram Reels/posts, X, Facebook, Vimeo, Reddit, and generic HTML5 players).
 *  - Clicking it opens a quality picker: video resolutions, audio-only (MP3/M4A/Opus), and whole
 *    playlists when the video belongs to one.
 *  - All UI lives in a Shadow DOM so page CSS can't break it (and it can't break the page).
 *    Text is always set via textContent, never innerHTML, so page data can't inject markup.
 */
(() => {
  if (window.__veloceLoaded) return;
  window.__veloceLoaded = true;

  const ICON_URL = chrome.runtime.getURL("icons/icon48.png");
  const host = location.hostname.replace(/^www\./, "");
  const onSite = (...domains) => domains.some((d) => host === d || host.endsWith("." + d));

  // ------------------------------------------------------------------ tiny DOM helper
  function h(tag, props = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "html") throw new Error("no innerHTML");
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c != null && c !== false) el.append(c instanceof Node ? c : String(c));
    return el;
  }

  const SVG_NS = "http://www.w3.org/2000/svg";
  const ICON_PATHS = {
    download: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"],
    x: ["M18 6 6 18", "M6 6l12 12"],
    film: ["M7 3v18", "M17 3v18", "M3 7.5h4", "M3 12h18", "M3 16.5h4", "M17 7.5h4", "M17 16.5h4", "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"],
    music: ["M9 18V5l12-2v13", "M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z", "M21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"],
    list: ["M8 6h13", "M8 12h13", "M8 18h13", "M3 6h.01", "M3 12h.01", "M3 18h.01"],
    check: ["M20 6 9 17l-5-5"],
    alert: ["M12 9v4", "M12 17h.01", "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"],
    signal: ["M2 20h.01", "M7 20v-4", "M12 20v-8", "M17 20V8", "M22 4v16"],
  };
  function icon(name, size = 16) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", size);
    svg.setAttribute("height", size);
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    for (const d of ICON_PATHS[name]) {
      const p = document.createElementNS(SVG_NS, "path");
      p.setAttribute("d", d);
      svg.append(p);
    }
    return svg;
  }

  const send = (msg) => new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(msg, (resp) => {
        void chrome.runtime.lastError;
        resolve(resp || { ok: false, error: "Extension unavailable — reload the page" });
      });
    } catch {
      resolve({ ok: false, error: "Extension was updated — reload the page" });
    }
  });

  const fmtBytes = (b) => {
    if (!b) return "";
    const u = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.min(Math.floor(Math.log(b) / Math.log(1024)), u.length - 1);
    return `${(b / 1024 ** i).toFixed(i >= 2 ? 1 : 0)} ${u[i]}`;
  };
  const fmtDuration = (s) => {
    if (!s) return "";
    s = Math.round(s);
    const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
    return hh ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}` : `${mm}:${String(ss).padStart(2, "0")}`;
  };
  const cleanTitle = (t) => (t || "video").replace(/\s*[-|•·]\s*(YouTube|TikTok|Instagram|X|Facebook|Vimeo)\s*$/i, "").trim();

  // ------------------------------------------------------------------ site adapters
  /** The URL yt-dlp should get for this <video>: the specific post, not the feed it sits in. */
  function canonicalUrl(video) {
    const findLink = (selector, maxDepth = 14) => {
      let el = video;
      for (let i = 0; el && i < maxDepth; i++, el = el.parentElement) {
        const a = el.matches?.(selector) ? el : el.querySelector?.(selector);
        if (a?.href) return a.href;
      }
      return null;
    };
    const path = location.pathname;

    if (onSite("youtube.com", "youtu.be")) return location.href;
    if (onSite("tiktok.com")) {
      if (/\/@[^/]+\/(video|photo)\/\d+/.test(path)) return location.href.split("?")[0];
      return findLink('a[href*="/video/"]') || location.href;
    }
    if (onSite("instagram.com")) {
      if (/^\/(reel|reels|p|tv)\/[^/]+/.test(path)) return location.href.split("?")[0];
      return findLink('a[href*="/reel/"], a[href*="/p/"]') || location.href;
    }
    if (onSite("x.com", "twitter.com")) {
      if (/\/status\/\d+/.test(path)) return location.href.split("?")[0];
      const link = findLink('a[href*="/status/"]');
      return link ? link.replace(/\/(photo|video|analytics).*$/, "") : location.href;
    }
    if (onSite("reddit.com")) return findLink('a[href*="/comments/"]') || location.href;
    return null; // generic site: decide from the <video> source / sniffed streams
  }

  const MEDIA_PAGE = () => onSite("youtube.com", "youtu.be", "tiktok.com", "instagram.com", "x.com", "twitter.com",
    "facebook.com", "fb.watch", "vimeo.com", "dailymotion.com", "twitch.tv", "reddit.com", "bilibili.com",
    "streamable.com", "threads.net");

  // The box people see as "the video". Players often keep the <video> element itself off-screen or
  // under overlays until playback starts (YouTube shows a cover image), so prefer the player container.
  const PLAYER_SELECTOR = "#movie_player, #shorts-player, .html5-video-player, .video-js, .jwplayer, .plyr, .vjs-tech, [data-testid='videoPlayer']";
  function hitRect(video) {
    const player = video.closest(PLAYER_SELECTOR);
    const r = (player || video).getBoundingClientRect();
    if (r.width >= 160 && r.height >= 120) return r;
    return video.parentElement ? video.parentElement.getBoundingClientRect() : r;
  }

  function isEligible(video) {
    const r = hitRect(video);
    if (r.width < 160 || r.height < 120) return false;
    if (onSite("youtube.com")) {
      const p = location.pathname;
      if (!/^\/(watch|shorts|embed|live)/.test(p)) return false;
      return !!video.closest("#movie_player, #shorts-player, .html5-video-player, ytd-reel-video-renderer");
    }
    return true;
  }

  // ------------------------------------------------------------------ floating hover button
  let themeChoice = "system";
  const applyHostTheme = (el) => { if (themeChoice === "system") el.removeAttribute("data-theme"); else el.setAttribute("data-theme", themeChoice); };
  try {
    chrome.storage.local.get({ theme: "system" }, (r) => { themeChoice = r.theme; applyHostTheme(badgeHost); });
    chrome.storage.onChanged.addListener((c) => { if (c.theme) { themeChoice = c.theme.newValue; applyHostTheme(badgeHost); if (modalHost) applyHostTheme(modalHost); } });
  } catch { /* extension reloaded */ }

  const badgeHost = h("div", { class: "veloce-root veloce-badge-root" });
  const badgeShadow = badgeHost.attachShadow({ mode: "closed" });
  badgeShadow.append(h("style", { text: BADGE_CSS() }));
  const badgeBtn = h("button", { class: "badge", type: "button", title: "Download with Veloce", "aria-label": "Download this video with Veloce" },
    icon("download", 14), h("span", { text: "Download" }));
  badgeShadow.append(badgeBtn);
  let badgeVideo = null;
  let hideTimer = 0;

  function placeBadge(video) {
    const r = hitRect(video);
    const vertical = r.height > r.width * 1.1;
    badgeHost.style.top = `${Math.max(8, r.top + (vertical ? 14 : 12))}px`;
    badgeHost.style.left = `${Math.min(window.innerWidth - 120, r.right - (vertical ? 108 : 112))}px`;
  }

  function showBadge(video) {
    clearTimeout(hideTimer);
    badgeVideo = video;
    if (!badgeHost.isConnected) document.documentElement.append(badgeHost);
    placeBadge(video);
    badgeHost.classList.add("visible");
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      badgeHost.classList.remove("visible");
      badgeVideo = null;
    }, 1400);
  }

  badgeHost.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  badgeHost.addEventListener("mouseleave", scheduleHide);
  badgeBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (badgeVideo) openPickerForVideo(badgeVideo);
  });

  // Live collection: the browser keeps it current, so there's no DOM query per mouse move.
  const videos = document.getElementsByTagName("video");
  let lastMove = 0;
  // Capture phase on window: players like YouTube's stop mousemove from bubbling to the document.
  window.addEventListener("mousemove", (e) => {
    if (!videos.length) return; // the common case on most pages: zero work
    const now = performance.now();
    if (now - lastMove < 90) return;
    lastMove = now;
    if (document.fullscreenElement) return;
    let hit = null;
    for (const v of videos) {
      const r = hitRect(v);
      if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom && isEligible(v)) { hit = v; break; }
    }
    if (hit) showBadge(hit);
    else if (badgeVideo && !badgeHost.matches(":hover")) scheduleHide();
  }, { passive: true, capture: true });

  window.addEventListener("scroll", () => { if (badgeVideo) placeBadge(badgeVideo); }, { passive: true, capture: true });

  // ------------------------------------------------------------------ deciding what to download
  const IN_FRAME = window.top !== window;

  async function openPickerForVideo(video) {
    if (IN_FRAME) {
      const src = video.currentSrc || video.src || video.querySelector("source")?.src || "";
      send({ type: "OPEN_PICKER_IN_TOP", url: /^https?:/i.test(src) ? src : "", frameUrl: location.href });
      return;
    }
    const pageUrl = canonicalUrl(video);
    const title = cleanTitle(document.title);
    if (pageUrl) return openPicker({ url: pageUrl, title });

    const src = video.currentSrc || video.src || video.querySelector("source")?.src || "";
    if (/^https?:/i.test(src)) return openPicker({ url: src, title, directFile: src });

    // blob:/MSE players: use what the network sniffer saw for this tab
    const { streams = [] } = await send({ type: "GET_TAB_STREAMS" });
    const ranked = [...streams].sort((a, b) => rank(b) - rank(a));
    const best = ranked[0];
    return openPicker({ url: best ? best.url : location.href, title, streams: ranked, referer: best?.referer });
  }

  function rank(s) {
    const typeScore = { HLS: 3, DASH: 2, File: 1 }[s.type] || 0;
    const master = /master|playlist|index/i.test(s.url) ? 0.5 : 0;
    return typeScore + master + Math.min(s.size / 1e10, 0.4) + s.timestamp / 1e14;
  }

  // ------------------------------------------------------------------ picker modal
  let modalHost = null;

  function closePicker() {
    modalHost?.remove();
    modalHost = null;
    document.removeEventListener("keydown", onKey, true);
  }
  function onKey(e) {
    if (e.key === "Escape") { e.stopPropagation(); closePicker(); }
  }

  async function openPicker({ url, title, streams = [], directFile = null, referer = null }) {
    closePicker();
    modalHost = h("div", { class: "veloce-root veloce-modal-root" });
    applyHostTheme(modalHost);
    const root = modalHost.attachShadow({ mode: "closed" });
    root.append(h("style", { text: MODAL_CSS() }));

    const body = h("div", { class: "body" });
    const dialog = h("div", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-label": "Veloce download options" },
      h("header", {},
        h("img", { class: "logo", src: ICON_URL, alt: "" }),
        h("div", { class: "head-text" },
          h("div", { class: "title", text: "Download" }),
          h("div", { class: "subtitle", text: `from ${hostLabel(location.href) || hostLabel(url)}` })),
        h("button", { class: "icon-btn", type: "button", "aria-label": "Close", onclick: closePicker }, icon("x", 18))),
      body);
    const backdrop = h("div", { class: "backdrop", onclick: (e) => { if (e.target === backdrop) closePicker(); } }, dialog);
    root.append(backdrop);
    toastTarget = dialog;
    document.documentElement.append(modalHost);
    document.addEventListener("keydown", onKey, true);
    dialog.querySelector(".icon-btn").focus();

    body.append(loadingView());

    const status = await send({ type: "ENGINE_STATUS" });
    if (!status.ok || !status.status) {
      body.replaceChildren(offlineView(directFile));
      return;
    }

    const probe = await send({ type: "PROBE_MEDIA", url, pageUrl: referer || location.href });
    if (!modalHost) return; // closed while loading
    if (!probe.ok) {
      body.replaceChildren(errorView(probe.error || "Couldn't read formats from this page."));
      return;
    }
    renderFormats(body, probe.result, { url, title, streams, directFile, referer });
  }

  function hostLabel(url) {
    try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
  }

  function loadingView() {
    return h("div", { class: "state" },
      h("div", { class: "spinner", "aria-hidden": "true" }),
      h("div", { class: "state-title", text: "Finding the best formats…" }),
      h("div", { class: "state-sub", text: "This takes a few seconds for most sites." }),
      h("div", { class: "skeleton" }), h("div", { class: "skeleton short" }));
  }

  function offlineView(directFile) {
    return h("div", { class: "state" },
      h("div", { class: "state-icon warn" }, icon("alert", 22)),
      h("div", { class: "state-title", text: "Veloce engine isn't running" }),
      h("div", { class: "state-sub", text: "Video and audio grabbing needs the Veloce app. Open it once, or run “veloce autostart enable” so it starts with your computer." }),
      directFile ? h("button", { class: "btn primary", type: "button", onclick: async () => {
        await send({ type: "DOWNLOAD_FILE", url: directFile, referrer: location.href });
        done("Sent to Chrome's downloader");
      } }, icon("download"), "Download file with Chrome") : null);
  }

  function errorView(message) {
    return h("div", { class: "state" },
      h("div", { class: "state-icon warn" }, icon("alert", 22)),
      h("div", { class: "state-title", text: "Couldn't get this video" }),
      h("div", { class: "state-sub", text: message.slice(0, 300) }),
      h("div", { class: "state-sub muted", text: "Private or login-only videos need you to be signed in on this site in this browser." }));
  }

  let toastTarget = null; // the open dialog element (the shadow root is closed, so we keep a reference)

  function done(message) {
    if (!modalHost || !toastTarget) return;
    const current = modalHost;
    toastTarget.append(h("div", { class: "toast", role: "status" }, icon("check"), h("span", { text: message })));
    setTimeout(() => { if (modalHost === current) closePicker(); }, 1400);
  }

  function renderFormats(body, info, ctx) {
    const videos = info.video_formats || [];
    const audios = info.audio_formats || [];
    const playlist = info.playlist;
    const title = info.title && info.title !== "video" ? info.title : ctx.title;

    const meta = h("div", { class: "media-head" },
      info.thumbnail ? h("img", { class: "thumb", src: info.thumbnail, alt: "", referrerpolicy: "no-referrer" }) : null,
      h("div", { class: "media-meta" },
        h("div", { class: "media-title", text: title }),
        h("div", { class: "media-sub", text: [info.uploader, fmtDuration(info.duration), info.extractor].filter(Boolean).join(" · ") })));

    const content = h("div", { class: "content" });
    const tabs = h("div", { class: "tabs", role: "tablist" });
    const sections = [];

    const addTab = (key, label, iconName, render) => {
      const btn = h("button", { class: "tab", type: "button", role: "tab", onclick: () => select(key) }, icon(iconName, 15), h("span", { text: label }));
      btn.dataset.key = key;
      tabs.append(btn);
      sections.push({ key, render, btn });
    };
    const select = (key) => {
      for (const s of sections) s.btn.setAttribute("aria-selected", String(s.key === key));
      content.replaceChildren(sections.find((s) => s.key === key).render());
    };

    const singleTitle = playlist && !videos.length ? playlist.title : title;
    if (videos.length || ctx.directFile) addTab("video", "Video", "film", () => videoList(videos, ctx, singleTitle));
    if (videos.length || audios.length || ctx.directFile) addTab("audio", "Audio only", "music", () => audioList(audios, ctx, singleTitle));
    if (playlist && playlist.entries?.length) addTab("playlist", `Playlist · ${playlist.count}`, "list", () => playlistView(playlist, ctx));
    if (ctx.streams?.length > 1) addTab("streams", "Detected streams", "signal", () => streamList(ctx.streams, title));

    body.replaceChildren(meta, tabs, content);
    if (!sections.length) {
      content.append(errorView("No downloadable formats were found on this page."));
      return;
    }
    select(playlist && !videos.length ? "playlist" : sections[0].key);
  }

  function row({ badge, name, sub, size, action, actionLabel = "Download", featured = false }) {
    const btn = h("button", { class: `btn ${featured ? "primary" : "ghost"} small`, type: "button" }, icon("download", 14), actionLabel);
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.replaceChildren(h("span", { class: "mini-spinner" }), "Starting…");
      const res = await action();
      if (res?.ok === false || res?.success === false) {
        btn.disabled = false;
        btn.replaceChildren(icon("alert", 14), "Retry");
        btn.title = res.error || res.reason || "Failed";
      } else {
        done("Download started");
      }
    });
    return h("div", { class: `row${featured ? " featured" : ""}` },
      h("span", { class: "res", text: badge }),
      h("div", { class: "row-text" }, h("div", { class: "row-name", text: name }), h("div", { class: "row-sub", text: [sub, size && `≈ ${size}`].filter(Boolean).join(" · ") })),
      btn);
  }

  const mediaDownload = (ctx, title, extra) => send({
    type: "DOWNLOAD_MEDIA",
    payload: { url: ctx.url, page_url: location.href, title, headers: { Referer: ctx.referer || location.href }, ...extra },
  });

  function videoList(videos, ctx, title) {
    const list = h("div", { class: "list" });
    const preferred = videos.find((v) => v.height === 1080) || videos.find((v) => v.height <= 1080) || videos[0];
    for (const v of videos) {
      list.append(row({
        badge: v.resolution,
        name: `${v.tag}${v.fps && v.fps > 30 ? ` · ${v.fps} fps` : ""}`,
        sub: v.vcodec ? `MP4 · ${v.vcodec.toUpperCase()}` : "MP4",
        size: fmtBytes(v.filesize),
        featured: v === preferred,
        action: () => mediaDownload(ctx, title, { format_id: v.height ? `${v.height}p` : v.format_id, extract_audio: false }),
      }));
    }
    if (ctx.directFile) {
      list.prepend(row({
        badge: "FILE", name: "Original file", sub: "Fastest · multi-connection", featured: true,
        action: () => send({ type: "DOWNLOAD_FILE", url: ctx.directFile, referrer: location.href }),
      }));
    }
    return list;
  }

  function audioList(audios, ctx, title) {
    const best = audios[0];
    const list = h("div", { class: "list" });
    const options = [
      { fmt: "mp3", name: "MP3", sub: "Plays everywhere · 192 kbps" },
      { fmt: "m4a", name: "M4A (AAC)", sub: "Apple devices · small" },
      { fmt: "opus", name: "Opus", sub: "Best quality per MB" },
      { fmt: "flac", name: "FLAC", sub: "Lossless container (from source audio)" },
    ];
    options.forEach((o, i) => list.append(row({
      badge: o.fmt.toUpperCase(), name: o.name, sub: o.sub,
      size: i === 0 && best ? fmtBytes(best.filesize) : "",
      featured: i === 0,
      action: () => mediaDownload(ctx, title, { extract_audio: true, audio_format: o.fmt }),
    })));
    return list;
  }

  function playlistView(pl, ctx) {
    const selected = new Set(pl.entries.map((_, i) => i));
    const countLabel = h("span", {});
    const startBtn = h("button", { class: "btn primary", type: "button" }, icon("download", 15), countLabel);
    const updateCount = () => {
      countLabel.textContent = `Download ${selected.size} of ${pl.entries.length}`;
      startBtn.disabled = selected.size === 0;
    };

    let quality = "1080p";
    const qualities = [["best", "Best"], ["1080p", "1080p"], ["720p", "720p"], ["480p", "480p"], ["mp3", "MP3 audio"]];
    const chips = h("div", { class: "chips", role: "radiogroup", "aria-label": "Quality" });
    for (const [key, label] of qualities) {
      const chip = h("button", { class: "chip", type: "button", role: "radio", "aria-checked": String(key === quality), text: label });
      chip.addEventListener("click", () => {
        quality = key;
        chips.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-checked", String(c === chip)));
      });
      chips.append(chip);
    }

    const toggleAll = h("label", { class: "check all" }, h("input", { type: "checkbox", checked: true }), h("span", { text: "Select all" }));
    const list = h("div", { class: "list entries" });
    pl.entries.forEach((e, i) => {
      const cb = h("input", { type: "checkbox", checked: true });
      cb.addEventListener("change", () => { cb.checked ? selected.add(i) : selected.delete(i); updateCount(); });
      list.append(h("label", { class: "entry" }, cb,
        h("span", { class: "entry-index", text: String(i + 1) }),
        h("span", { class: "entry-title", text: e.title }),
        h("span", { class: "entry-dur", text: fmtDuration(e.duration) })));
    });
    toggleAll.querySelector("input").addEventListener("change", (ev) => {
      const on = ev.target.checked;
      list.querySelectorAll("input").forEach((cb, i) => { cb.checked = on; on ? selected.add(i) : selected.delete(i); });
      updateCount();
    });

    startBtn.addEventListener("click", async () => {
      startBtn.disabled = true;
      countLabel.textContent = "Queuing…";
      const entries = pl.entries.filter((_, i) => selected.has(i)).map((e) => ({ url: e.url, title: e.title }));
      const audio = quality === "mp3";
      const res = await send({
        type: "DOWNLOAD_MEDIA",
        payload: {
          entries, playlist_title: pl.title, page_url: location.href,
          extract_audio: audio, audio_format: "mp3", format_id: audio ? "bestaudio" : quality,
        },
      });
      if (res.ok === false || res.success === false) {
        startBtn.disabled = false;
        updateCount();
        startBtn.title = res.error || "Failed";
      } else {
        done(`${entries.length} videos queued`);
      }
    });
    updateCount();

    return h("div", { class: "playlist" },
      h("div", { class: "pl-head" },
        h("div", {}, h("div", { class: "pl-title", text: pl.title }),
          h("div", { class: "pl-sub", text: [pl.uploader, `${pl.count} videos`].filter(Boolean).join(" · ") })),
        toggleAll),
      chips, list,
      h("div", { class: "footer" }, h("span", { class: "hint", text: `Saved in “${pl.title}” inside your Veloce folder` }), startBtn));
  }

  function streamList(streams, title) {
    const list = h("div", { class: "list" });
    for (const s of streams) {
      let name = s.url;
      try { const u = new URL(s.url); name = u.pathname.split("/").pop() || u.hostname; } catch { /* keep */ }
      list.append(row({
        badge: s.type, name, sub: s.contentType || "stream", size: fmtBytes(s.size),
        // The frame that requested a stream is the Referer its server expects (embedded players live on other domains)
        action: () => (s.type === "File"
          ? send({ type: "DOWNLOAD_FILE", url: s.url, referrer: s.referer || location.href })
          : send({ type: "DOWNLOAD_MEDIA", payload: { url: s.url, page_url: location.href, title, format_id: "best", headers: { Referer: s.referer || location.href } } })),
      }));
    }
    return list;
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (IN_FRAME) return; // only the main page shows the picker
    if (msg?.type === "OPEN_MEDIA_PICKER" && msg.fromFrame) {
      const title = cleanTitle(document.title);
      if (msg.url) { openPicker({ url: msg.url, title, directFile: msg.url, referer: msg.frameUrl }); return; }
      // blob: player inside the frame — use the streams the network sniffer saw for this tab
      send({ type: "GET_TAB_STREAMS" }).then(({ streams = [] }) => {
        const ranked = [...streams].sort((a, b) => rank(b) - rank(a));
        openPicker({ url: ranked[0]?.url || msg.frameUrl, title, streams: ranked, referer: ranked[0]?.referer || msg.frameUrl });
      });
      return;
    }
    if (msg?.type === "OPEN_MEDIA_PICKER") {
      const video = [...document.querySelectorAll("video")].find(isEligible);
      if (msg.url && msg.url !== location.href) openPicker({ url: msg.url, title: cleanTitle(document.title) });
      else if (video) openPickerForVideo(video);
      else openPicker({ url: msg.url || location.href, title: cleanTitle(document.title) });
    }
  });

  // ------------------------------------------------------------------ styles (shadow DOM)
  function THEME_VARS() {
    // Same palette as the popup and the app. Follows the OS unless the user chose a theme in Veloce settings.
    return `
      :host { all: initial; }
      * { box-sizing: border-box; }
      :host {
        --bg: #ffffff; --surface: #f5f7fb; --surface-2: #eef2f8; --border: #e3e8f1;
        --text: #0b1530; --muted: #5f6b85; --accent: #2563eb; --accent-2: #38bdf8; --accent-ink: #ffffff;
        --ok: #15803d; --warn: #b45309; --shadow: 0 24px 64px -16px rgba(11, 21, 48, .35), 0 0 0 1px rgba(11, 21, 48, .06);
        --font: ui-sans-serif, system-ui, -apple-system, "Segoe UI Variable Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-family: var(--font);
      }
      @media (prefers-color-scheme: dark) {
        :host(:not([data-theme="light"])) {
          --bg: #111a2e; --surface: #0d1428; --surface-2: #17223a; --border: #1e2a44;
          --text: #e8eefb; --muted: #8593ad; --accent: #4f8cff; --accent-2: #5cc8fa; --ok: #34c56b; --warn: #f0a63a;
          --shadow: 0 24px 64px -16px rgba(0, 0, 0, .75), 0 0 0 1px rgba(255, 255, 255, .06);
        }
      }
      :host([data-theme="dark"]) {
          --bg: #111a2e; --surface: #0d1428; --surface-2: #17223a; --border: #1e2a44;
          --text: #e8eefb; --muted: #8593ad; --accent: #4f8cff; --accent-2: #5cc8fa; --ok: #34c56b; --warn: #f0a63a;
          --shadow: 0 24px 64px -16px rgba(0, 0, 0, .75), 0 0 0 1px rgba(255, 255, 255, .06);
      }`;
  }

  function BADGE_CSS() {
    return `${THEME_VARS()}
      /* Light touch over someone else's video: small, quiet until pointed at. */
      .badge {
        display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 11px 0 9px;
        border-radius: 999px; border: 1px solid rgba(255, 255, 255, .16); cursor: pointer;
        background: rgba(11, 21, 48, .62); color: rgba(255, 255, 255, .94); font: 500 12px/1 var(--font);
        box-shadow: 0 2px 8px rgba(0, 0, 0, .18); transition: background .15s ease, border-color .15s ease;
      }
      .badge:hover { background: #2563eb; border-color: transparent; color: #fff; }
      .badge:active { background: #1d4ed8; }
      .badge:focus-visible { outline: 2px solid #38bdf8; outline-offset: 2px; }
      .badge svg { opacity: .9; }`;
  }

  function MODAL_CSS() {
    return `${THEME_VARS()}
      .backdrop { position: fixed; inset: 0; display: grid; place-items: center; padding: 16px;
        background: rgba(11, 21, 48, .45); animation: fade .15s ease-out; }
      .dialog { width: min(480px, 100%); max-height: min(640px, calc(100vh - 32px)); display: flex; flex-direction: column;
        background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 16px;
        box-shadow: var(--shadow); overflow: hidden; animation: pop .18s cubic-bezier(.2,.8,.2,1); }
      header { display: flex; align-items: center; gap: 10px; padding: 14px 14px 12px 16px; border-bottom: 1px solid var(--border); }
      .logo { width: 28px; height: 28px; border-radius: 8px; flex: none; }
      .head-text { min-width: 0; flex: 1; }
      .title { font: 650 14px/1.3 var(--font); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .subtitle { font: 500 11.5px/1.3 var(--font); color: var(--muted); margin-top: 2px; }
      .icon-btn { all: unset; display: grid; place-items: center; width: 32px; height: 32px; border-radius: 8px; color: var(--muted); cursor: pointer; }
      .icon-btn:hover { background: var(--surface-2); color: var(--text); }
      .icon-btn:focus-visible, .btn:focus-visible, .tab:focus-visible, .chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
      .body { overflow-y: auto; padding: 14px 16px 16px; display: flex; flex-direction: column; gap: 12px; }
      .media-head { display: flex; gap: 12px; align-items: center; }
      .thumb { width: 96px; height: 54px; object-fit: cover; border-radius: 8px; background: var(--surface-2); flex: none; }
      .media-meta { min-width: 0; }
      .media-title { font: 650 13.5px/1.35 var(--font); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
      .media-sub { font: 500 11.5px/1.4 var(--font); color: var(--muted); margin-top: 3px; }
      .tabs { display: flex; gap: 4px; padding: 3px; background: var(--surface-2); border-radius: 10px; }
      .tab { all: unset; flex: 1; display: inline-flex; justify-content: center; align-items: center; gap: 6px; height: 30px;
        border-radius: 8px; font: 600 12px/1 var(--font); color: var(--muted); cursor: pointer; white-space: nowrap; }
      .tab[aria-selected="true"] { background: var(--bg); color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,.12); }
      .list { display: flex; flex-direction: column; gap: 6px; }
      .row { display: flex; align-items: center; gap: 10px; padding: 9px 10px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
      .row.featured { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); background: color-mix(in srgb, var(--accent) 7%, var(--surface)); }
      .res { min-width: 54px; text-align: center; font: 700 11px/1 var(--mono); padding: 6px 6px; border-radius: 6px;
        background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
      .row-text { flex: 1; min-width: 0; }
      .row-name { font: 600 12.5px/1.3 var(--font); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .row-sub { font: 500 11px/1.3 var(--font); color: var(--muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .btn { all: unset; display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 34px; padding: 0 14px; border-radius: 9px;
        font: 650 12.5px/1 var(--font); cursor: pointer; white-space: nowrap; transition: filter .12s ease, background .12s ease; }
      .btn.small { height: 30px; padding: 0 11px; font-size: 12px; }
      .btn.primary { background: #2563eb; color: #fff; }
      .btn.primary:hover { background: #1d4ed8; }
      .btn.primary:hover { filter: brightness(1.08); }
      .btn.ghost { background: var(--surface-2); color: var(--text); }
      .btn.ghost:hover { background: color-mix(in srgb, var(--accent) 14%, var(--surface-2)); }
      .btn[disabled] { opacity: .6; cursor: default; }
      .state { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 8px; padding: 18px 8px 6px; }
      .state-icon { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 12px; background: var(--surface-2); }
      .state-icon.warn { color: var(--warn); background: color-mix(in srgb, var(--warn) 14%, transparent); }
      .state-title { font: 650 14px/1.3 var(--font); }
      .state-sub { font: 500 12px/1.5 var(--font); color: var(--muted); max-width: 360px; }
      .state-sub.muted { opacity: .8; }
      .state .btn { margin-top: 6px; }
      .spinner { width: 26px; height: 26px; border-radius: 50%; border: 3px solid var(--surface-2); border-top-color: var(--accent); animation: spin .8s linear infinite; }
      .mini-spinner { width: 12px; height: 12px; border-radius: 50%; border: 2px solid rgba(255,255,255,.35); border-top-color: currentColor; animation: spin .8s linear infinite; }
      .skeleton { width: 100%; height: 44px; border-radius: 10px; margin-top: 8px;
        background: linear-gradient(90deg, var(--surface) 0%, var(--surface-2) 50%, var(--surface) 100%); background-size: 200% 100%; animation: shimmer 1.2s infinite; }
      .skeleton.short { width: 70%; margin-top: 0; }
      .playlist { display: flex; flex-direction: column; gap: 10px; }
      .pl-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
      .pl-title { font: 650 13px/1.3 var(--font); }
      .pl-sub { font: 500 11px/1.3 var(--font); color: var(--muted); }
      .chips { display: flex; flex-wrap: wrap; gap: 6px; }
      .chip { all: unset; height: 28px; padding: 0 11px; border-radius: 999px; border: 1px solid var(--border); font: 600 11.5px/28px var(--font); cursor: pointer; color: var(--muted); }
      .chip[aria-checked="true"] { border-color: var(--accent); color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, transparent); }
      .entries { max-height: 240px; overflow-y: auto; gap: 2px; }
      .entry { display: grid; grid-template-columns: 18px 26px 1fr auto; align-items: center; gap: 8px; padding: 7px 8px; border-radius: 8px; cursor: pointer; }
      .entry:hover { background: var(--surface-2); }
      .entry-index { font: 600 11px/1 var(--mono); color: var(--muted); text-align: right; }
      .entry-title { font: 500 12px/1.3 var(--font); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .entry-dur { font: 500 11px/1 var(--mono); color: var(--muted); }
      .check { display: inline-flex; align-items: center; gap: 6px; font: 600 11.5px/1 var(--font); color: var(--muted); cursor: pointer; }
      input[type=checkbox] { accent-color: var(--accent); width: 15px; height: 15px; margin: 0; }
      .footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-top: 4px; }
      .hint { font: 500 11px/1.4 var(--font); color: var(--muted); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .toast { position: absolute; left: 50%; bottom: 16px; transform: translateX(-50%); display: flex; align-items: center; gap: 8px;
        padding: 10px 14px; border-radius: 10px; background: var(--ok); color: #fff; font: 600 12.5px/1.2 var(--font); box-shadow: var(--shadow); white-space: nowrap;
        animation: pop .2s ease-out; max-width: calc(100% - 32px); }
      .dialog { position: relative; }
      @keyframes fade { from { opacity: 0 } }
      @keyframes pop { from { opacity: 0; transform: translateY(6px) scale(.98) } }
      @keyframes spin { to { transform: rotate(360deg) } }
      @keyframes shimmer { to { background-position: -200% 0 } }
      @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }`;
  }
})();
