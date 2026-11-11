/* global chrome */
/**
 * VELOCE BACKGROUND SERVICE WORKER
 * - Intercepts downloads & forwards to engine if available, or falls back to native download.
 * - Deep Media Network Sniffer (HLS, DASH, direct MP4).
 */

const ENGINE_API = "http://127.0.0.1:9229/api";
let interceptEnabled = true;

const tabStreams = new Map();

chrome.storage.local.get(["interceptEnabled"], (res) => {
  if (res.interceptEnabled !== undefined) {
    interceptEnabled = res.interceptEnabled;
  }
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.interceptEnabled) {
    interceptEnabled = changes.interceptEnabled.newValue;
  }
});

// Media Network Sniffer
chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    if (details.tabId < 0) return;

    const url = details.url;
    const lowerUrl = url.toLowerCase();

    let contentType = "";
    if (details.responseHeaders) {
      const ctHeader = details.responseHeaders.find(h => h.name.toLowerCase() === "content-type");
      if (ctHeader && ctHeader.value) contentType = ctHeader.value.toLowerCase();
    }

    const isHls = lowerUrl.includes(".m3u8") || contentType.includes("application/vnd.apple.mpegurl") || contentType.includes("application/x-mpegurl");
    const isDash = lowerUrl.includes(".mpd") || contentType.includes("application/dash+xml");
    const isDirectMedia = contentType.startsWith("video/") || contentType.startsWith("audio/") ||
                          lowerUrl.endsWith(".mp4") || lowerUrl.endsWith(".webm") || lowerUrl.endsWith(".m4a");

    if (isHls || isDash || isDirectMedia) {
      if (!tabStreams.has(details.tabId)) {
        tabStreams.set(details.tabId, new Map());
      }
      tabStreams.get(details.tabId).set(url, {
        url: url,
        type: isHls ? "HLS" : (isDash ? "DASH" : "Direct"),
        contentType: contentType,
        timestamp: Date.now()
      });
    }
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading") {
    tabStreams.delete(tabId);
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  tabStreams.delete(tabId);
});

// Intercept browser regular downloads only if engine is alive
chrome.downloads.onCreated.addListener(async (downloadItem) => {
  if (!interceptEnabled) return;

  const url = downloadItem.url || downloadItem.finalUrl;
  if (!url || url.startsWith("blob:") || url.startsWith("data:") || url.startsWith("chrome-extension:")) {
    return;
  }

  // Check if engine is alive
  try {
    const statusResp = await fetch(`${ENGINE_API}/status`, { signal: AbortSignal.timeout(600) });
    if (!statusResp.ok) return;

    // Engine is alive, cancel native single-stream download and pass to Veloce
    chrome.downloads.cancel(downloadItem.id, () => {
      chrome.downloads.erase({ id: downloadItem.id });
    });
    sendToEngine(url, downloadItem.filename);
  } catch (err) {
    // Engine offline: do nothing, allow Chrome native download to proceed normally
  }
});

// Message Hub
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "GET_TAB_STREAMS") {
    const tabId = sender.tab ? sender.tab.id : message.tabId;
    const streams = tabId && tabStreams.has(tabId) ? Array.from(tabStreams.get(tabId).values()) : [];
    sendResponse({ streams });
    return true;
  }

  if (message.type === "DOWNLOAD_URL" || message.type === "DOWNLOAD_STREAM") {
    const targetUrl = message.url || (message.payload ? message.payload.url : "");
    const filename = message.filename || (message.payload ? `${message.payload.title || 'video'}.mp4` : "download.mp4");

    // Try engine first
    fetch(`${ENGINE_API}/status`, { signal: AbortSignal.timeout(800) })
      .then(res => res.json())
      .then(() => {
        // Engine online: handle full multi-stream or yt-dlp media extraction
        if (message.type === "DOWNLOAD_STREAM") {
          return fetch(`${ENGINE_API}/media/download`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(message.payload)
          });
        } else {
          return sendToEngine(targetUrl, filename);
        }
      })
      .then(res => sendResponse({ success: true }))
      .catch(() => {
        // Fallback when engine is offline:
        // NEVER download a webpage HTML URL as a video
        const isStreamingSite = targetUrl.includes("youtube.com") || targetUrl.includes("youtu.be") ||
                                targetUrl.includes("vimeo.com") || targetUrl.includes("twitch.tv") ||
                                targetUrl.startsWith("blob:");

        if (isStreamingSite) {
          chrome.notifications.create({
            type: "basic",
            iconUrl: "../icons/icon48.png",
            title: "Veloce Engine Offline",
            message: "Start the engine first: run veloce-windows-x64.exe (Windows) or ./veloce (Linux/Mac)."
          });
          sendResponse({ success: false, reason: "ENGINE_REQUIRED" });
          return;
        }

        // Direct downloadable file (e.g. .mp4, .zip, .iso, .pdf)
        if (targetUrl.startsWith("http://") || targetUrl.startsWith("https://")) {
          chrome.downloads.download({
            url: targetUrl,
            filename: filename,
            saveAs: false
          }, (dlId) => {
            sendResponse({ success: !!dlId, direct: true });
          });
        } else {
          sendResponse({ success: false, error: "Invalid URL" });
        }
      });
    return true;
  }

  if (message.type === "PROBE_MEDIA") {
    fetch(`${ENGINE_API}/media/probe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: message.url, headers: { "User-Agent": navigator.userAgent } })
    })
      .then(res => res.json())
      .then(data => sendResponse(data))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
});

async function sendToEngine(url, suggestedFilename = "", headers = {}) {
  const payload = {
    url: url,
    connections: 16,
    headers: { "User-Agent": navigator.userAgent, ...headers }
  };
  const resp = await fetch(`${ENGINE_API}/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return await resp.json();
}
