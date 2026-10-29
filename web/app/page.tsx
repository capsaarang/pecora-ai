import Link from "next/link";
import CaseList from "@/components/CaseList";
import { listCases } from "@/lib/data";

export const dynamic = "force-dynamic";

const STEPS = [
  ["Fetch the original filing", "The 10-K exactly as investors saw it on SEC EDGAR, never a later correction."],
  ["Hide the company", "Names, people and product brands are masked, so the AI judges the words, not the headlines."],
  ["Flag candidates", "An AI screener reads the passages where problems usually hide: revenue, insiders, lawsuits, risks."],
  ["Hold a trial", "An Auditor argues each flag, a Defender gives the company's side, an Adjudicator rules and scores it."],
  ["Check every quote", "Plain code verifies each quote word for word. A changed number or a dropped “not” is caught."],
  ["Compare with peers", "Key ratios are ranked against the company's industry using the SEC's own XBRL data."],
];

const ACTIONS = [
  ["Open a case file", "See every finding the screener flagged and the ones that went to trial."],
  ["Read the trial", "Auditor and Defender briefs side by side, then the Adjudicator's ruling and confidence."],
  ["Check the receipts", "Click any quote to see it highlighted in the original filing, with its verification status."],
  ["Reveal the company", "Cases are blind by default. Reveal the name only after you've read the evidence."],
];

export default function Overview() {
  const cases = listCases();
  return (
    <div className="space-y-14">
      <section className="max-w-3xl">
        <p className="label">Adversarial review of SEC 10-K filings</p>
        <h1 className="mt-2 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
          AI findings you can argue with.
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-ink/85">
          Pecora.ai reads a company&rsquo;s annual report like a skeptical investigator. Every suspicious passage is
          put on trial, every quote is checked against the filing, and only the warning signs that hold up are kept.
        </p>
        <div className="mt-6 flex flex-wrap gap-3 font-sans text-sm">
          <Link href="/cases/" className="rounded bg-ink px-4 py-2 text-paper hover:bg-ink/85">
            Open the case files
          </Link>
          <a href="#how" className="rounded border border-ink/30 px-4 py-2 hover:bg-card">
            How it works
          </a>
        </div>
      </section>

      <section>
        <h2 className="label mb-4">What you can do here</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {ACTIONS.map(([title, body]) => (
            <div key={title} className="rounded-md border border-rule bg-card p-4">
              <h3 className="font-semibold">{title}</h3>
              <p className="mt-1 font-sans text-sm leading-relaxed text-muted">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="how" className="scroll-mt-24">
        <h2 className="label mb-4">How it works</h2>
        <ol className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
          {STEPS.map(([title, body], i) => (
            <li key={title} className="flex gap-3">
              <span className="font-mono text-2xl leading-none text-muted">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3 className="font-semibold">{title}</h3>
                <p className="mt-1 font-sans text-sm leading-relaxed text-muted">{body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h2 className="label mb-4">Case files</h2>
        <CaseList cases={cases} />
      </section>

      <section className="max-w-3xl rounded-md border-l-4 border-ink/70 bg-card p-5">
        <h2 className="font-semibold">Why &ldquo;Pecora&rdquo;</h2>
        <p className="mt-2 leading-relaxed text-ink/85">
          In 1933 Ferdinand Pecora led the Senate hearings that cross-examined Wall Street after the 1929 crash. His
          work led to the laws that created the SEC. Pecora.ai cross-examines the reports those laws require.
        </p>
      </section>
    </div>
  );
}
