import type { Check } from "@/lib/types";

const STATUS: Record<string, { text: string; tone: string }> = {
  exact: { text: "✓ verified", tone: "text-dismissed" },
  near: { text: "✓ verified (minor differences)", tone: "text-dismissed" },
  altered: { text: "✗ altered", tone: "text-auditor" },
  wrong_passage: { text: "⚠ from a different passage", tone: "text-inconclusive" },
  not_found: { text: "✗ not in the filing", tone: "text-auditor" },
};

/** A quote with its verification status. Clickable when it was located in the filing. */
export default function Citation({ quote, passageId, check, selected, onSelect }: {
  quote?: string;
  passageId?: string;
  check?: Check;
  selected: boolean;
  onSelect: () => void;
}) {
  if (!quote) return null;
  const status = STATUS[check?.status ?? ""] ?? { text: check ? `✗ ${check.status}` : "", tone: "text-muted" };
  const locatable = !!check?.filing_spans?.length;
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={!locatable}
      title={locatable ? "Show in the filing" : "This quote could not be located in the filing"}
      className={`mt-1.5 block w-full rounded border px-2.5 py-1.5 text-left font-mono text-[0.78rem] leading-snug transition ${
        selected ? "border-ink bg-mark/40" : "border-transparent bg-ink/[0.05] hover:border-ink/30"
      } ${locatable ? "cursor-pointer" : "cursor-default"}`}
    >
      <span className="text-muted">[{passageId}]</span> &ldquo;{quote}&rdquo;{" "}
      <span className={`whitespace-nowrap font-sans text-xs ${status.tone}`}>{status.text}</span>
      {check?.status === "altered" && check.changes.length > 0 && (
        <span className="mt-1 block font-sans text-xs text-auditor">{check.changes.join("; ")}</span>
      )}
    </button>
  );
}
