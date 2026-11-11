/**
 * VELOCE BACKGROUND SERVICE WORKER (Manifest V3)
 * - Intercepts regular downloads & reroutes to multi-stream engine.
 * - Deep Network Sniffer: Intercepts HLS (.m3u8), DASH (.mpd), and MSE video/audio streams.
 * - Maintains active tab stream inventory.
 */

const ENGINE_API = "http://127.0.0.1:9229/api";
let interceptEnabled = true;

// Tab stream cache: tabId -> Map(streamUrl -> metadata)
const tabStreams = new Map();

// Load settings
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

// Deep Media Network Sniffer
chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    if (details.tabId < 0) return;

    const url = details.url;
    const lowerUrl = url.toLowerCase();

    // Check Content-Type headers
    let contentType = "";
    if (details.responseHeaders) {
      const ctHeader = details.responseHeaders.find(h => h.name.toLowerCase() === "content-type");
      if (ctHeader && ctHeader.value) contentType = ctHeader.value.toLowerCase();
    }

    const isHls = lowerUrl.includes(".m3u8") || contentType.includes("application/vnd.apple.mpegurl") || contentType.includes("application/x-mpegurl");
    const isDash = lowerUrl.includes(".mpd") || contentType.includes("application/dash+xml");
    const isDirectMedia = contentType.startsWith("video/") || contentType.startsWith("audio/") ||
                          lowerUrl.endsWith(".mp4") || lowerUrl.endsWith(".m4s") || lowerUrl.endsWith(".webm") || lowerUrl.endsWith(".mp3");

    if (isHls || isDash || isDirectMedia) {
      if (!tabStreams.has(details.tabId)) {
        tabStreams.set(details.tabId, new Map());
      }
      const streamMap = tabStreams.get(details.tabId);
      const streamType = isHls ? "HLS (.m3u8)" : (isDash ? "MPEG-DASH (.mpd)" : "Direct Media");

      streamMap.set(url, {
        url: url,
        type: streamType,
        contentType: contentType,
        timestamp: Date.now()
      });

      // Update extension badge to show number of detected media streams
      chrome.action.setBadgeText({
        tabId: details.tabId,
        text: streamMap.size.toString()
      });
      chrome.action.setBadgeBackgroundColor({
        tabId: details.tabId,
        color: "#38BDF8"
      });
    }
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

// Clear tab stream cache when tab reloads or closes
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading") {
    tabStreams.delete(tabId);
    chrome.action.setBadgeText({ tabId, text: "" });
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  tabStreams.delete(tabId);
});

// Intercept browser regular downloads
chrome.downloads.onCreated.addListener(async (downloadItem) => {
  if (!interceptEnabled) return;

  const url = downloadItem.url || downloadItem.finalUrl;
  if (!url || url.startsWith("blob:") || url.startsWith("data:") || url.startsWith("chrome-extension:")) {
    return;
  }

  try {
    const statusResp = await fetch(`${ENGINE_API}/status`, { signal: AbortSignal.timeout(1000) });
    if (!statusResp.ok) return;
  } catch (err) {
    return;
  }

  chrome.downloads.cancel(downloadItem.id, () => {
    chrome.downloads.erase({ id: downloadItem.id });
  });

  sendToEngine(url, downloadItem.filename);
});

// Message hub
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "GET_TAB_STREAMS") {
    const tabId = sender.tab ? sender.tab.id : message.tabId;
    const streams = tabId && tabStreams.has(tabId) ? Array.from(tabStreams.get(tabId).values()) : [];
    sendResponse({ streams });
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

  if (message.type === "DOWNLOAD_STREAM") {
    fetch(`${ENGINE_API}/media/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.payload)
    })
      .then(res => res.json())
      .then(data => {
        chrome.notifications.create({
          type: "basic",
          iconUrl: "../icons/icon48.png",
          title: "Veloce Media Capture",
          message: `Accelerating ${message.payload.extract_audio ? 'Audio (.mp3)' : 'Lightweight Video'}: ${message.payload.title}`
        });
        sendResponse(data);
      })
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.type === "DOWNLOAD_URL") {
    sendToEngine(message.url, message.filename, message.headers)
      .then((res) => sendResponse({ success: true, res }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }
});

async function sendToEngine(url, suggestedFilename = "", headers = {}) {
  try {
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
    const result = await resp.json();
    if (result.success) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "../icons/icon48.png",
        title: "Veloce Multi-Stream Download",
        message: `Accelerating with 16 dynamic threads: ${suggestedFilename || url.substring(0, 45)}`
      });
    }
    return result;
  } catch (err) {
    console.error("Veloce Bridge Error:", err);
    throw err;
  }
}
