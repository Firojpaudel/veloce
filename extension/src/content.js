/**
 * VELOCE CONTENT SCRIPT - STREAM & MEDIA SNIFFER
 * Scans DOM for video/audio streams and injects the sleek floating Veloce overlay.
 */

(function () {
  const VELOCE_CLASS = "veloce-floating-panel";

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

      if (!mediaUrl) {
        alert("Veloce: Could not identify direct stream URL for this media.");
        return;
      }

      const cleanTitle = (document.title || "video").replace(/[^a-zA-Z0-9_\-\.]/g, "_");

      chrome.runtime.sendMessage({
        type: "DOWNLOAD_URL",
        url: mediaUrl,
        filename: `${cleanTitle}.mp4`
      }, (resp) => {
        if (resp && resp.success) {
          const btn = container.querySelector(".veloce-sniff-btn");
          btn.innerHTML = `
            <svg class="veloce-sniff-icon" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            <span style="color: #6ee7b7;">Accelerating in Veloce!</span>
          `;
          setTimeout(() => {
            btn.innerHTML = `
              <svg class="veloce-sniff-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <path d="M13 2L3 14H12L11 22L21 10H12L13 2Z"/>
              </svg>
              <span>Download Media</span>
              <span class="veloce-badge">VELOCE</span>
            `;
          }, 3500);
        }
      });
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
