import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import type { Audit, EntitlementStatus, Project } from "@/lib/api";
import { RunAuditButton } from "./RunAuditButton";

const SEVERITY_BAND: Record<string, string> = {
  COMPLETED: "text-green-400", FAILED: "text-red-400", CANCELLED: "text-muted",
};

export default async function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [project, audits, entitlement] = await Promise.all([
    serverApiGet<Project>(`projects/${id}`),
    serverApiGet<Audit[]>(`projects/${id}/audits`),
    serverApiGet<EntitlementStatus>("entitlements/audit"),
  ]);

  if (!project) {
    return <div className="p-8 text-muted">Project not found.</div>;
  }

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{project.name}</h1>
          <p className="text-muted text-sm mt-1">{project.canonical_origin}</p>
        </div>
        <RunAuditButton projectId={project.id} canRun={!!entitlement?.can_run} reason={entitlement?.reason ?? null} />
      </div>

      <div className="flex gap-4 mt-6 text-sm">
        <Link href={`/projects/${project.id}/backlinks`} className="text-accent hover:underline">Backlinks</Link>
        <Link href={`/projects/${project.id}/rank-tracker`} className="text-accent hover:underline">Rank Tracker</Link>
        <Link href={`/projects/${project.id}/competitors`} className="text-accent hover:underline">Competitors</Link>
      </div>

      <h2 className="text-lg font-semibold mt-10 mb-4">Audit History</h2>
      {!audits ? (
        <div className="card p-6 text-muted text-sm">Couldn't load audits.</div>
      ) : audits.length === 0 ? (
        <div className="card p-8 text-center text-muted">No audits yet — run your first one above.</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="py-2 font-normal">Status</th>
              <th className="py-2 font-normal">Spy Score</th>
              <th className="py-2 font-normal">Started</th>
              <th className="py-2 font-normal"></th>
            </tr>
          </thead>
          <tbody>
            {audits.map((a) => (
              <tr key={a.id} className="border-b border-border/50 hover:bg-white/5">
                <td className={`py-3 ${SEVERITY_BAND[a.status] ?? ""}`}>{a.status}</td>
                <td className="py-3">{a.spy_score ?? "—"}</td>
                <td className="py-3 text-muted">{a.created_at ? new Date(a.created_at).toLocaleString() : "—"}</td>
                <td className="py-3">
                  <Link href={`/audits/${a.id}`} className="text-accent">View</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
