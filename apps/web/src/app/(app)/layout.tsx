import Link from "next/link";
import { NotificationBell } from "./NotificationBell";

const NAV_LIVE = [
  { href: "/dashboard", label: "Overview" },
  { href: "/projects", label: "Projects" },
];

// Site Explorer, Keywords, Content Explorer, Search Console, AEO, GEO and
// Reports are all project-scoped (no single global URL to link to from
// here, like Backlinks/Rank Tracker/Competitors before them) — reached from
// a project's own detail page instead, not listed as top-level nav items.

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex">
      <aside className="w-60 shrink-0 border-r border-border bg-surface flex flex-col">
        <div className="px-5 py-5 text-lg font-bold tracking-tight">SPY</div>
        <nav className="flex-1 px-3 space-y-0.5 overflow-y-auto">
          {NAV_LIVE.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="block px-3 py-2 rounded-md text-sm hover:bg-white/5"
            >
              {item.label}
            </Link>
          ))}
          <div className="my-3 border-t border-border" />
          <Link href="/settings" className="block px-3 py-2 rounded-md text-sm hover:bg-white/5">
            Settings
          </Link>
          <Link href="/admin" className="block px-3 py-2 rounded-md text-sm hover:bg-white/5 text-muted">
            Admin
          </Link>
        </nav>
        <div className="px-3 pb-3 border-t border-border pt-3">
          <NotificationBell />
        </div>
      </aside>
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  );
}
