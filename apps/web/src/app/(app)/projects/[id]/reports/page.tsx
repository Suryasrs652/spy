import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import type { Audit, Project } from "@/lib/api";
import { DownloadReportButton } from "./DownloadReportButton";

export default async function ReportsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [project, audits] = await Promise.all([
    serverApiGet<Project>(`projects/${id}`),
    serverApiGet<Audit[]>(`projects/${id}/audits`),
  ]);

  if (!project) {
    return <div className="p-8 text-muted">Project not found.</div>;
  }

  const completed = (audits ?? []).filter((a) => a.status === "COMPLETED");

  return (
    <div className="p-8 max-w-4xl">
      <Link href={`/projects/${id}`} className="text-sm text-muted hover:text-accent">← Back to project</Link>
      <h1 className="text-2xl font-semibold mt-2 mb-1">Reports</h1>
      <p className="text-muted text-sm mb-8">
        {project.canonical_origin} — download the PDF report for any completed audit.
      </p>

      {!audits ? (
        <div className="card p-6 text-muted text-sm">Couldn&apos;t load audits.</div>
      ) : completed.length === 0 ? (
        <div className="card p-8 text-center text-muted">
          No completed audits yet. Reports become available once an audit finishes.
        </div>
      ) : (
        <div className="space-y-2">
          {completed.map((a) => (
            <div key={a.id} className="card p-4 flex items-center justify-between gap-4">
              <div>
                <div className="text-sm font-medium">
                  Spy Score {a.spy_score !== null ? a.spy_score.toFixed(0) : "—"}
                </div>
                <div className="text-xs text-muted mt-1">
                  Completed {a.completed_at ? new Date(a.completed_at).toLocaleString() : "—"} · v{a.score_version}
                </div>
              </div>
              <div className="flex items-center gap-4 shrink-0">
                <Link href={`/audits/${a.id}`} className="text-accent text-sm hover:underline">View</Link>
                <DownloadReportButton auditId={a.id} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
