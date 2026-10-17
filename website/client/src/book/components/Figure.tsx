import { useRef, useState } from "react";
import { usePrint } from "../context";
import { beginPending } from "./pending";

export interface FrameSpec {
  /** Image file under `base`, shown in the print frame sequence. */
  src?: string;
  alt: string;
  caption: string;
}

interface FigureProps {
  /** Base path of the scene's media, e.g. /book/media/design_space. */
  base: string;
  /** File stem used for the video and poster. */
  stem: string;
  alt: string;
  caption: string;
  frames: FrameSpec[];
}

function Img({ src, alt }: { src: string; alt: string }) {
  const doneRef = useRef<(() => void) | null>(null);
  if (!doneRef.current && typeof window !== "undefined") doneRef.current = beginPending();
  const finish = () => doneRef.current?.();
  return <img src={src} alt={alt} loading="eager" onLoad={finish} onError={finish} />;
}

/**
 * Frame caption. The number and the text are one string: Paged.js drops
 * whitespace-only text nodes, which turned "1. Every" into "1.Every".
 */
function FrameCaption({ index, caption }: { index: number; caption: string }) {
  return (
    <div className="book-frame-cap">
      <b>{`${index + 1}.`}</b>
      {` ${caption}`}
    </div>
  );
}

export default function Figure(props: FigureProps) {
  const { base, stem, alt, caption, frames } = props;
  const print = usePrint();
  const [playing, setPlaying] = useState(false);
  const video = useRef<HTMLVideoElement>(null);

  if (print) {
    return (
      <figure className="book-figure book-frames" role="group" aria-label={alt}>
        <div className="book-frame-row">
          {frames.map((f, i) => {
            if (!f.src) throw new Error(`Figure ${stem}: frame ${i + 1} has no src`);
            return (
              <div className="book-frame" key={f.src}>
                <Img src={`${base}/${f.src}`} alt={f.alt} />
                <FrameCaption index={i} caption={f.caption} />
              </div>
            );
          })}
        </div>
        <figcaption>{caption}</figcaption>
      </figure>
    );
  }

  const toggle = () => {
    const v = video.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
  };

  return (
    <figure className="book-figure">
      <video
        ref={video}
        poster={`${base}/${stem}-poster.png`}
        preload="none"
        muted
        loop
        playsInline
        controls={false}
        aria-label={alt}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
      >
        <source src={`${base}/${stem}.webm`} type="video/webm" />
        <source src={`${base}/${stem}.mp4`} type="video/mp4" />
      </video>
      <button type="button" className="book-play" onClick={toggle} aria-pressed={playing}>
        {playing ? "Pause animation" : "Play animation"}
      </button>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
