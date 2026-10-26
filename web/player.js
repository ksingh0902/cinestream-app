// web/player.js
// One player, two strategies. The site never checks "which source".
export async function mountPlayer(host, movieId) {
  if (typeof host === "string") {
    host = document.getElementById(host) || document.querySelector(host);
  }
  if (!host) return;

  host.innerHTML = "";
  const loading = document.createElement("div");
  loading.className = "player-loading";
  loading.textContent = "Loading stream...";
  loading.style.cssText = "display:flex;align-items:center;justify-content:center;height:100%;min-height:360px;background:#05070f;color:#e2e8f0;font-size:16px;";
  host.appendChild(loading);

  try {
    const res = await fetch(`/api/stream/${movieId}`);
    if (!res.ok) {
      host.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;min-height:360px;background:#05070f;color:#ef4444;">Stream unavailable. Please try again later.</div>';
      return;
    }
    const info = await res.json();
    host.innerHTML = "";

    if (info.kind === "hls" || info.kind === "video") {
      return mountHls(host, movieId, info);
    }
    return mountIframe(host, movieId, info);
  } catch (err) {
    host.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;min-height:360px;background:#05070f;color:#ef4444;">Error loading stream: ${err.message}</div>`;
  }
}

/* ---- source A strategy: hls.js + same-origin proxy + self-heal ---- */
async function mountHls(host, movieId, info) {
  const container = document.createElement("div");
  container.style.cssText = "position:relative;width:100%;background:#000;aspect-ratio:16/9;";

  const video = document.createElement("video");
  video.controls = true;
  video.playsInline = true;
  video.style.cssText = "width:100%;height:100%;display:block;background:#000;";
  container.appendChild(video);
  host.appendChild(container);

  if (info.kind === "video") {
    video.src = info.url;
    video.play().catch(() => {});
  } else if (window.Hls && window.Hls.isSupported()) {
    const hls = new window.Hls({
      enableWorker: true,
      lowLatencyMode: false,
      xhrSetup: (xhr) => { xhr.withCredentials = true; }
    });
    hls.loadSource(info.url);
    hls.attachMedia(video);

    hls.on(window.Hls.Events.ERROR, async (_e, data) => {
      if (!data.fatal) return;
      const at = video.currentTime;
      try {
        const r = await fetch(`/api/stream/${movieId}?refresh=1`);
        if (!r.ok) return;
        const fresh = await r.json();
        hls.loadSource(fresh.url);
        video.currentTime = at; // resume at same timestamp
        video.play().catch(() => {});
      } catch (_) {}
    });
  } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = info.url;
  }
}

/* ---- source B strategy: sandboxed iframe + server switcher ---- */
function mountIframe(host, movieId, info) {
  const container = document.createElement("div");
  container.style.cssText = "position:relative;width:100%;background:#000;";

  const frame = document.createElement("iframe");
  frame.src = info.url;
  frame.allow = "autoplay; fullscreen; encrypted-media; picture-in-picture";
  frame.allowFullscreen = true;
  frame.referrerPolicy = "origin";
  frame.style.cssText = "width:100%;aspect-ratio:16/9;border:0;background:#000;display:block;";
  container.appendChild(frame);
  host.appendChild(container);

  // graceful recovery: upstream rotated the player → re-resolve once
  let retried = false;
  frame.addEventListener("error", async () => {
    if (retried) return;
    retried = true;
    try {
      const r = await fetch(`/api/stream/${movieId}?refresh=1`);
      if (r.ok) {
        const fresh = await r.json();
        frame.src = fresh.url;
      }
    } catch (_) {}
  });

  if (info.servers && info.servers.length > 1) {
    const bar = document.createElement("div");
    bar.className = "server-bar";
    bar.style.cssText = "display:flex;gap:8px;padding:12px;background:#0c101c;border-top:1px solid #1e293b;overflow-x:auto;";
    info.servers.forEach((s, i) => {
      const b = document.createElement("button");
      b.textContent = s.label || `Server ${i + 1}`;
      b.style.cssText = "padding:6px 14px;background:#1e293b;color:#f8fafc;border:1px solid #334155;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500;transition:all 0.2s;";
      b.onmouseover = () => { b.style.background = "#3b82f6"; b.style.borderColor = "#60a5fa"; };
      b.onmouseout = () => {
        if (frame.src !== s.url) {
          b.style.background = "#1e293b";
          b.style.borderColor = "#334155";
        }
      };
      b.onclick = () => {
        frame.src = s.url;
        Array.from(bar.children).forEach(child => {
          child.style.background = "#1e293b";
          child.style.borderColor = "#334155";
        });
        b.style.background = "#2563eb";
        b.style.borderColor = "#60a5fa";
      };
      bar.appendChild(b);
    });
    host.appendChild(bar);
  }
}

// Global attachment for non-module script tag inclusion if needed
if (typeof window !== "undefined") {
  window.mountPlayer = mountPlayer;
}
