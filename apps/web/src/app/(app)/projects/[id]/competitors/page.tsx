"use client";

import { useEffect, useState } from "react";
import { use as usePromise } from "react";
import Link from "next/link";
import { apiDelete, apiGet, apiPost, ApiError } from "@/lib/api";
import type { Competitor, CompetitorComparison, CompetitorMatrix as Matrix, ContentGap } from "@/lib/api";
import { CompetitorMatrix } from "@/components/CompetitorMatrix";

const SCORE_LABELS: Record<string, string> = {
  spy_score: "Overall", seo_score: "SEO", aeo_score: "AEO", geo_score: "GEO",
  technical_score: "Technical", onpage_score: "On-page",
  content_score: "Content", performance_score: "Performance",
};

export default function CompetitorsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = usePromise(params);
  const [competitors, setCompetitors] = useState<Competitor[] | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [comparison, setComparison] = useState<CompetitorComparison | null>(null);
  const [gap, setGap] = useState<ContentGap | null>(null);
  const [matrix, setMatrix] = useState<Matrix | null>(null);

  async function load() {
    try {
      const [list, built] = await Promise.all([
        apiGet<Competitor[]>(`projects/${id}/competitors`),
        apiGet<Matrix>(`projects/${id}/competitors/matrix`).catch(() => null),
      ]);
      setCompetitors(list);
      setMatrix(built);
    } catch {
      setCompetitors([]);
    }
  }

  useEffect(() => {
    // load() only sets state after its own await resolves (a plain
    // fetch-on-mount), not synchronously within this effect body.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    const interval = setInterval(load, 4000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function addCompetitor() {
    if (!name.trim() || !url.trim()) return;
    setError(null);
    setAdding(true);
    try {
      await apiPost(`projects/${id}/competitors`, { name: name.trim(), url: url.trim() });
      setName("");
      setUrl("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add that competitor.");
    } finally {
      setAdding(false);
    }
  }

  async function removeCompetitor(competitorId: string) {
    await apiDelete(`projects/${id}/competitors/${competitorId}`);
    await load();
  }

  async function refreshCompetitor(competitorId: string) {
    await apiPost(`projects/${id}/competitors/${competitorId}/refresh`);
    await load();
  }

  async function viewDetails(competitorId: string) {
    if (expanded === competitorId) {
      setExpanded(null);
      setComparison(null);
      setGap(null);
      return;
    }
    setExpanded(competitorId);
    setComparison(null);
    setGap(null);
    const [comp, contentGap] = await Promise.all([
      apiGet<CompetitorComparison>(`projects/${id}/competitors/${competitorId}/compare`),
      apiGet<ContentGap>(`projects/${id}/competitors/${competitorId}/content-gap`),
    ]);
    setComparison(comp);
    setGap(contentGap);
  }

  return (
    <div className="p-8 max-w-4xl">
      <Link href={`/projects/${id}`} className="text-sm text-muted hover:text-accent">← Back to project</Link>
      <h1 className="text-2xl font-semibold mt-2 mb-1">Competitors</h1>
      <p className="text-muted text-sm mb-8">
        Runs a real (lighter) crawl of each competitor and scores it with the same engine as your own audits —
        this doesn&apos;t use an audit credit.
      </p>

      <div className="card p-4 mb-8 space-y-3">
        <div className="flex gap-3">
          <input className="input flex-1" placeholder="Competitor name" value={name} onChange={(e) => setName(e.target.value)} />
          <input className="input flex-1" placeholder="https://competitor.com" value={url} onChange={(e) => setUrl(e.target.value)} />
          <button onClick={addCompetitor} disabled={adding} className="btn-primary shrink-0">
            {adding ? "Adding…" : "Add"}
          </button>
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>

      {matrix && (
        <div className="mb-10">
          <CompetitorMatrix matrix={matrix} />
        </div>
      )}

      {!competitors ? (
        <div className="card p-6 text-muted text-sm">Loading…</div>
      ) : competitors.length === 0 ? (
        <div className="card p-8 text-center text-muted">No competitors added yet.</div>
      ) : (
        <>
        <h2 className="text-lg font-semibold mb-3">Each competitor</h2>
        <div className="space-y-3">
          {competitors.map((c) => (
            <div key={c.id} className="card p-4">
              <div className="flex items-center justify-between gap-4">
                <button onClick={() => viewDetails(c.id)} className="text-left flex-1 min-w-0">
                  <div className="font-medium">{c.name}</div>
                  <div className="text-xs text-muted mt-1">{c.domain}</div>
                </button>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-xs text-muted uppercase">{c.status}</span>
                  {c.spy_score !== null && <span className="text-lg font-bold text-accent">{c.spy_score}</span>}
                  <button
                    onClick={() => refreshCompetitor(c.id)}
                    disabled={c.status === "CRAWLING"}
                    className="btn-secondary text-xs px-2 py-1"
                  >
                    {c.status === "CRAWLING" ? "Crawling…" : "Refresh"}
                  </button>
                  <button onClick={() => removeCompetitor(c.id)} className="text-xs text-muted hover:text-red-400">
                    Remove
                  </button>
                </div>
              </div>
              {c.failure_message && <p className="text-xs text-red-400 mt-2">{c.failure_message}</p>}

              {expanded === c.id && (
                <div className="mt-4 pt-4 border-t border-border space-y-6">
                  <div>
                    <h3 className="text-sm font-semibold mb-2">Score Comparison</h3>
                    {!comparison ? (
                      <p className="text-sm text-muted">Loading…</p>
                    ) : (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {comparison.comparisons.map((row) => (
                          <div key={row.field} className="text-center">
                            <div className="text-xs text-muted uppercase">{SCORE_LABELS[row.field] ?? row.field}</div>
                            <div className="text-sm mt-1">
                              {row.your_score ?? "—"} <span className="text-muted">vs</span> {row.competitor_score ?? "—"}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold mb-2">Content Gap</h3>
                    {!gap ? (
                      <p className="text-sm text-muted">Loading…</p>
                    ) : !gap.has_data ? (
                      <p className="text-sm text-muted">{gap.reason}</p>
                    ) : gap.gap_terms.length === 0 ? (
                      <p className="text-sm text-muted">No gap terms found — your content covers the same topics.</p>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {gap.gap_terms.map((term) => (
                          <span key={term} className="text-xs border border-border rounded-full px-2 py-1">{term}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        </>
      )}
    </div>
  );
}
