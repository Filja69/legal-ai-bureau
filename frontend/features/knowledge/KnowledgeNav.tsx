"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/knowledge", label: "Overview" },
  { href: "/knowledge/sources", label: "Sources" },
  { href: "/knowledge/index", label: "Index" },
  { href: "/knowledge/search-debug", label: "Search Debug" },
];

export function KnowledgeNav() {
  const pathname = usePathname();
  return (
    <div className="flex w-fit gap-1 overflow-x-auto rounded-xl border border-line bg-panel-muted p-1 text-sm">
      {LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className={`shrink-0 rounded-lg px-3.5 py-1.5 font-medium transition-colors ${
            pathname === l.href ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink"
          }`}
        >
          {l.label}
        </Link>
      ))}
    </div>
  );
}
