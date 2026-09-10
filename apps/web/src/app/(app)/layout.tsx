import { redirect } from "next/navigation";
import Link from "next/link";
import { auth, signOut } from "@/lib/auth";
import { NotificationBell } from "./NotificationBell";

const NAV_LIVE = [
  { href: "/dashboard", label: "Overview" },
  { href: "/projects", label: "Projects" },
];

// Site Explorer, Keywords, Content Explorer, Search Console, AEO, GEO and
// Reports are all project-scoped (no single global URL to link to from
// here, like Backlinks/Rank Tracker/Competitors before them) — reached from
// a project's own detail page instead, not listed as top-level nav items.

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session) {
    redirect("/login");
  }

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
          <Link href="/billing" className="block px-3 py-2 rounded-md text-sm hover:bg-white/5">
            Billing
          </Link>
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
        <div className="px-5 py-4 border-t border-border text-xs text-muted">
          <div className="truncate">{session.user?.email}</div>
          <form
            action={async () => {
              "use server";
              await signOut({ redirectTo: "/" });
            }}
          >
            <button type="submit" className="mt-2 text-accent hover:underline">Log out</button>
          </form>
        </div>
      </aside>
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  );
}
