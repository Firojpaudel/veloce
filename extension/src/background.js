/**
 * VELOCE BACKGROUND SERVICE WORKER (Manifest V3)
 * Automatic download interception, request header extraction, and Core Engine bridge.
 */

const ENGINE_API = "http://127.0.0.1:9229/api";
let interceptEnabled = true;

// Load settings
chrome.storage.local.get(["interceptEnabled"], (res) => {
  if (res.interceptEnabled !== undefined) {
    interceptEnabled = res.interceptEnabled;
  }
});

// Settings watcher
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.interceptEnabled) {
    interceptEnabled = changes.interceptEnabled.newValue;
  }
});

// Intercept browser downloads
chrome.downloads.onCreated.addListener(async (downloadItem) => {
  if (!interceptEnabled) return;

  const url = downloadItem.url || downloadItem.finalUrl;
  if (!url || url.startsWith("blob:") || url.startsWith("data:") || url.startsWith("chrome-extension:")) {
    return;
  }

  // Health check to ensure Veloce daemon is active
  try {
    const statusResp = await fetch(`${ENGINE_API}/status`, { signal: AbortSignal.timeout(1000) });
    if (!statusResp.ok) return;
  } catch (err) {
    // Engine not online, let standard browser download handle it seamlessly
    return;
  }

  // Cancel native single-stream browser download
  chrome.downloads.cancel(downloadItem.id, () => {
    chrome.downloads.erase({ id: downloadItem.id });
  });

  // Delegate to Veloce multi-connection engine
  sendToEngine(url, downloadItem.filename);
});

// Message hub
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "DOWNLOAD_URL") {
    sendToEngine(message.url, message.filename, message.headers)
      .then((res) => sendResponse({ success: true, res }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.type === "CHECK_ENGINE") {
    fetch(`${ENGINE_API}/status`, { signal: AbortSignal.timeout(1500) })
      .then((res) => res.json())
      .then((data) => sendResponse({ online: true, data }))
      .catch((err) => sendResponse({ online: false, error: err.message }));
    return true;
  }
});

async function sendToEngine(url, suggestedFilename = "", headers = {}) {
  try {
    const payload = {
      url: url,
      connections: 16,
      headers: {
        "User-Agent": navigator.userAgent,
        ...headers
      }
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
