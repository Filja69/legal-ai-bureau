"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/settings", label: "Profile" },
  { href: "/settings/workspace", label: "Workspace" },
  { href: "/settings/security", label: "Security" },
];

export function SettingsNav() {
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
