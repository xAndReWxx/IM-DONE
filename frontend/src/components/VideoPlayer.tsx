/* ============================================================
 * PhysioAI Pro V2 — VideoPlayer
 * ============================================================
 * Simple inline video player for exercise demonstration.
 * Shows a <video> with controls, loops automatically, and
 * displays a placeholder if the video 404s.
 * ============================================================ */

import { useState } from "react";
import "./VideoPlayer.css";

type Props = {
  src: string;
  title: string;
};

export function VideoPlayer({ src, title }: Props) {
  const [notFound, setNotFound] = useState(false);

  if (notFound) {
    return (
      <div className="videoplayer videoplayer--placeholder" aria-label={`No video for ${title}`}>
        <div className="videoplayer__placeholder-inner">
          <span className="label">NO VIDEO</span>
          <span className="videoplayer__placeholder-name">{title}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="videoplayer">
      <video
        className="videoplayer__video"
        src={src}
        title={title}
        controls
        loop
        muted
        playsInline
        onError={() => setNotFound(true)}
        aria-label={`Exercise video: ${title}`}
      />
    </div>
  );
}
