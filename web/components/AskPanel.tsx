"use client";

import { useRef, useState } from "react";
import type { AskCitation, AskReply, AskTurn } from "@/lib/ask";
import type { Span } from "@/lib/types";

const STATUS: Record<string, { text: string; tone: string }> = {
  exact: { text: "✓ verified", tone: "text-dismissed" },
  near: { text: "✓ verified (minor differences)", tone: "text-dismissed" },
  altered: { text: "✗ altered", tone: "text-auditor" },
  wrong_passage: { text: "⚠ from a different passage", tone: "text-inconclusive" },
  not_found: { text: "✗ not in the filing", tone: "text-auditor" },
};

type Entry = { question: string; reply: AskReply | null };

/** Follow-up questions about the case, answered from the trial's own passages, with every quote checked. */
export default function AskPanel({ caseId, suggestions, sample, onShow }: {
  caseId: string;
  suggestions: string[];
  sample: boolean;
  onShow: (spans: Span[], caption: string) => void;
}) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  const askQuestion = async (question: string) => {
    question = question.trim();
    if (!question || busy) return;
    const history: AskTurn[] = entries.flatMap((e) =>
      e.reply ? [{ role: "user" as const, content: e.question }, { role: "assistant" as const, content: e.reply.answer }] : []);
    setEntries((all) => [...all, { question, reply: null }]);
    setDraft("");
    setError(null);
    setBusy(true);
    try {
      const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/ask/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? `Request failed (${res.status})`);
      setEntries((all) => all.map((e, i) => (i === all.length - 1 ? { ...e, reply: body as AskReply } : e)));
    } catch (e) {
      setEntries((all) => all.slice(0, -1));
      setDraft(question);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const unasked = suggestions.filter((s) => !entries.some((e) => e.question === s));

  return (
    <section id="ask" className="scroll-mt-20 rounded-md border border-rule bg-card p-4">
      <h3 className="text-lg font-semibold">Ask about this filing</h3>
      <p className="mt-1 font-sans text-sm text-muted">
        Answers draw only on the passages these trials used. Every quote in an answer is checked against the filing.
      </p>

      {entries.length > 0 && (
        <ol className="mt-4 space-y-5">
          {entries.map((e, i) => (
            <li key={i} className="space-y-2">
              <p className="font-sans text-[0.95rem] font-semibold">{e.question}</p>
              {e.reply ? (
                <Answer reply={e.reply} onShow={onShow} />
              ) : (
                <p className="animate-pulse font-sans text-sm text-muted">Reading the passages…</p>
              )}
            </li>
          ))}
        </ol>
      )}

      {unasked.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {unasked.map((s) => (
            <button
              key={s}
              type="button"
              disabled={busy}
              onClick={() => askQuestion(s)}
              className="rounded-full border border-ink/25 px-3 py-1 text-left font-sans text-sm hover:border-ink/60 hover:bg-paper disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="mt-4 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          askQuestion(draft);
        }}
      >
        <label htmlFor="ask-input" className="sr-only">Your question</label>
        <textarea
          id="ask-input"
          ref={input}
          rows={1}
          value={draft}
          maxLength={500}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              askQuestion(draft);
            }
          }}
          placeholder="Ask why a finding was upheld, what the Defender missed…"
          className="min-h-[2.6rem] flex-1 resize-y rounded border border-rule bg-paper/60 px-3 py-2 font-sans text-sm outline-none focus:border-ink/60"
        />
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          className="rounded bg-ink px-4 py-2 font-sans text-sm text-paper hover:bg-ink/85 disabled:opacity-40"
        >
          Ask
        </button>
      </form>
      {error && <p className="mt-2 font-sans text-sm text-auditor">{error}</p>}
      {sample && (
        <p className="mt-2 font-sans text-xs text-muted">
          The suggested questions are answered offline. Anything else goes to Claude, so it needs the Claude CLI or an API key.
        </p>
      )}
    </section>
  );
}

function Answer({ reply, onShow }: { reply: AskReply; onShow: (spans: Span[], caption: string) => void }) {
  return (
    <div className="space-y-1.5">
      <p className={`leading-relaxed ${reply.source === "error" ? "font-sans text-sm text-auditor" : ""}`}>{reply.answer}</p>
      {reply.citations.map((c, i) => <AnswerQuote key={i} c={c} onShow={onShow} />)}
      {reply.error && <p className="font-mono text-xs text-muted">{reply.error}</p>}
    </div>
  );
}

function AnswerQuote({ c, onShow }: { c: AskCitation; onShow: (spans: Span[], caption: string) => void }) {
  const status = STATUS[c.status] ?? { text: `✗ ${c.status}`, tone: "text-muted" };
  const locatable = c.filing_spans.length > 0;
  return (
    <button
      type="button"
      disabled={!locatable}
      onClick={() => onShow(c.filing_spans, "answer quote")}
      title={locatable ? "Show in the filing" : "This quote could not be located in the filing"}
      className={`block w-full rounded border border-transparent bg-ink/[0.05] px-2.5 py-1.5 text-left font-mono text-[0.78rem] leading-snug transition ${
        locatable ? "cursor-pointer hover:border-ink/30" : "cursor-default"
      }`}
    >
      &ldquo;{c.quote}&rdquo;{" "}
      <span className={`whitespace-nowrap font-sans text-xs ${status.tone}`}>{status.text}</span>
      {c.status === "altered" && c.changes.length > 0 && (
        <span className="mt-1 block font-sans text-xs text-auditor">{c.changes.join("; ")}</span>
      )}
    </button>
  );
}
