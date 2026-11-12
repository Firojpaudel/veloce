/* global chrome */
/**
 * Veloce background service worker
 *  - Hands browser downloads to the Veloce engine (with Chrome's own filename, referrer and cookies),
 *    falling back to Chrome's downloader whenever the engine is off.
 *  - Sniffs HLS / DASH / direct media requests per tab (kept in session storage so it survives
 *    service-worker restarts).
 *  - Context menus, toolbar badge with active-download count, completion notifications.
 *  - Single message hub used by the popup and the content script.
 */

const ENGINE_API = "http://127.0.0.1:9229/api";

const DEFAULT_SETTINGS = {
  interceptEnabled: true,
  minInterceptMB: 1,
  connections: 16,
  excludedHosts: [],
  notifyOnComplete: true,
  sendCookies: true,
  theme: "system",
};

// Sites where yt-dlp should extract media from the *page* URL rather than a raw stream.
const MEDIA_SITES = [
  "youtube.com", "youtu.be", "tiktok.com", "instagram.com", "x.com", "twitter.com", "facebook.com",
  "fb.watch", "vimeo.com", "dailymotion.com", "twitch.tv", "reddit.com", "soundcloud.com", "bandcamp.com",
  "bilibili.com", "streamable.com", "pinterest.com", "threads.net", "linkedin.com",
];

const ACTIVE = new Set(["QUEUED", "INITIALIZING", "DOWNLOADING"]);

// ---------------------------------------------------------------------------- helpers

async function getSettings() {
  return chrome.storage.local.get(DEFAULT_SETTINGS);
}

function hostOf(url) {
  try { return new URL(url).hostname.toLowerCase(); } catch { return ""; }
}

function isMediaSite(url) {
  const host = hostOf(url);
  return MEDIA_SITES.some((d) => host === d || host.endsWith("." + d));
}

function isHttp(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url);
}

