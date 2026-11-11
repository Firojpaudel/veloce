/**
 * VELOCE CONTENT SCRIPT - STREAM & MEDIA SNIFFER WITH QUALITY SELECTOR
 * Detects HTML5 video, HLS, DASH, and MSE streams and presents
 * a veteran quality & audio extraction selection dialog.
 */

(function () {
  const VELOCE_CLASS = "veloce-floating-panel";

  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return "Lightweight / Dynamic";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function openQualityModal(mediaUrl, pageTitle) {
    // Remove any existing modal
    const existing = document.querySelector(".veloce-modal-backdrop");
    if (existing) existing.remove();

    const backdrop = document.createElement("div");
    backdrop.className = "veloce-modal-backdrop";
    backdrop.innerHTML = `
      <div class="veloce-modal-dialog">
        <div class="veloce-dialog-header">
          <div class="veloce-dialog-title-box">
            <svg class="veloce-sniff-icon" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2.2">
              <path d="M13 2L3 14H12L11 22L21 10H12L13 2Z"/>
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
          <div style="padding: 24px; text-align: center; color: #94a3b8; font-size: 12px;">
            Analyzing stream resolutions and audio bitrates...
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

    let videoFormats = [];
    let audioFormats = [];

    function renderVideo() {
      tabVideo.className = "veloce-tab active";
      tabAudio.className = "veloce-tab";

      if (videoFormats.length === 0) {
        container.innerHTML = `
          <div class="veloce-format-row">
            <div class="veloce-format-left">
              <span class="veloce-res-badge lightweight">720p HD</span>
              <div class="veloce-format-details">
                <span class="veloce-format-name">Lightweight HD (Balanced)</span>
                <span class="veloce-format-sub">Fast stream download</span>
              </div>
            </div>
            <button class="veloce-dl-pill" id="btn-dl-default">Download MP4</button>
          </div>
        `;
        container.querySelector("#btn-dl-default").addEventListener("click", () => {
          startDownload(mediaUrl, "720p", false);
        });
        return;
      }

      container.innerHTML = videoFormats.map((f, idx) => `
        <div class="veloce-format-row">
          <div class="veloce-format-left">
            <span class="veloce-res-badge ${f.is_lightweight ? 'lightweight' : ''}">${f.resolution}</span>
            <div class="veloce-format-details">
              <span class="veloce-format-name">${f.tag || f.resolution} (${f.ext ? f.ext.toUpperCase() : 'MP4'})</span>
              <span class="veloce-format-sub">Est. Size: ${formatBytes(f.filesize)}</span>
            </div>
          </div>
          <button class="veloce-dl-pill" data-idx="${idx}">Download</button>
        </div>
      `).join("");

      container.querySelectorAll(".veloce-dl-pill").forEach(btn => {
        btn.addEventListener("click", () => {
          const idx = parseInt(btn.dataset.idx);
          const fmt = videoFormats[idx];
          startDownload(mediaUrl, fmt.format_id || fmt.resolution, false);
        });
      });
    }

    function renderAudio() {
      tabAudio.className = "veloce-tab active";
      tabVideo.className = "veloce-tab";

      container.innerHTML = `
        <div class="veloce-format-row">
          <div class="veloce-format-left">
            <span class="veloce-res-badge lightweight">MP3</span>
            <div class="veloce-format-details">
              <span class="veloce-format-name">High Quality Audio (192 kbps)</span>
              <span class="veloce-format-sub">Lightweight audio extraction</span>
            </div>
          </div>
          <button class="veloce-dl-pill" id="btn-dl-mp3">Extract MP3</button>
        </div>
        <div class="veloce-format-row">
          <div class="veloce-format-left">
            <span class="veloce-res-badge">M4A</span>
            <div class="veloce-format-details">
              <span class="veloce-format-name">Lossless AAC Stream</span>
              <span class="veloce-format-sub">Fast native container</span>
            </div>
          </div>
          <button class="veloce-dl-pill" id="btn-dl-m4a">Download M4A</button>
        </div>
      `;

      container.querySelector("#btn-dl-mp3").addEventListener("click", () => {
        startDownload(mediaUrl, "bestaudio", true, "mp3");
      });
      container.querySelector("#btn-dl-m4a").addEventListener("click", () => {
        startDownload(mediaUrl, "bestaudio", true, "m4a");
      });
    }

    tabVideo.addEventListener("click", renderVideo);
    tabAudio.addEventListener("click", renderAudio);

    function startDownload(targetUrl, formatId, extractAudio = false, audioFmt = "mp3") {
      backdrop.remove();
      chrome.runtime.sendMessage({
        type: "DOWNLOAD_STREAM",
        payload: {
          url: targetUrl,
          title: pageTitle.replace(/[^a-zA-Z0-9_\-\.]/g, "_"),
          format_id: formatId,
          extract_audio: extractAudio,
          audio_format: audioFmt
        }
      });
    }

    // Probe the media using Veloce Engine
    chrome.runtime.sendMessage({
      type: "PROBE_MEDIA",
      url: mediaUrl
    }, (resp) => {
      if (resp && resp.result) {
        videoFormats = resp.result.video_formats || [];
        audioFormats = resp.result.audio_formats || [];
      }
      renderVideo();
    });
  }

  function createFloatingButton(mediaElement) {
    if (mediaElement.dataset.veloceHooked) return;
    mediaElement.dataset.veloceHooked = "true";

    const container = document.createElement("div");
    container.className = VELOCE_CLASS;
    container.innerHTML = `
      <div class="veloce-sniff-btn">
        <svg class="veloce-sniff-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <path d="M13 2L3 14H12L11 22L21 10H12L13 2Z"/>
        </svg>
        <span>Download Media</span>
        <span class="veloce-badge">VELOCE</span>
      </div>
    `;

    function updatePosition() {
      const rect = mediaElement.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0 || window.getComputedStyle(mediaElement).display === "none") {
        container.style.display = "none";
        return;
      }
      container.style.display = "flex";
      container.style.top = `${Math.max(10, window.scrollY + rect.top + 12)}px`;
      container.style.left = `${Math.max(10, window.scrollX + rect.right - 185)}px`;
    }

    document.body.appendChild(container);

    mediaElement.addEventListener("play", updatePosition);
    mediaElement.addEventListener("loadedmetadata", updatePosition);
    mediaElement.addEventListener("mouseenter", updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition);

    container.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();

      let mediaUrl = mediaElement.currentSrc || mediaElement.src;
      if (!mediaUrl) {
        const source = mediaElement.querySelector("source");
        if (source) mediaUrl = source.src;
      }

      // If still empty or blob, check if the page URL itself can be probed by yt-dlp
      if (!mediaUrl || mediaUrl.startsWith("blob:")) {
        mediaUrl = window.location.href;
      }

      const pageTitle = document.title || "Video";
      openQualityModal(mediaUrl, pageTitle);
    });

    updatePosition();
  }

  function scanMedia() {
    const mediaElements = document.querySelectorAll("video, audio");
    mediaElements.forEach(createFloatingButton);
  }

  const observer = new MutationObserver(() => scanMedia());
  observer.observe(document.body, { childList: true, subtree: true });

  scanMedia();
})();
