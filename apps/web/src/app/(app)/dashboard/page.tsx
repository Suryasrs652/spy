import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import { getLatestCompletedAudit } from "@/lib/latestAudit";
import type { AuditSummary, Project } from "@/lib/api";

function band(score: number | null): string {
  if (score === null) return "text-muted";
  if (score >= 90) return "text-green-400";
  if (score >= 75) return "text-blue-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-orange-400";
  return "text-red-400";
}

type ProjectSnapshot = { project: Project; summary: AuditSummary | null };

async function snapshot(project: Project): Promise<ProjectSnapshot> {
  const audit = await getLatestCompletedAudit(project.id);
  if (!audit) return { project, summary: null };
  const summary = await serverApiGet<AuditSummary>(`audits/${audit.id}/summary`).catch(() => null);
  return { project, summary };
}

export default async function DashboardPage() {
  const projects = await serverApiGet<Project[]>("projects");
  const hasProjects = projects && projects.length > 0;
  const snapshots = hasProjects ? await Promise.all(projects.map(snapshot)) : [];

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
        <div className="space-y-4">
          {snapshots.map(({ project, summary }) => (
            <Link
              key={project.id}
              href={summary ? `/audits/${summary.audit_id}` : `/projects/${project.id}`}
              className="card p-5 block hover:border-accent transition-colors"
            >
              <div className="flex items-start justify-between gap-6 flex-wrap">
                <div className="min-w-0">
                  <div className="font-medium">{project.name}</div>
                  <div className="text-sm text-muted mt-1">{project.domain}</div>
                </div>

                {!summary ? (
                  <div className="text-sm text-muted">No completed audit yet</div>
                ) : (
                  <div className="flex items-center gap-6 flex-wrap">
                    <div className="text-center">
                      <div className={`text-2xl font-bold ${band(summary.spy_score)}`}>
                        {summary.spy_score ?? "—"}
                      </div>
                      <div className="text-[10px] text-muted uppercase tracking-wide">Overall</div>
                    </div>
                    {(["seo", "aeo", "geo"] as const).map((key) => (
                      <div key={key} className="text-center">
                        <div className={`text-lg font-semibold ${band(summary[`${key}_score`])}`}>
                          {summary[`${key}_score`] ?? "—"}
                        </div>
                        <div className="text-[10px] text-muted uppercase tracking-wide">{key}</div>
                      </div>
                    ))}
                    <div className="text-center">
                      <div
                        className={`text-lg font-semibold ${
                          summary.issue_counts.critical.issues + summary.issue_counts.high.issues > 0
                            ? "text-orange-400"
                            : "text-muted"
                        }`}
                      >
                        {summary.issue_counts.critical.issues + summary.issue_counts.high.issues}
                      </div>
                      <div className="text-[10px] text-muted uppercase tracking-wide">
                        Critical + high
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {summary && summary.blockers.length > 0 && (
                <div className="mt-4 pt-4 border-t border-border">
                  <div className="text-[10px] text-muted uppercase tracking-wide mb-2">
                    Biggest blocker
                  </div>
                  <div className="text-sm">{summary.blockers[0].title}</div>
                  <div className="text-xs text-muted mt-1">
                    Worth {summary.blockers[0].points_recoverable.toFixed(1)} points ·{" "}
                    {summary.blockers[0].effort_label.toLowerCase()} effort
                  </div>
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
