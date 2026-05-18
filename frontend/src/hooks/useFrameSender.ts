/* ============================================================
 * PhysioAI Pro V2 — useFrameSender
 * ============================================================
 * Captures frames from a <video> element at a fixed interval,
 * encodes them as JPEG, and hands them to a `sendFrame` callback
 * (typically wired to useSessionSocket).
 *
 * WHY AN INTERVAL AND NOT requestAnimationFrame?
 *   We want predictable bandwidth — locking to a known rate
 *   (default ~12 FPS) is more important than buttery-smooth
 *   capture. The server smooths the result anyway.
 *
 * WHY THE INTERMEDIATE OFFSCREEN CANVAS?
 *   <video>.captureStream + WebRTC would be lighter but isn't
 *   universally supported on mobile browsers. JPEG via canvas
 *   works everywhere and lets us tune quality on the fly.
 * ============================================================ */

import { useEffect, useRef, useState } from "react";

export function useFrameSender(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  active: boolean,
  sendFrame: (blob: Blob) => Promise<void>,
  intervalMs = 80,    // ~12 fps
  quality = 0.55,
) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [clientFps, setClientFps] = useState(0);

  useEffect(() => {
    if (!active) {
      setClientFps(0);
      return;
    }
    if (!canvasRef.current) canvasRef.current = document.createElement("canvas");
    const canvas = canvasRef.current;

    let running = true;
    let count = 0;
    let lastFpsTime = performance.now();

    const loop = () => {
      if (!running) return;

      const video = videoRef.current;
      // Wait for video to have actual frames.
      if (!video || video.readyState < 2) {
        requestAnimationFrame(loop);
        return;
      }

      // Match canvas to the video's intrinsic size.
      if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
      }

      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.drawImage(video, 0, 0);
        canvas.toBlob((blob) => blob && void sendFrame(blob), "image/jpeg", quality);
      }

      count += 1;
      const now = performance.now();
      if (now - lastFpsTime >= 1000) {
        setClientFps(Math.round((count * 1000) / (now - lastFpsTime)));
        count = 0;
        lastFpsTime = now;
      }

      window.setTimeout(() => requestAnimationFrame(loop), intervalMs);
    };

    requestAnimationFrame(loop);
    return () => { running = false; };
  }, [active, sendFrame, videoRef, intervalMs, quality]);

  return { clientFps };
}
