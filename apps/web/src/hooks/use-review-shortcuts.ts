import { useEffect } from "react";

interface Options {
  enabled: boolean;
  onRate: (rating: number) => void;
  onReject: () => void;
  onPick: () => void;
  onNext: () => void;
  onPrev: () => void;
  onTogglePreview: () => void;
}

export function useReviewShortcuts(options: Options) {
  useEffect(() => {
    if (!options.enabled) {
      return;
    }

    const handle = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (event.key >= "1" && event.key <= "5") {
        options.onRate(Number(event.key));
      } else if (event.key.toLowerCase() === "x") {
        options.onReject();
      } else if (event.key.toLowerCase() === "p") {
        options.onPick();
      } else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
        options.onNext();
      } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        options.onPrev();
      } else if (event.key === " ") {
        event.preventDefault();
        options.onTogglePreview();
      }
    };

    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [options]);
}
