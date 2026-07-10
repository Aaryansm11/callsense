"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ROLES = [
  { key: "director", label: "Sales Director", href: "/director" },
  { key: "team", label: "Team Leader", href: "/team" },
  { key: "advisor", label: "Advisor", href: "/advisor" },
];

export function Header() {
  const pathname = usePathname();
  const active =
    ROLES.find((r) => pathname.startsWith(r.href))?.key ?? "director";

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        <Link href="/director" className="flex items-center gap-2.5">
          {/* SkilloVilla brand mark (downloaded into /public) */}
          <img
            src="/skillovilla-mark.png"
            alt="SkilloVilla"
            width={32}
            height={32}
            className="rounded-md"
          />
          <div className="leading-tight">
            <div className="text-sm font-semibold text-ink">CallSense</div>
            <div className="text-[11px] text-muted">
              SkilloVilla · Sales-Call Intelligence
            </div>
          </div>
        </Link>

        <div className="flex items-center gap-2">
          <span className="hidden text-xs text-muted sm:inline">Viewing as</span>
          <nav className="flex rounded-lg border border-border bg-gray-50 p-0.5">
            {ROLES.map((r) => (
              <Link
                key={r.key}
                href={r.href}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  active === r.key
                    ? "bg-white text-ink shadow-sm"
                    : "text-muted hover:text-ink"
                }`}
              >
                {r.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </header>
  );
}
