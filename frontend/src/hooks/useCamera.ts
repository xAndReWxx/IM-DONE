/* ============================================================
 * PhysioAI Pro V2 — useCamera (Production-Grade)
 * ============================================================
 * Opens the user-facing camera, wires its MediaStream to a
 * <video> element, and gives the caller `start`/`stop` controls.
 *
 * SECURITY & COMPATIBILITY
 *   Browsers block navigator.mediaDevices on insecure origins
 *   (plain HTTP non-localhost). This hook:
 *     1. Checks navigator.mediaDevices exists before calling
 *     2. Checks getUserMedia exists (old browsers lack it)
 *     3. Detects insecure-origin as the root cause and shows
 *        a clear error instead of crashing
 *     4. Maps every DOMException name to a human-readable msg
 *     5. Supports retry from any error state
 *
 * TABLET / MOBILE SUPPORT
 *   • Uses facingMode: "user" for front camera
 *   • Constrains to 640×480 (works on all mobile browsers)
 *   • Handles permission prompts gracefully
 *   • Works on Chrome Android, iPad Safari, Samsung Internet
 *
 * RACE CONDITION FIX
 *   • Stops any existing stream before starting a new one
 *   • Waits for `canplay` event before calling play()
 *   • Handles AbortError (play interrupted) gracefully
 *   • Guards against concurrent start() calls
 * ============================================================ */

import { useCallback, useRef, useState } from "react";

/** Camera states for UI display. */
export type CameraStatus =
  | "idle"           // Not started yet
  | "requesting"     // Waiting for user permission
  | "starting"       // Permission granted, initializing stream
  | "active"         // Camera is live and streaming
  | "error";         // Something went wrong

/** Detailed error info for the UI. */
export type CameraError = {
  code: string;
  message: string;
  isRecoverable: boolean;
};

// ── Error code → human-readable message ──
const ERROR_MESSAGES: Record<string, CameraError> = {
  insecure_origin: {
    code: "insecure_origin",
    message: "Camera requires a secure connection (HTTPS). Use https:// to access this page.",
    isRecoverable: false,
  },
  not_supported: {
    code: "not_supported",
    message: "Your browser does not support camera access. Use Chrome, Safari, or Edge.",
    isRecoverable: false,
  },
  permission_denied: {
    code: "permission_denied",
    message: "Camera permission was denied. Allow camera access in your browser settings.",
    isRecoverable: true,
  },
  not_found: {
    code: "not_found",
    message: "No camera found on this device.",
    isRecoverable: false,
  },
  not_readable: {
    code: "not_readable",
    message: "Camera is in use by another application. Close other apps and retry.",
    isRecoverable: true,
  },
  overconstrained: {
    code: "overconstrained",
    message: "Camera does not support the requested resolution. Retrying with defaults...",
    isRecoverable: true,
  },
  abort: {
    code: "abort",
    message: "Camera initialization was interrupted. Please retry.",
    isRecoverable: true,
  },
  unknown: {
    code: "unknown",
    message: "Camera unavailable. Please check permissions and retry.",
    isRecoverable: true,
  },
};


