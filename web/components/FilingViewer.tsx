"use client";

import { useEffect, useRef } from "react";
import type { CaseFile, Span } from "@/lib/types";

/** The filing section that holds the selected quote, with every span of it highlighted and scrolled into view. */
export default function FilingViewer({ filing, spans, caption }: {
  filing: CaseFile["filing"];
  spans: Span[] | null;
  caption: string | null;
}) {
  const box = useRef<HTMLDivElement>(null);
  const first = useRef<HTMLElement>(null);

  useEffect(() => {
    // Scroll inside the viewer only, so the trial column keeps its place
    if (box.current && first.current) {
      box.current.scrollTo({ top: first.current.offsetTop - box.current.clientHeight / 3, behavior: "smooth" });
    }
  }, [spans]);

  if (!spans?.length) {
    return (
      <div className="flex h-full flex-col">
        <p className="label">The filing</p>
        <p className="mt-2 font-sans text-sm text-muted">Click any quote in the trial to see it here, in context.</p>
        <ul className="mt-4 space-y-1 overflow-y-auto font-sans text-sm">
          {filing.sections.filter((s) => s.end - s.start > 2000).map((s) => (
            <li key={s.start} className="flex justify-between gap-3 border-b border-rule/60 py-1">
              <span>{s.item_number} · {s.name}</span>
              <span className="font-mono text-xs text-muted">{((s.end - s.start) / 1000).toFixed(0)}k chars</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const section = filing.sections.find((s) => s.start <= spans[0][0] && spans[0][0] < s.end)
    ?? { name: "Filing", item_number: "", start: 0, end: filing.text.length };
  const pieces: React.ReactNode[] = [];
  let pos = section.start;
  spans.filter(([a]) => a < section.end).forEach(([a, b], i) => {
    pieces.push(filing.text.slice(pos, a));
    pieces.push(<mark key={a} ref={i === 0 ? first : undefined}>{filing.text.slice(a, b)}</mark>);
    pos = b;
  });
  pieces.push(filing.text.slice(pos, section.end));

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-baseline justify-between gap-3 border-b border-rule pb-2">
        <p className="label">{section.item_number} · {section.name}</p>
        {caption && <p className="truncate font-sans text-xs text-muted">{caption}</p>}
      </div>
      <div ref={box} className="relative mt-2 flex-1 overflow-y-auto whitespace-pre-wrap pr-2 text-[0.92rem] leading-relaxed">
        {pieces}
      </div>
    </div>
  );
}
