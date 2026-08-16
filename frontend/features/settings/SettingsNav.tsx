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
    <div className="flex gap-1 border-b border-slate-800 text-sm">
      {LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className={`px-3 py-2 ${
            pathname === l.href ? "border-b-2 border-slate-200 text-slate-100" : "text-slate-500 hover:text-slate-300"
          }`}
        >
          {l.label}
        </Link>
      ))}
    </div>
  );
}
