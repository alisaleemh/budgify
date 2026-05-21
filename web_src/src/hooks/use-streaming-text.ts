import { useEffect, useState } from "react";

function prefersReducedMotion() {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function useStreamingText(text: string, active: boolean) {
  const [displayText, setDisplayText] = useState(active ? "" : text);

  useEffect(() => {
    if (!active || prefersReducedMotion()) {
      setDisplayText(text);
      return;
    }

    let frame = 0;
    let index = 0;
    const step = Math.max(1, Math.ceil(text.length / 48));
    const tick = () => {
      index = Math.min(text.length, index + step);
      setDisplayText(text.slice(0, index));
      if (index < text.length) {
        frame = window.setTimeout(tick, 16);
      }
    };

    setDisplayText("");
    frame = window.setTimeout(tick, 0);
    return () => window.clearTimeout(frame);
  }, [active, text]);

  return displayText;
}
