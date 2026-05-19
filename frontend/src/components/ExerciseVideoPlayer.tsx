import { memo, useState, useRef, useEffect } from "react";
import "./VideoPlayer.css";

type Props = {
  src: string;
  title: string;
};

export const ExerciseVideoPlayer = memo(function ExerciseVideoPlayer({ src, title }: Props) {
  const [error, setError] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Auto-play reliably
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.play().catch((err) => {
        console.warn("Autoplay blocked or failed", err);
      });
    }
  }, [src]);

  if (error) {
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
        ref={videoRef}
        className="videoplayer__video"
        src={src}
        title={title}
        autoPlay
        loop
        muted
        playsInline
        onError={() => setError(true)}
        aria-label={`Exercise video: ${title}`}
      />
    </div>
  );
});
