import type { Metadata } from "next";
import Link from "next/link";
import Nav from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pecora.ai",
  description: "Adversarial AI review of SEC 10-K filings: every red flag argued, judged, and checked against the filing.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-rule bg-paper/95 backdrop-blur">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-baseline gap-3">
              <span className="text-xl font-bold tracking-tight">Pecora.ai</span>
              <span className="hidden font-sans text-sm text-muted sm:inline">AI findings you can argue with</span>
            </Link>
            <Nav />
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">{children}</main>
        <footer className="mx-auto max-w-7xl border-t border-rule px-4 py-6 font-sans text-xs text-muted sm:px-6">
          Pecora.ai flags questions worth asking. An upheld finding is not evidence of fraud and nothing here is
          investment advice. All filings are public SEC records.
        </footer>
      </body>
    </html>
  );
}