async function api(path, { method = "GET", body, timeout = 5000 } = {}) {
  const resp = await fetch(`${ENGINE_API}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(timeout),
  });
  let data = {};
  try { data = await resp.json(); } catch { /* empty body */ }
  if (!resp.ok) throw new Error(data.error || `Engine returned HTTP ${resp.status}`);
  return data;
}

async function engineStatus(timeout = 900) {
  try {
    return await api("/status", { timeout });
  } catch {
    return null;
  }
}

/** Cookies for a URL's site (incl. subdomains) in chrome.cookies shape, for yt-dlp's cookies.txt. */
async function siteCookies(url) {
  const { sendCookies } = await getSettings();
  if (!sendCookies || !isHttp(url)) return [];
  const host = hostOf(url).replace(/^www\./, "");
  const parts = host.split(".");
  const domain = parts.length > 2 ? parts.slice(-2).join(".") : host;
  try {
    const list = await chrome.cookies.getAll({ domain });
    return list.map((c) => ({
      name: c.name, value: c.value, domain: c.domain, path: c.path,
      secure: c.secure, httpOnly: c.httpOnly, expirationDate: c.expirationDate || 0,
    }));
  } catch {
    return [];
  }
}

/** A Cookie header for exactly this URL (file downloads). */
async function cookieHeaderFor(url) {
  const { sendCookies } = await getSettings();
  if (!sendCookies || !isHttp(url)) return "";
  try {
    const list = await chrome.cookies.getAll({ url });
    return list.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch {
    return "";
  }
}

function basename(path) {
  return (path || "").split(/[\\/]/).pop();
}

// ---------------------------------------------------------------------------- downloads

async function startFileDownload({ url, filename = "", referrer = "" }) {
  const settings = await getSettings();
  const headers = { "User-Agent": navigator.userAgent };
  if (referrer && isHttp(referrer)) headers.Referer = referrer;
  const cookie = await cookieHeaderFor(url);
  if (cookie) headers.Cookie = cookie;

  const data = await api("/download", {
    method: "POST",
    body: { url, filename: basename(filename) || undefined, connections: settings.connections, headers },
  });
  watchTasks();
  return data;
}

async function startMediaDownload(payload) {
  const pageUrl = payload.page_url || payload.url || (payload.entries && payload.entries[0]?.url) || "";
  const body = {
    ...payload,
    headers: { "User-Agent": navigator.userAgent, ...(payload.headers || {}) },
    cookies: await siteCookies(pageUrl),
  };
  const data = await api("/media/download", { method: "POST", body, timeout: 15000 });
  watchTasks();
  return data;
}

async function probeMedia(url, pageUrl) {
  return api("/media/probe", {
    method: "POST",
    body: {
      url,
      headers: { "User-Agent": navigator.userAgent, ...(pageUrl && isHttp(pageUrl) ? { Referer: pageUrl } : {}) },
      cookies: await siteCookies(pageUrl || url),
    },
    timeout: 60000,
  });
}

async function inspectLink(url) {
  const headers = { "User-Agent": navigator.userAgent };
  const cookie = await cookieHeaderFor(url);
  if (cookie) headers.Cookie = cookie;
  return api("/inspect", { method: "POST", body: { url, headers }, timeout: 20000 });
}

/** Engine-off fallback for plain files: Chrome's own downloader, into a "veloce" subfolder. */
function chromeDownload(url, filename) {
  return new Promise((resolve) => {
    const opts = { url, saveAs: false };
    const name = basename(filename);
    if (name) opts.filename = `veloce/${name}`;
    chrome.downloads.download(opts, (id) => resolve({ success: !!id, direct: true, id }));
  });
}

// ---------------------------------------------------------------------------- interception

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  // Chrome waits for suggest(); decide quickly, then always release it.
  maybeIntercept(item)
    .catch(() => {})
    .finally(() => { try { suggest(); } catch { /* already resolved */ } });
  return true;
});

async function maybeIntercept(item) {
  const settings = await getSettings();
  if (!settings.interceptEnabled) return;
  if (item.byExtensionId === chrome.runtime.id) return; // our own fallback downloads
  const url = item.finalUrl || item.url;
  if (!isHttp(url)) return; // blob:, data:, file:
  const host = hostOf(url);
  if ((settings.excludedHosts || []).some((h) => h && (host === h || host.endsWith("." + h)))) return;
  if (item.fileSize > 0 && item.fileSize < settings.minInterceptMB * 1024 * 1024) return;
  if ((item.mime || "").startsWith("text/html")) return;

  if (!(await engineStatus(700))) return; // engine off: let Chrome download normally

  try {
    await startFileDownload({ url, filename: item.filename, referrer: item.referrer });
  } catch {
    return; // engine refused: keep Chrome's download running
  }
  // Only cancel Chrome's copy after the engine accepted the job, so a failure never loses the download.
  chrome.downloads.cancel(item.id, () => {
    void chrome.runtime.lastError;
    chrome.downloads.erase({ id: item.id }, () => void chrome.runtime.lastError);
  });
}

// ---------------------------------------------------------------------------- media sniffer

const SEGMENT_RE = /\.(ts|m4s|aac|vtt|webvtt|key|jpg|png)(\?|$)|[/_-](seg|segment|chunk|frag|fragment)[-_]?\d+|[?&](range|bytestart|sq)=/i;
const tabStreams = new Map(); // tabId -> Map(url -> stream); mirrored to chrome.storage.session
const persistTimers = new Map();

async function loadTabStreams(tabId) {
  if (tabStreams.has(tabId)) return tabStreams.get(tabId);
  const key = `streams:${tabId}`;
  const stored = (await chrome.storage.session.get(key))[key] || [];
  const map = new Map(stored.map((s) => [s.url, s]));
  tabStreams.set(tabId, map);
  return map;
}

function persistTabStreams(tabId) {
  clearTimeout(persistTimers.get(tabId));
  persistTimers.set(tabId, setTimeout(() => {
    const map = tabStreams.get(tabId);
    if (map) chrome.storage.session.set({ [`streams:${tabId}`]: [...map.values()] });
  }, 400));
}

function forgetTab(tabId) {
  tabStreams.delete(tabId);
  chrome.storage.session.remove(`streams:${tabId}`);
}

chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    if (details.tabId < 0 || details.statusCode >= 400) return;
    const url = details.url;
    const lower = url.toLowerCase();
    const header = (name) =>
      (details.responseHeaders || []).find((h) => h.name.toLowerCase() === name)?.value || "";
    const contentType = header("content-type").toLowerCase();
    const size = parseInt(header("content-length"), 10) || 0;

    const isHls = /\.m3u8(\?|$)/.test(lower) || contentType.includes("mpegurl");
    const isDash = /\.mpd(\?|$)/.test(lower) || contentType.includes("dash+xml");
    const isDirect = !isHls && !isDash &&
      (contentType.startsWith("video/") || contentType.startsWith("audio/") || /\.(mp4|webm|m4a|mp3|mkv|mov)(\?|$)/.test(lower));
    if (!isHls && !isDash && !isDirect) return;
    // Skip adaptive-stream fragments and tiny files (previews, ads pings)
    if (isDirect && (SEGMENT_RE.test(lower) || (size > 0 && size < 512 * 1024) || /[?&]range=/.test(lower))) return;

    loadTabStreams(details.tabId).then((map) => {
      if (map.has(url)) return;
      map.set(url, {
        url,
        // Embedded players check where requests come from; remember the frame that asked for this stream
        referer: details.initiator && details.initiator !== "null" ? `${details.initiator}/` : "",
        type: isHls ? "HLS" : isDash ? "DASH" : "File",
        contentType,
        size,
        timestamp: Date.now(),
      });
      // Bound memory: keep the 25 most recent per tab
      if (map.size > 25) map.delete(map.keys().next().value);
      persistTabStreams(details.tabId);
    });
  },
  { urls: ["http://*/*", "https://*/*"], types: ["media", "xmlhttprequest", "other"] },
  ["responseHeaders"]
);

chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.status === "loading" && info.url) forgetTab(tabId); // real navigation (not SPA in-page)
});
chrome.tabs.onRemoved.addListener(forgetTab);

// ---------------------------------------------------------------------------- context menus

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "veloce-link", title: "Download link with Veloce", contexts: ["link"] });
    chrome.contextMenus.create({ id: "veloce-media", title: "Download this media with Veloce", contexts: ["video", "audio"] });
    chrome.contextMenus.create({ id: "veloce-page", title: "Grab video from this page with Veloce", contexts: ["page"] });
  });
  chrome.alarms.create("veloce-watch", { periodInMinutes: 1 });
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create("veloce-watch", { periodInMinutes: 1 });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "veloce-watch") watchTasks();
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const engine = await engineStatus();
  if (info.menuItemId === "veloce-link") {
    const url = info.linkUrl;
    if (isMediaSite(url) && engine && tab?.id >= 0) {
      chrome.tabs.sendMessage(tab.id, { type: "OPEN_MEDIA_PICKER", url }, () => void chrome.runtime.lastError);
      return;
    }
    if (engine) startFileDownload({ url, referrer: info.pageUrl }).catch(() => chromeDownload(url));
    else chromeDownload(url);
    return;
  }
  if (!tab || tab.id < 0) return;
  if (!engine) {
    notify("veloce-offline", "Veloce engine is off", "Start the Veloce app to grab videos. Plain file links still download through Chrome.");
    return;
  }
  const src = info.srcUrl && isHttp(info.srcUrl) && !isMediaSite(info.pageUrl) ? info.srcUrl : info.pageUrl;
  chrome.tabs.sendMessage(tab.id, { type: "OPEN_MEDIA_PICKER", url: src }, () => void chrome.runtime.lastError);
});

// ---------------------------------------------------------------------------- badge + notifications

let watching = false;

function notify(id, title, message, buttons) {
  chrome.notifications.create(id, {
    type: "basic",
    iconUrl: chrome.runtime.getURL("icons/icon128.png"),
    title,
    message,
    buttons,
    priority: 0,
  }, () => void chrome.runtime.lastError);
}

async function watchTasks() {
  if (watching) return;
  watching = true;
  try {
    const known = (await chrome.storage.session.get("taskStatus")).taskStatus || {};
    for (;;) {
      let tasks;
      try {
        tasks = (await api("/tasks", { timeout: 2000 })).tasks || [];
      } catch {
        chrome.action.setBadgeText({ text: "" });
        break;
      }
      const settings = await getSettings();
      let active = 0;
      for (const t of tasks) {
        if (ACTIVE.has(t.status)) active++;
        const prev = known[t.id];
        if (prev && ACTIVE.has(prev) && t.status !== prev && settings.notifyOnComplete) {
          if (t.status === "COMPLETED") {
            notify(`done:${t.id}`, "Download complete", t.filename || "File saved", [{ title: "Show in folder" }]);
          } else if (t.status === "ERROR") {
            notify(`fail:${t.id}`, "Download failed", `${t.filename || "Download"}: ${t.error || "unknown error"}`.slice(0, 180));
          }
        }
        known[t.id] = t.status;
      }
      await chrome.storage.session.set({ taskStatus: known });
      chrome.action.setBadgeBackgroundColor({ color: "#2563eb" });
      chrome.action.setBadgeTextColor?.({ color: "#ffffff" });
      chrome.action.setBadgeText({ text: active ? String(active) : "" });
      if (!active) break;
      await new Promise((r) => setTimeout(r, 1500));
    }
  } finally {
    watching = false;
  }
}

function openTaskFolder(notificationId) {
  const id = notificationId.split(":")[1];
  if (id) api(`/tasks/${id}/open`, { method: "POST" }).catch(() => {});
  chrome.notifications.clear(notificationId);
}
chrome.notifications.onButtonClicked.addListener((nid) => { if (nid.startsWith("done:")) openTaskFolder(nid); });
chrome.notifications.onClicked.addListener((nid) => { if (nid.startsWith("done:")) openTaskFolder(nid); });

// ---------------------------------------------------------------------------- message hub

const handlers = {
  async ENGINE_STATUS() {
    return { status: await engineStatus() };
  },
  async LIST_TASKS() {
    return api("/tasks", { timeout: 2000 });
  },
  async TASK_ACTION({ id, action }) {
    const res = await api(`/tasks/${encodeURIComponent(id)}/${action}`, { method: "POST" });
    watchTasks();
    return res;
  },
  async CLEAR_COMPLETED() {
    return api("/tasks/clear-completed", { method: "POST" });
  },
  async OPEN_FOLDER() {
    return api("/open-folder", { method: "POST" });
  },
  async INSPECT({ url }) {
    return inspectLink(url);
  },
  async PROBE_MEDIA({ url, pageUrl }) {
    return probeMedia(url, pageUrl);
  },
  async DOWNLOAD_FILE({ url, filename, referrer }) {
    if (await engineStatus()) return startFileDownload({ url, filename, referrer });
    return chromeDownload(url, filename);
  },
  async DOWNLOAD_MEDIA({ payload }) {
    if (!(await engineStatus())) return { success: false, reason: "ENGINE_REQUIRED" };
    return startMediaDownload(payload);
  },
  async GET_TAB_STREAMS({ tabId }, sender) {
    const id = tabId ?? sender.tab?.id;
    if (id == null || id < 0) return { streams: [] };
    const map = await loadTabStreams(id);
    return { streams: [...map.values()].sort((a, b) => b.timestamp - a.timestamp) };
  },
  async OPEN_PICKER_IN_TOP({ url, frameUrl }, sender) {
    if (!sender.tab || sender.tab.id < 0) return {};
    chrome.tabs.sendMessage(sender.tab.id, { type: "OPEN_MEDIA_PICKER", url, frameUrl, fromFrame: true }, { frameId: 0 },
      () => void chrome.runtime.lastError);
    return {};
  },
  async PREFETCH_MEDIA({ url, pageUrl }) {
    if (!isHttp(url) || !(await engineStatus(500))) return {};
    const headers = { "User-Agent": navigator.userAgent, ...(pageUrl && isHttp(pageUrl) ? { Referer: pageUrl } : {}) };
    api("/media/prefetch", { method: "POST", body: { url, headers, cookies: await siteCookies(pageUrl || url) }, timeout: 5000 })
      .catch(() => {});
    return {};
  },
  async IS_MEDIA_SITE({ url }) {
    return { mediaSite: isMediaSite(url) };
  },
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const handler = handlers[message?.type];
  if (!handler) return false;
  handler(message, sender)
    .then((data) => sendResponse({ ok: true, ...data }))
    .catch((err) => sendResponse({ ok: false, error: err.message || String(err) }));
  return true; // async response
});

watchTasks();
