"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Overview" },
  { href: "/cases/", label: "Cases" },
  { href: "/run/", label: "Run analysis" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="flex gap-1 font-sans text-sm" aria-label="Sections">
      {TABS.map((t) => {
        const active = t.href === "/" ? path === "/" : path.startsWith(t.href.replace(/\/$/, ""));
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={active ? "page" : undefined}
            className={`rounded px-3 py-1.5 transition-colors ${
              active ? "bg-ink text-paper" : "text-muted hover:bg-rule/60 hover:text-ink"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