export function useCamera() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [status, setStatus] = useState<CameraStatus>("idle");
  const [error, setError] = useState<CameraError | null>(null);
  // Guards against two simultaneous start() attempts.
  const startingRef = useRef(false);

  /** Check if camera APIs are available (feature detection). */
  const checkCameraSupport = useCallback((): CameraError | null => {
    // Check 1: Is this a secure context?
    // Browsers disable mediaDevices on insecure HTTP (except localhost).
    if (typeof window !== "undefined" && !window.isSecureContext) {
      const isLocalhost =
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1" ||
        window.location.hostname === "[::1]";
      if (!isLocalhost) {
        return ERROR_MESSAGES.insecure_origin;
      }
    }

    // Check 2: Does navigator.mediaDevices exist?
    if (!navigator?.mediaDevices) {
      // Could be insecure origin OR ancient browser.
      if (typeof window !== "undefined" && !window.isSecureContext) {
        return ERROR_MESSAGES.insecure_origin;
      }
      return ERROR_MESSAGES.not_supported;
    }

    // Check 3: Does getUserMedia exist?
    if (typeof navigator.mediaDevices.getUserMedia !== "function") {
      return ERROR_MESSAGES.not_supported;
    }

    return null; // All good.
  }, []);

  /** Request camera permission and start the stream. */
  const start = useCallback(async () => {
    // Prevent concurrent starts.
    if (startingRef.current) return;
    startingRef.current = true;
    setError(null);
    setStatus("requesting");

    const video = videoRef.current;

    // Stop any previously active stream first.
    if (video) {
      const oldStream = video.srcObject as MediaStream | null;
      if (oldStream) {
        oldStream.getTracks().forEach((t) => t.stop());
        video.srcObject = null;
      }
    }

    // ── Feature detection ──
    const supportError = checkCameraSupport();
    if (supportError) {
      setError(supportError);
      setStatus("error");
      startingRef.current = false;
      return;
    }

    try {
      setStatus("requesting");

      // Try preferred constraints first.
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: "user",
            width: { ideal: 640 },
            height: { ideal: 480 },
          },
          audio: false,
        });
      } catch (e) {
        // If OverconstrainedError, retry with minimal constraints.
        if (e instanceof DOMException && e.name === "OverconstrainedError") {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "user" },
            audio: false,
          });
        } else {
          throw e;
        }
      }

      setStatus("starting");

      if (!video) {
        // videoRef not yet attached — tear down the stream.
        stream.getTracks().forEach((t) => t.stop());
        startingRef.current = false;
        setStatus("idle");
        return;
      }

      video.srcObject = stream;

      // Wait until the browser has decoded enough to play.
      await waitUntilCanPlay(video);

      try {
        await video.play();
      } catch (e) {
        // AbortError means play() was interrupted (e.g. srcObject replaced).
        // Benign — the stream is still live.
        if (e instanceof DOMException && e.name === "AbortError") {
          startingRef.current = false;
          return;
        }
        throw e;
      }

      setStatus("active");
      setError(null);
    } catch (e) {
      const cameraError = mapError(e);
      setError(cameraError);
      setStatus("error");
    } finally {
      startingRef.current = false;
    }
  }, [checkCameraSupport]);

  /** Stop the stream and clear the video element. */
  const stop = useCallback(() => {
    const video = videoRef.current;
    const stream = video?.srcObject as MediaStream | null;
    stream?.getTracks().forEach((t) => t.stop());
    if (video) {
      video.pause();
      video.srcObject = null;
    }
    setStatus("idle");
    setError(null);
  }, []);

  // Backward-compatible `active` flag.
  const active = status === "active";
  // Backward-compatible `error` string (for existing UI).
  const errorMessage = error?.message ?? null;

  return {
    videoRef,
    active,
    status,
    error: errorMessage,
    errorDetail: error,
    start,
    stop,
  };
}


/* ── Helpers ── */

/**
 * Resolve when the video element has enough data to start playback.
 * Uses the `canplay` event but falls back immediately if the browser
 * already reports readyState >= 2 (HAVE_CURRENT_DATA).
 */
function waitUntilCanPlay(video: HTMLVideoElement): Promise<void> {
  return new Promise((resolve) => {
    if (video.readyState >= 2) {
      resolve();
      return;
    }
    const onCanPlay = () => {
      video.removeEventListener("canplay", onCanPlay);
      resolve();
    };
    video.addEventListener("canplay", onCanPlay);

    // Safety timeout — don't hang forever if canplay never fires.
    setTimeout(() => {
      video.removeEventListener("canplay", onCanPlay);
      resolve();
    }, 5000);
  });
}

/**
 * Map a caught error to a structured CameraError.
 */
function mapError(e: unknown): CameraError {
  if (e instanceof DOMException) {
    switch (e.name) {
      case "NotAllowedError":
        return ERROR_MESSAGES.permission_denied;
      case "NotFoundError":
        return ERROR_MESSAGES.not_found;
      case "NotReadableError":
        return ERROR_MESSAGES.not_readable;
      case "OverconstrainedError":
        return ERROR_MESSAGES.overconstrained;
      case "AbortError":
        return ERROR_MESSAGES.abort;
      case "SecurityError":
        return ERROR_MESSAGES.insecure_origin;
      default:
        return {
          code: e.name.toLowerCase(),
          message: e.message || "Camera error occurred",
          isRecoverable: true,
        };
    }
  }

  if (e instanceof Error) {
    // Some browsers throw a TypeError for missing mediaDevices.
    if (e.message.includes("getUserMedia") || e.message.includes("mediaDevices")) {
      return ERROR_MESSAGES.insecure_origin;
    }
    return {
      code: "unknown",
      message: e.message,
      isRecoverable: true,
    };
  }

  return ERROR_MESSAGES.unknown;
}
