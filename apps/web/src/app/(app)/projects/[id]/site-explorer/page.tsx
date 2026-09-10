import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import { getLatestCompletedAudit } from "@/lib/latestAudit";
import type { AuditPage, Project } from "@/lib/api";

function StatusBadge({ code }: { code: number | null }) {
  if (code === null) return <span className="text-muted">—</span>;
  const color = code >= 200 && code < 300 ? "text-green-400" : code >= 300 && code < 400 ? "text-yellow-400" : "text-red-400";
  return <span className={color}>{code}</span>;
}

export default async function SiteExplorerPage({ params }: { params: Promise<{ id: string }> }) {
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
      <h1 className="text-2xl font-semibold mt-2 mb-1">Site Explorer</h1>
      <p className="text-muted text-sm mb-8">
        {project.canonical_origin} — technical inventory of every crawled URL from the latest completed audit.
      </p>

      {!audit ? (
        <div className="card p-8 text-center text-muted">
          No completed audit yet. Run an audit from the project page to populate the site inventory.
        </div>
      ) : !pages || pages.length === 0 ? (
        <div className="card p-8 text-center text-muted">The latest audit crawled no pages.</div>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-4 mb-8">
            <div className="card p-5">
              <div className="text-2xl font-bold">{pages.length}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Pages Crawled</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{pages.filter((p) => p.indexable).length}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Indexable</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{pages.filter((p) => p.redirect_count > 0).length}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Redirected</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{pages.filter((p) => !p.robots_allowed).length}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Blocked by Robots</div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead>
                <tr className="text-left text-muted border-b border-border">
                  <th className="py-2 pr-4 font-normal">URL</th>
                  <th className="py-2 pr-4 font-normal">Status</th>
                  <th className="py-2 pr-4 font-normal">Title</th>
                  <th className="py-2 pr-4 font-normal">Indexable</th>
                  <th className="py-2 pr-4 font-normal">Words</th>
                  <th className="py-2 pr-4 font-normal">Depth</th>
                  <th className="py-2 pr-4 font-normal">PageRank</th>
                  <th className="py-2 pr-4 font-normal">Response</th>
                  <th className="py-2 pr-4 font-normal">Redirects</th>
                  <th className="py-2 pr-4 font-normal">Robots</th>
                  <th className="py-2 pr-4 font-normal">Sitemap</th>
                </tr>
              </thead>
              <tbody>
                {pages.map((p) => (
                  <tr key={p.id} className="border-b border-border/50 hover:bg-white/5">
                    <td className="py-2.5 pr-4 max-w-xs truncate" title={p.url}>{p.url}</td>
                    <td className="py-2.5 pr-4"><StatusBadge code={p.status_code} /></td>
                    <td className="py-2.5 pr-4 max-w-xs truncate text-muted" title={p.title ?? ""}>{p.title || "—"}</td>
                    <td className="py-2.5 pr-4">{p.indexable ? "Yes" : <span className="text-yellow-400">No</span>}</td>
                    <td className="py-2.5 pr-4">{p.word_count ?? "—"}</td>
                    <td className="py-2.5 pr-4">{p.crawl_depth}</td>
                    <td className="py-2.5 pr-4">{p.internal_pagerank !== null ? p.internal_pagerank.toFixed(3) : "—"}</td>
                    <td className="py-2.5 pr-4">{p.response_ms !== null ? `${p.response_ms}ms` : "—"}</td>
                    <td className="py-2.5 pr-4">{p.redirect_count}</td>
                    <td className="py-2.5 pr-4">{p.robots_allowed ? "Allowed" : <span className="text-red-400">Blocked</span>}</td>
                    <td className="py-2.5 pr-4">{p.from_sitemap ? "Yes" : "No"}</td>
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
