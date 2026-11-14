"use client";

import { useEffect, useRef, useState } from "react";

/** "Watch the 30-second demo": opens the walkthrough video in a dialog that can be skipped at any time. */
export default function DemoVideo({ className, label = "Watch the 30-second demo" }: { className?: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const [ended, setEnded] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const close = () => {
    video.current?.pause();
    setOpen(false);
  };

  useEffect(() => {
    if (!open) return;
    setEnded(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={className}>
        <span aria-hidden="true">▶&nbsp;</span>{label}
      </button>
      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Pecora.ai demo video"
          onClick={close}
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4 backdrop-blur-sm"
        >
          <div onClick={(e) => e.stopPropagation()} className="w-full max-w-4xl overflow-hidden rounded-md bg-card shadow-2xl">
            <div className="flex items-center justify-between gap-3 border-b border-rule px-4 py-2">
              <p className="font-sans text-sm text-muted">Pecora.ai in 30 seconds · sample trial, fictional company</p>
              <button
                type="button"
                onClick={close}
                autoFocus
                className="rounded border border-ink/30 px-3 py-1 font-sans text-sm hover:bg-paper"
              >
                {ended ? "Close" : "Skip"}
              </button>
            </div>
            <video
              ref={video}
              src="/pecora-demo.mp4"
              autoPlay
              muted
              playsInline
              controls
              onEnded={() => setEnded(true)}
              className="block aspect-video w-full bg-ink"
            />
          </div>
        </div>
      )}
    </>
  );
}
