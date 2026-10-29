import RunPanel from "@/components/RunPanel";

export const metadata = { title: "Run analysis · Pecora.ai" };

export default function RunPage() {
  return (
    <div className="space-y-6">
      <div className="max-w-3xl">
        <p className="label">Run analysis</p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">Put a new filing on trial</h1>
        <p className="mt-3 leading-relaxed text-ink/85">
          Enter a company and fiscal year. Pecora.ai fetches the original 10-K, hides the company, screens it for
          red flags and runs the full trial on your machine. When it finishes, the case joins the case files.
        </p>
      </div>
      <RunPanel />
    </div>
  );
}
