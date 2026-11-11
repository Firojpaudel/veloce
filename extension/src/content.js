/* global chrome */
/**
 * VELOCE CONTENT SCRIPT
 * - Clean media player docking (only on primary active players).
 * - Avoids preview cards, thumbnail hovers, and feed clutter.
 * - Single floating button that only appears on player hover.
 */

(function () {
  const BADGE_CLASS = "veloce-floating-badge";

  function isYouTube() {
    return window.location.hostname.includes("youtube.com");
  }

  function shouldHookElement(video) {
    if (!video) return false;

    // Filter out miniature video preview elements (e.g. YouTube feed cards, hover previews)
    const rect = video.getBoundingClientRect();
    if (rect.width < 360 || rect.height < 200) {
      return false;
    }

    if (isYouTube()) {
      // On YouTube, only hook the primary player on watch/embed pages
      const isWatchPage = window.location.pathname.startsWith("/watch") || window.location.pathname.startsWith("/embed");
      if (!isWatchPage) return false;

      const player = video.closest("#movie_player, .html5-video-player");
      return !!player;
    }

    return true;
  }

  function attachDownloadBadge(video) {
    if (video.dataset.veloceHooked) return;
    if (!shouldHookElement(video)) return;

    // Identify parent container
    const container = video.parentElement;
    if (!container) return;

    // Prevent duplicate badges on same container
    if (container.querySelector(`.${BADGE_CLASS}`)) return;

    video.dataset.veloceHooked = "true";
    container.classList.add("veloce-player-container");

    // Ensure container has relative/absolute positioning
    const style = window.getComputedStyle(container);
    if (style.position === "static") {
      container.style.position = "relative";
    }

    const badge = document.createElement("button");
    badge.className = BADGE_CLASS;
    badge.title = "Download with Veloce";
    badge.innerHTML = `
      <svg class="veloce-badge-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="7 10 12 15 17 10"></polyline>
        <line x1="12" y1="15" x2="12" y2="3"></line>
      </svg>
      <span>Download</span>
    `;

    container.appendChild(badge);

    badge.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();

      let mediaUrl = video.currentSrc || video.src;
      if (!mediaUrl) {
        const srcEl = video.querySelector("source");
        if (srcEl) mediaUrl = srcEl.src;
      }

      // If blob on YouTube or streaming site, use full page URL
      if (!mediaUrl || mediaUrl.startsWith("blob:")) {
        mediaUrl = window.location.href;
      }

      const cleanTitle = (document.title || "video").replace(/[^a-zA-Z0-9_\-\.]/g, "_");
      openQualityModal(mediaUrl, cleanTitle);
    });
  }

  function openQualityModal(mediaUrl, pageTitle) {
    const existing = document.querySelector(".veloce-modal-backdrop");
    if (existing) existing.remove();

    const backdrop = document.createElement("div");
    backdrop.className = "veloce-modal-backdrop";
    backdrop.innerHTML = `
      <div class="veloce-modal-dialog">
        <div class="veloce-dialog-header">
          <div class="veloce-dialog-title-group">
            <svg class="veloce-badge-icon" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2.5">
              <polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polyline>
            </svg>
            <span class="veloce-dialog-title">${pageTitle}</span>
          </div>
          <button class="veloce-close-btn" id="veloce-close-modal">&times;</button>
        </div>

        <div class="veloce-tabs">
          <div class="veloce-tab active" id="veloce-tab-video">Video Formats</div>
          <div class="veloce-tab" id="veloce-tab-audio">Audio Only (MP3)</div>
        </div>

        <div class="veloce-formats-list" id="veloce-formats-container">
          <div class="veloce-format-row">
            <div class="veloce-format-left">
              <span class="veloce-res-badge">720p HD</span>
              <div class="veloce-format-details">
                <span class="veloce-format-name">Lightweight HD (Balanced)</span>
                <span class="veloce-format-sub">Fast stream download</span>
              </div>
            </div>
            <button class="veloce-dl-pill" id="btn-dl-720">Download</button>
          </div>

          <div class="veloce-format-row">
            <div class="veloce-format-left">
              <span class="veloce-res-badge">1080p</span>
              <div class="veloce-format-details">
                <span class="veloce-format-name">Full High Definition</span>
                <span class="veloce-format-sub">Highest visual fidelity</span>
              </div>
            </div>
            <button class="veloce-dl-pill" id="btn-dl-1080">Download</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);

    const closeBtn = backdrop.querySelector("#veloce-close-modal");
    closeBtn.addEventListener("click", () => backdrop.remove());
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.remove();
    });

    const tabVideo = backdrop.querySelector("#veloce-tab-video");
    const tabAudio = backdrop.querySelector("#veloce-tab-audio");
    const container = backdrop.querySelector("#veloce-formats-container");

    function renderVideo() {
      tabVideo.className = "veloce-tab active";
      tabAudio.className = "veloce-tab";
      container.innerHTML = `
        <div class="veloce-format-row">
          <div class="veloce-format-left">
            <span class="veloce-res-badge">720p HD</span>
            <div class="veloce-format-details">
              <span class="veloce-format-name">Lightweight HD (Balanced)</span>
              <span class="veloce-format-sub">Recommended format</span>
            </div>
          </div>
          <button class="veloce-dl-pill" id="btn-dl-720">Download</button>
        </div>
        <div class="veloce-format-row">
          <div class="veloce-format-left">
            <span class="veloce-res-badge">1080p</span>
            <div class="veloce-format-details">
              <span class="veloce-format-name">Full High Definition</span>
              <span class="veloce-format-sub">Best resolution</span>
            </div>
          </div>
          <button class="veloce-dl-pill" id="btn-dl-1080">Download</button>
        </div>
      `;

      container.querySelector("#btn-dl-720").addEventListener("click", () => {
        executeDownload(mediaUrl, "720p", false);
      });
      container.querySelector("#btn-dl-1080").addEventListener("click", () => {
        executeDownload(mediaUrl, "1080p", false);
      });
    }

    function renderAudio() {
      tabAudio.className = "veloce-tab active";
      tabVideo.className = "veloce-tab";
      container.innerHTML = `
        <div class="veloce-format-row">
          <div class="veloce-format-left">
            <span class="veloce-res-badge">MP3</span>
            <div class="veloce-format-details">
              <span class="veloce-format-name">Extracted Audio Track</span>
              <span class="veloce-format-sub">Universal audio file</span>
            </div>
          </div>
          <button class="veloce-dl-pill" id="btn-dl-mp3">Extract MP3</button>
        </div>
      `;

      container.querySelector("#btn-dl-mp3").addEventListener("click", () => {
        executeDownload(mediaUrl, "bestaudio", true, "mp3");
      });
    }

    tabVideo.addEventListener("click", renderVideo);
    tabAudio.addEventListener("click", renderAudio);

    container.querySelector("#btn-dl-720").addEventListener("click", () => {
      executeDownload(mediaUrl, "720p", false);
    });
    container.querySelector("#btn-dl-1080").addEventListener("click", () => {
      executeDownload(mediaUrl, "1080p", false);
    });

    function executeDownload(url, format, extractAudio = false, audioFmt = "mp3") {
      backdrop.remove();
      chrome.runtime.sendMessage({
        type: "DOWNLOAD_STREAM",
        payload: {
          url: url,
          title: pageTitle,
          format_id: format,
          extract_audio: extractAudio,
          audio_format: audioFmt
        }
      }, (resp) => {
        if (resp && resp.reason === "ENGINE_REQUIRED") {
          alert("Veloce Engine Offline:\n\nStreaming media extraction requires the Veloce engine running in the background.\n\nTo start the engine:\n• Windows: Double-click 'veloce-windows-x64.exe'\n• macOS / Linux: Run './veloce' (or 'python3 main.py daemon')\n\nOnce running, click Download again!");
        }
      });
    }

    // Try probing formats from engine if online
    chrome.runtime.sendMessage({ type: "PROBE_MEDIA", url: mediaUrl }, (resp) => {
      if (resp && resp.result && resp.result.video_formats && resp.result.video_formats.length > 0) {
        container.innerHTML = resp.result.video_formats.map(f => `
          <div class="veloce-format-row">
            <div class="veloce-format-left">
              <span class="veloce-res-badge">${f.resolution}</span>
              <div class="veloce-format-details">
                <span class="veloce-format-name">${f.resolution} Video</span>
                <span class="veloce-format-sub">${f.tag || 'Standard stream'}</span>
              </div>
            </div>
            <button class="veloce-dl-pill" data-fmt="${f.format_id}">Download</button>
          </div>
        `).join("");

        container.querySelectorAll(".veloce-dl-pill").forEach(btn => {
          btn.addEventListener("click", () => {
            executeDownload(mediaUrl, btn.dataset.fmt, false);
          });
        });
      }
    });
  }

  function scanDOM() {
    const videos = document.querySelectorAll("video");
    videos.forEach(attachDownloadBadge);
  }

  // Observe navigation and dynamic player loads
  const observer = new MutationObserver(() => scanDOM());
  observer.observe(document.body, { childList: true, subtree: true });

  scanDOM();
})();
