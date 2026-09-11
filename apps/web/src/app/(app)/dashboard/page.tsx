import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import type { Project } from "@/lib/api";

export default async function DashboardPage() {
  const projects = await serverApiGet<Project[]>("projects");

  const hasProjects = projects && projects.length > 0;

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-2xl font-semibold">Overview</h1>
      <p className="text-muted mt-1">What happened, what&apos;s wrong, and what to do next.</p>

      <div className="mt-8 card p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">Run as many audits as you like.</div>
            <div className="text-sm text-muted mt-1">
              A complete SEO, AEO and GEO audit of any site you own — free and unmetered.
            </div>
          </div>
          <Link href={hasProjects ? "/projects" : "/projects/new"} className="btn-primary">
            Run an Audit
          </Link>
        </div>
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
