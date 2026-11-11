/**
 * VELOCE ACCELERATOR - POPUP CONTROLLER
 * Engineered for buttery-smooth 60fps rendering, live segment holograms, and rapid interaction.
 */

const ENGINE_API = "http://127.0.0.1:9229/api";

const statusBadge = document.getElementById("engine-status");
const interceptToggle = document.getElementById("intercept-toggle");
const urlInput = document.getElementById("url-input");
const btnPaste = document.getElementById("btn-paste");
const btnAdd = document.getElementById("btn-add");
const btnRefresh = document.getElementById("btn-refresh");
const btnClearDone = document.getElementById("btn-clear-done");
const tasksList = document.getElementById("tasks-list");

const hudSpeed = document.getElementById("hud-speed");
const hudUnit = document.getElementById("hud-unit");
const hudActiveCount = document.getElementById("hud-active-count");

// Load intercept setting
chrome.storage.local.get(["interceptEnabled"], (res) => {
  if (res.interceptEnabled !== undefined) {
    interceptToggle.checked = res.interceptEnabled;
  }
});

interceptToggle.addEventListener("change", () => {
  chrome.storage.local.set({ interceptEnabled: interceptToggle.checked });
});

// Clipboard paste helper
btnPaste.addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text && (text.startsWith("http://") || text.startsWith("https://"))) {
      urlInput.value = text.trim();
      urlInput.focus();
    }
  } catch (err) {
    console.debug("Clipboard read access not granted:", err);
  }
});

function formatSpeed(bytesPerSec) {
  if (!bytesPerSec || bytesPerSec <= 0) return { val: "0.0", unit: "MB/s" };
  if (bytesPerSec < 1024 * 1024) {
    return { val: (bytesPerSec / 1024).toFixed(1), unit: "KB/s" };
  }
  return { val: (bytesPerSec / (1024 * 1024)).toFixed(2), unit: "MB/s" };
}

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function getFileIcon(filename) {
  const ext = (filename || "").split('.').pop().toLowerCase();
  if (["mp4", "mkv", "webm", "avi", "mov", "flv", "m3u8"].includes(ext)) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>`;
  }
  if (["mp3", "wav", "flac", "aac", "ogg", "m4a"].includes(ext)) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>`;
  }
  if (["zip", "rar", "7z", "tar", "gz", "bz2", "xz"].includes(ext)) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"></polyline><rect x="1" y="3" width="22" height="5"></rect><line x1="10" y1="12" x2="14" y2="12"></line></svg>`;
  }
  if (["iso", "dmg", "img", "bin"].includes(ext)) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="3"></circle></svg>`;
  }
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>`;
}

async function checkEngineStatus() {
  try {
    const res = await fetch(`${ENGINE_API}/status`, { signal: AbortSignal.timeout(1200) });
    if (res.ok) {
      statusBadge.className = "engine-badge online";
      statusBadge.querySelector(".status-label").textContent = "Core Engine Active";
      return true;
    }
  } catch (err) {
    statusBadge.className = "engine-badge offline";
    statusBadge.querySelector(".status-label").textContent = "Engine Offline";
  }
  return false;
}

