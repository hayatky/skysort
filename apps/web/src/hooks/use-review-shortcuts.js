import { useEffect } from "react";
export function useReviewShortcuts(options) {
    useEffect(() => {
        if (!options.enabled) {
            return;
        }
        const handle = (event) => {
            if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
                return;
            }
            if (event.key >= "1" && event.key <= "5") {
                options.onRate(Number(event.key));
            }
            else if (event.key.toLowerCase() === "x") {
                options.onReject();
            }
            else if (event.key.toLowerCase() === "p") {
                options.onPick();
            }
            else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                options.onNext();
            }
            else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                options.onPrev();
            }
            else if (event.key === " ") {
                event.preventDefault();
                options.onTogglePreview();
            }
        };
        window.addEventListener("keydown", handle);
        return () => window.removeEventListener("keydown", handle);
    }, [options]);
}
