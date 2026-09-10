import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import type { Backlink, BacklinkSummary, Project } from "@/lib/api";

export default async function BacklinksPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [project, summary, backlinks] = await Promise.all([
    serverApiGet<Project>(`projects/${id}`),
    serverApiGet<BacklinkSummary>(`projects/${id}/backlinks/summary`),
    serverApiGet<Backlink[]>(`projects/${id}/backlinks`),
  ]);

  return (
    <div className="p-8 max-w-4xl">
      <Link href={`/projects/${id}`} className="text-sm text-muted hover:text-accent">← Back to project</Link>
      <h1 className="text-2xl font-semibold mt-2 mb-1">Backlinks</h1>
      <p className="text-muted text-sm mb-8">
        {project?.canonical_origin} — built from Spy&apos;s own crawl history, not a comprehensive web-scale
        backlink database. Coverage grows as more sites get audited.
      </p>

      <div className="grid grid-cols-3 gap-4 mb-10">
        <div className="card p-5">
          <div className="text-2xl font-bold">{summary?.total_backlinks ?? 0}</div>
          <div className="text-xs text-muted uppercase tracking-wide mt-1">Total Backlinks</div>
        </div>
        <div className="card p-5">
          <div className="text-2xl font-bold">{summary?.referring_domains ?? 0}</div>
          <div className="text-xs text-muted uppercase tracking-wide mt-1">Referring Domains</div>
        </div>
        <div className="card p-5">
          <div className="text-2xl font-bold">{summary?.followed_backlinks ?? 0}</div>
          <div className="text-xs text-muted uppercase tracking-wide mt-1">Followed</div>
        </div>
      </div>

      <h2 className="text-lg font-semibold mb-4">Discovered Links</h2>
      {!backlinks || backlinks.length === 0 ? (
        <div className="card p-8 text-center text-muted">
          No backlinks discovered yet. Spy learns about backlinks to your site whenever it crawls a site that
          happens to link here — coverage grows over time as more audits run across the platform.
        </div>
      ) : (
        <div className="space-y-2">
          {backlinks.map((b) => (
            <div key={b.id} className="card p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{b.source_url}</div>
                  <div className="text-xs text-muted mt-1">links to {b.target_url}</div>
                </div>
                {b.nofollow && (
                  <span className="text-[10px] uppercase tracking-wide border border-border rounded px-1.5 py-0.5 shrink-0">
                    nofollow
                  </span>
                )}
              </div>
              {b.anchor_text && <div className="text-xs text-muted mt-2">Anchor: &quot;{b.anchor_text}&quot;</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
