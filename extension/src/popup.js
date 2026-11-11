/**
 * VELOCE - POPUP CONTROLLER (CLEAN LIGHT DESIGN)
 */

const ENGINE_API = "http://127.0.0.1:9229/api";

const statusDot = document.querySelector(".status-dot");
const statusText = document.querySelector(".status-text");
const engineHint = document.getElementById("engine-mode-hint");
const interceptToggle = document.getElementById("intercept-toggle");
const urlInput = document.getElementById("url-input");
const btnPaste = document.getElementById("btn-paste");
const btnAdd = document.getElementById("btn-add");
const btnRefresh = document.getElementById("btn-refresh");
const btnClearDone = document.getElementById("btn-clear-done");
const tasksList = document.getElementById("tasks-list");
const speedMeter = document.getElementById("speed-meter");

let engineOnline = false;

// Intercept toggle state
chrome.storage.local.get(["interceptEnabled"], (res) => {
  if (res.interceptEnabled !== undefined) {
    interceptToggle.checked = res.interceptEnabled;
  }
});

interceptToggle.addEventListener("change", () => {
  chrome.storage.local.set({ interceptEnabled: interceptToggle.checked });
});

btnPaste.addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text && (text.startsWith("http://") || text.startsWith("https://"))) {
      urlInput.value = text.trim();
      urlInput.focus();
    }
  } catch (err) {
    // Clipboard permission not granted
  }
});

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

async function checkEngineStatus() {
  try {
    const res = await fetch(`${ENGINE_API}/status`, { signal: AbortSignal.timeout(1000) });
    if (res.ok) {
      engineOnline = true;
      statusDot.className = "status-dot";
      statusText.textContent = "Engine Connected";
      engineHint.textContent = "16x Dynamic Segmentation Active";
      return true;
    }
  } catch (err) {
    engineOnline = false;
    statusDot.className = "status-dot offline";
    statusText.textContent = "Standby (Direct Mode)";
    engineHint.textContent = "Standard Direct Download Active";
  }
  return false;
}

async function fetchTasks() {
  await checkEngineStatus();

  if (!engineOnline) {
    // Check Chrome native downloads
    chrome.downloads.search({ limit: 5, orderBy: ["-startTime"] }, (items) => {
      renderChromeDownloads(items || []);
    });
    return;
  }

  try {
    const res = await fetch(`${ENGINE_API}/tasks`);
    const data = await res.json();
    renderEngineTasks(data.tasks || []);
  } catch (err) {
    chrome.downloads.search({ limit: 5, orderBy: ["-startTime"] }, (items) => {
      renderChromeDownloads(items || []);
    });
  }
}

function renderEngineTasks(tasks) {
  if (tasks.length === 0) {
    showEmpty();
    speedMeter.textContent = "Throughput: 0.0 MB/s";
    return;
  }

  let totalSpeed = 0;
  tasksList.innerHTML = "";

  tasks.forEach((task) => {
    if (task.status === "DOWNLOADING") {
      totalSpeed += task.speed || 0;
    }

    const item = document.createElement("div");
    item.className = "task-item";
    const isDone = task.status === "COMPLETED";

    item.innerHTML = `
      <div class="task-top">
        <span class="task-title" title="${task.filename}">${task.filename}</span>
        <span class="task-rate">${isDone ? "Done" : `${formatBytes(task.speed || 0)}/s`}</span>
      </div>
      <div class="progress-track">
        <div class="progress-bar" style="width: ${task.percent || 0}%;"></div>
      </div>
      <div class="task-bottom">
        <span>${formatBytes(task.downloaded || 0)} / ${formatBytes(task.total_size || 0)} (${task.percent || 0}%)</span>
        <div class="task-ctrls">
          ${!isDone ? `<button class="btn-ctrl" onclick="window.pauseTask('${task.id}')">Pause</button>` : ""}
          <button class="btn-ctrl danger" onclick="window.cancelTask('${task.id}')">Remove</button>
        </div>
      </div>
    `;
    tasksList.appendChild(item);
  });

  speedMeter.textContent = `Throughput: ${formatBytes(totalSpeed)}/s`;
}

function renderChromeDownloads(items) {
  const activeItems = items.filter(i => i.state === "in_progress" || i.state === "complete");
  if (activeItems.length === 0) {
    showEmpty();
    speedMeter.textContent = "Throughput: 0.0 MB/s";
    return;
  }

  tasksList.innerHTML = "";
  let totalBytesSec = 0;

  activeItems.forEach(item => {
    const filename = item.filename ? item.filename.split("/").pop().split("\\").pop() : "download";
    const percent = item.totalBytes > 0 ? Math.round((item.bytesReceived / item.totalBytes) * 100) : 0;
    const isDone = item.state === "complete";
    if (item.estimatedEndTime && !isDone) totalBytesSec += item.bytesReceived;

    const div = document.createElement("div");
    div.className = "task-item";
    div.innerHTML = `
      <div class="task-top">
        <span class="task-title" title="${filename}">${filename}</span>
        <span class="task-rate">${isDone ? "Completed" : `${percent}%`}</span>
      </div>
      <div class="progress-track">
        <div class="progress-bar" style="width: ${isDone ? 100 : percent}%;"></div>
      </div>
      <div class="task-bottom">
        <span>${formatBytes(item.bytesReceived)} ${item.totalBytes > 0 ? `/ ${formatBytes(item.totalBytes)}` : ""}</span>
        <span style="text-transform: capitalize;">${item.state.replace("_", " ")}</span>
      </div>
    `;
    tasksList.appendChild(div);
  });

  speedMeter.textContent = `Active Transfers: ${activeItems.filter(i => i.state === "in_progress").length}`;
}

function showEmpty() {
  tasksList.innerHTML = `
    <div class="empty-state">
      <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="7 10 12 15 17 10"></polyline>
        <line x1="12" y1="15" x2="12" y2="3"></line>
      </svg>
      <div class="empty-title">No Active Transfers</div>
      <div class="empty-sub">Downloads will appear here</div>
    </div>
  `;
}

window.pauseTask = async function(id) {
  try {
    await fetch(`${ENGINE_API}/tasks/${id}/pause`, { method: "POST" });
    fetchTasks();
  } catch (e) {}
};

window.cancelTask = async function(id) {
  try {
    await fetch(`${ENGINE_API}/tasks/${id}/cancel`, { method: "POST" });
    fetchTasks();
  } catch (e) {}
};

btnAdd.addEventListener("click", () => {
  const url = urlInput.value.trim();
  if (!url) return;

  chrome.runtime.sendMessage({
    type: "DOWNLOAD_URL",
    url: url
  }, () => {
    urlInput.value = "";
    fetchTasks();
  });
});

urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") btnAdd.click();
});

btnClearDone.addEventListener("click", async () => {
  if (engineOnline) {
    try {
      const res = await fetch(`${ENGINE_API}/tasks`);
      const data = await res.json();
      for (const t of (data.tasks || [])) {
        if (t.status === "COMPLETED") {
          await fetch(`${ENGINE_API}/tasks/${t.id}/cancel`, { method: "POST" });
        }
      }
    } catch (e) {}
  }
  chrome.downloads.erase({ state: "complete" });
  fetchTasks();
});

btnRefresh.addEventListener("click", fetchTasks);

fetchTasks();
setInterval(fetchTasks, 2000);
