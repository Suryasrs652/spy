import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import { getLatestCompletedAudit } from "@/lib/latestAudit";
import type { AuditPage, Project } from "@/lib/api";

export default async function ContentExplorerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [project, audit] = await Promise.all([
    serverApiGet<Project>(`projects/${id}`),
    getLatestCompletedAudit(id),
  ]);

  if (!project) {
    return <div className="p-8 text-muted">Project not found.</div>;
  }

  const pages = audit ? await serverApiGet<AuditPage[]>(`audits/${audit.id}/pages`) : null;

  return (
    <div className="p-8 max-w-6xl">
      <Link href={`/projects/${id}`} className="text-sm text-muted hover:text-accent">← Back to project</Link>
      <h1 className="text-2xl font-semibold mt-2 mb-1">Content Explorer</h1>
      <p className="text-muted text-sm mb-8">
        {project.canonical_origin} — content-quality signals per page from the latest completed audit.
      </p>

      {!audit ? (
        <div className="card p-8 text-center text-muted">
          No completed audit yet. Run an audit from the project page to populate content signals.
        </div>
      ) : !pages || pages.length === 0 ? (
        <div className="card p-8 text-center text-muted">The latest audit crawled no pages.</div>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-4 mb-8">
            <div className="card p-5">
              <div className="text-2xl font-bold">{pages.filter((p) => p.has_schema).length}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">With Schema</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{pages.filter((p) => !p.heading_order_valid).length}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Broken Heading Order</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{pages.filter((p) => p.has_author_byline).length}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">With Byline</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{pages.reduce((sum, p) => sum + p.images_missing_alt, 0)}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Images Missing Alt</div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead>
                <tr className="text-left text-muted border-b border-border">
                  <th className="py-2 pr-4 font-normal">URL</th>
                  <th className="py-2 pr-4 font-normal">Words</th>
                  <th className="py-2 pr-4 font-normal">H1/H2/H3</th>
                  <th className="py-2 pr-4 font-normal">Heading Order</th>
                  <th className="py-2 pr-4 font-normal">Schema</th>
                  <th className="py-2 pr-4 font-normal">Questions</th>
                  <th className="py-2 pr-4 font-normal">Lists</th>
                  <th className="py-2 pr-4 font-normal">Tables</th>
                  <th className="py-2 pr-4 font-normal">Def. List</th>
                  <th className="py-2 pr-4 font-normal">Byline</th>
                  <th className="py-2 pr-4 font-normal">Imgs w/o Alt</th>
                </tr>
              </thead>
              <tbody>
                {pages.map((p) => (
                  <tr key={p.id} className="border-b border-border/50 hover:bg-white/5">
                    <td className="py-2.5 pr-4 max-w-xs truncate" title={p.url}>{p.url}</td>
                    <td className="py-2.5 pr-4">{p.word_count ?? "—"}</td>
                    <td className="py-2.5 pr-4">{p.h1_count}/{p.h2_count}/{p.h3_count}</td>
                    <td className="py-2.5 pr-4">
                      {p.heading_order_valid ? "Valid" : <span className="text-yellow-400">Invalid</span>}
                    </td>
                    <td className="py-2.5 pr-4 max-w-[10rem] truncate" title={p.schema_types.join(", ")}>
                      {p.has_schema ? p.schema_types.join(", ") || "Yes" : "—"}
                    </td>
                    <td className="py-2.5 pr-4">{p.question_heading_count}</td>
                    <td className="py-2.5 pr-4">{p.list_count}</td>
                    <td className="py-2.5 pr-4">{p.table_count}</td>
                    <td className="py-2.5 pr-4">{p.has_definition_list ? "Yes" : "No"}</td>
                    <td className="py-2.5 pr-4">{p.has_author_byline ? "Yes" : "No"}</td>
                    <td className="py-2.5 pr-4">
                      {p.images_missing_alt > 0 ? (
                        <span className="text-yellow-400">{p.images_missing_alt}</span>
                      ) : (
                        0
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
