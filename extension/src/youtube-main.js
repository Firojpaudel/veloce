/**
 * Runs in YouTube's own page context (manifest "world": "MAIN") because the player data lives there.
 * When Veloce's content script asks, it answers with the current video's details and available
 * qualities, so the picker can open instantly instead of waiting for a network lookup.
 * It only reads data; downloads still go through the Veloce app (yt-dlp).
 */
(() => {
  const read = () => {
    const players = [document.getElementById("movie_player"), document.getElementById("shorts-player"),
      document.querySelector("ytd-reel-video-renderer[is-active] #shorts-player")];
    for (const p of players) {
      try {
        const r = p && typeof p.getPlayerResponse === "function" ? p.getPlayerResponse() : null;
        if (r && r.videoDetails) return r;
      } catch { /* not ready */ }
    }
    return null;
  };

  window.addEventListener("message", (e) => {
    if (e.source !== window || !e.data || e.data.type !== "veloce:get-player") return;
    const r = read();
    const vd = r && r.videoDetails;
    const data = vd ? {
      videoId: vd.videoId,
      title: vd.title,
      author: vd.author,
      lengthSeconds: Number(vd.lengthSeconds) || 0,
      isLive: !!vd.isLiveContent && !!(r.streamingData && r.streamingData.hlsManifestUrl),
      thumbnail: (vd.thumbnail && vd.thumbnail.thumbnails || []).slice(-1)[0]?.url || "",
      formats: ((r.streamingData && r.streamingData.adaptiveFormats) || []).map((f) => ({
        mimeType: f.mimeType || "", height: f.height || 0, fps: f.fps || 0,
        contentLength: Number(f.contentLength) || 0, bitrate: f.averageBitrate || f.bitrate || 0,
      })),
    } : null;
    window.postMessage({ type: "veloce:player", id: e.data.id, data }, "*");
  });
})();
