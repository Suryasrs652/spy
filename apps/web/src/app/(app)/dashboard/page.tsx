import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import type { EntitlementStatus, Project } from "@/lib/api";

export default async function DashboardPage() {
  const [entitlement, projects] = await Promise.all([
    serverApiGet<EntitlementStatus>("entitlements/audit"),
    serverApiGet<Project[]>("projects"),
  ]);

  const hasProjects = projects && projects.length > 0;

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-2xl font-semibold">Overview</h1>
      <p className="text-muted mt-1">What happened, what&apos;s wrong, and what to do next.</p>

      <div className="mt-8 card p-6">
        {entitlement?.can_run ? (
          <div className="flex items-center justify-between">
            <div>
              <div className="font-medium">
                {entitlement.type === "FREE_LIFETIME" ? "Your free audit is ready." : `${entitlement.remaining} credit(s) available.`}
              </div>
              <div className="text-sm text-muted mt-1">
                Run a complete SEO, AEO and GEO audit on any site you own.
              </div>
            </div>
            <Link href={hasProjects ? "/projects" : "/projects/new"} className="btn-primary">
              Run My Next Audit
            </Link>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <div>
              <div className="font-medium">
                {entitlement?.reason === "EMAIL_NOT_VERIFIED"
                  ? "Verify your email to unlock your free audit."
                  : "Your free audit has been used."}
              </div>
              <div className="text-sm text-muted mt-1">
                {entitlement?.reason === "EMAIL_NOT_VERIFIED"
                  ? "Check your inbox for the verification link."
                  : "Buy a credit to run another audit and measure what improved."}
              </div>
            </div>
            {entitlement?.reason !== "EMAIL_NOT_VERIFIED" && (
              <Link href="/billing" className="btn-primary">Upgrade to Spy Pro</Link>
            )}
          </div>
        )}
      </div>

      <h2 className="text-lg font-semibold mt-10 mb-4">Your Projects</h2>
      {!projects ? (
        <div className="card p-6 text-muted text-sm">Couldn&apos;t load projects right now.</div>
      ) : projects.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="text-muted">No projects yet — add your first website to get started.</p>
          <Link href="/projects/new" className="btn-primary inline-block mt-4">Add a Project</Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {projects.map((p) => (
            <Link key={p.id} href={`/projects/${p.id}`} className="card p-5 hover:border-accent transition-colors">
              <div className="font-medium">{p.name}</div>
              <div className="text-sm text-muted mt-1">{p.domain}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