async function fetchTasks() {
  const isOnline = await checkEngineStatus();
  if (!isOnline) {
    hudSpeed.textContent = "0.0";
    hudUnit.textContent = "MB/s";
    hudActiveCount.textContent = "0";
    tasksList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon-wrap" style="color: #f43f5e;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        </div>
        <div class="empty-text">Veloce Engine Not Detected</div>
        <div class="empty-sub" style="font-family: monospace; margin-top: 6px; color: #94a3b8;">python3 main.py daemon</div>
      </div>
    `;
    return;
  }

  try {
    const res = await fetch(`${ENGINE_API}/tasks`);
    const data = await res.json();
    renderTasks(data.tasks || []);
  } catch (err) {
    console.debug("Error updating tasks:", err);
  }
}

function renderTasks(tasks) {
  let totalBandwidth = 0;
  let activeCount = 0;

  if (tasks.length === 0) {
    hudSpeed.textContent = "0.0";
    hudUnit.textContent = "MB/s";
    hudActiveCount.textContent = "0";
    tasksList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
        </div>
        <div class="empty-text">No active transfers</div>
        <div class="empty-sub">Links and video streams will automatically appear here</div>
      </div>
    `;
    return;
  }

  tasksList.innerHTML = "";

  tasks.forEach((task) => {
    if (task.status === "DOWNLOADING") {
      totalBandwidth += task.speed || 0;
      activeCount++;
    }

    const card = document.createElement("div");
    card.className = "task-card";

    // Build segments spectrum bar (Dynamic segment hologram)
    let segmentsHtml = "";
    if (task.segments && task.segments.length > 0) {
      segmentsHtml = `<div class="segment-spectrum" title="Dynamic Multi-Stream Spectrum">` +
        task.segments.map(s => {
          const cls = s.completed ? "completed" : (s.active ? "active" : "");
          return `<div class="segment-slice ${cls}"></div>`;
        }).join("") +
        `</div>`;
    }

    const iconSvg = getFileIcon(task.filename);
    const speedInfo = formatSpeed(task.speed);
    const isDone = task.status === "COMPLETED";

    card.innerHTML = `
      <div class="card-top">
        <div class="file-info">
          <div class="file-type-icon">${iconSvg}</div>
          <span class="file-name" title="${task.filename}">${task.filename}</span>
        </div>
        <span class="card-speed-badge">${isDone ? "COMPLETE" : `${speedInfo.val} ${speedInfo.unit}`}</span>
      </div>

      <div class="progress-track">
        <div class="progress-fill" style="width: ${task.percent || 0}%;"></div>
      </div>

      ${segmentsHtml}

      <div class="card-meta">
        <span class="meta-stats">${formatBytes(task.downloaded || 0)} / ${formatBytes(task.total_size || 0)}</span>
        <span class="meta-status ${isDone ? 'completed' : ''}">${task.status} (${task.percent || 0}%)</span>
      </div>

      <div class="card-actions">
        ${!isDone ? `<button class="action-pill" onclick="window.velocePause('${task.id}')">Pause</button>` : ''}
        <button class="action-pill danger" onclick="window.veloceCancel('${task.id}')">Remove</button>
      </div>
    `;

    tasksList.appendChild(card);
  });

  const globalSpeed = formatSpeed(totalBandwidth);
  hudSpeed.textContent = globalSpeed.val;
  hudUnit.textContent = globalSpeed.unit;
  hudActiveCount.textContent = activeCount.toString();
}

window.velocePause = async function(id) {
  try {
    await fetch(`${ENGINE_API}/tasks/${id}/pause`, { method: "POST" });
    fetchTasks();
  } catch (e) {
    console.error(e);
  }
};

window.veloceCancel = async function(id) {
  try {
    await fetch(`${ENGINE_API}/tasks/${id}/cancel`, { method: "POST" });
    fetchTasks();
  } catch (e) {
    console.error(e);
  }
};

btnClearDone.addEventListener("click", async () => {
  try {
    const res = await fetch(`${ENGINE_API}/tasks`);
    const data = await res.json();
    for (const t of (data.tasks || [])) {
      if (t.status === "COMPLETED") {
        await fetch(`${ENGINE_API}/tasks/${t.id}/cancel`, { method: "POST" });
      }
    }
    fetchTasks();
  } catch (e) {
    console.error(e);
  }
});

btnAdd.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) return;

  chrome.runtime.sendMessage({
    type: "DOWNLOAD_URL",
    url: url
  }, (resp) => {
    urlInput.value = "";
    fetchTasks();
  });
});

urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    btnAdd.click();
  }
});

btnRefresh.addEventListener("click", fetchTasks);

// Initial query and live 1.2s poll
fetchTasks();
setInterval(fetchTasks, 1200);
