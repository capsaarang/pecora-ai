import CaseList from "@/components/CaseList";
import { listCases } from "@/lib/data";

export const dynamic = "force-dynamic";

export const metadata = { title: "Case files · Pecora.ai" };

export default function Cases() {
  return (
    <div className="space-y-6">
      <div className="max-w-3xl">
        <p className="label">Case files</p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">Every filing we&rsquo;ve put on trial</h1>
        <p className="mt-3 leading-relaxed text-ink/85">
          Each case shows the funnel from flagged passages to upheld findings, the full trial for each finding, and
          every quote highlighted in the original filing.
        </p>
      </div>
      <CaseList cases={listCases()} />
    </div>
  );
}
