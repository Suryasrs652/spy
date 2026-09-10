"use client";

import { useEffect, useState } from "react";
import { use as usePromise } from "react";
import Link from "next/link";
import { apiDelete, apiGet, apiPost, ApiError } from "@/lib/api";
import type { RankHistory, RankOverviewRow } from "@/lib/api";

export default function RankTrackerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = usePromise(params);
  const [rows, setRows] = useState<RankOverviewRow[] | null>(null);
  const [newKeyword, setNewKeyword] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [history, setHistory] = useState<RankHistory | null>(null);

  async function load() {
    try {
      const data = await apiGet<RankOverviewRow[]>(`projects/${id}/keywords`);
      setRows(data);
    } catch {
      setRows([]);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function addKeyword() {
    if (!newKeyword.trim()) return;
    setError(null);
    setAdding(true);
    try {
      await apiPost(`projects/${id}/keywords`, { keyword: newKeyword.trim() });
      setNewKeyword("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add that keyword.");
    } finally {
      setAdding(false);
    }
  }

  async function removeKeyword(keywordId: string) {
    await apiDelete(`projects/${id}/keywords/${keywordId}`);
    await load();
  }

  async function toggleHistory(row: RankOverviewRow) {
    if (expanded === row.id) {
      setExpanded(null);
      setHistory(null);
      return;
    }
    setExpanded(row.id);
    const data = await apiGet<RankHistory>(`projects/${id}/keywords/${encodeURIComponent(row.keyword)}/history`);
    setHistory(data);
  }

  return (
    <div className="p-8 max-w-4xl">
      <Link href={`/projects/${id}`} className="text-sm text-muted hover:text-accent">← Back to project</Link>
      <h1 className="text-2xl font-semibold mt-2 mb-1">Rank Tracker</h1>
      <p className="text-muted text-sm mb-8">
        Position history comes from Google Search Console data you&apos;ve already connected and synced — not a
        live SERP checker. A tracked keyword shows &quot;no data&quot; until your site has real GSC impressions
        for it.
      </p>

      <div className="card p-4 mb-8 flex items-center gap-3">
        <input
          className="input flex-1"
          placeholder="Add a keyword to track…"
          value={newKeyword}
          onChange={(e) => setNewKeyword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addKeyword()}
        />
        <button onClick={addKeyword} disabled={adding} className="btn-primary shrink-0">
          {adding ? "Adding…" : "Add"}
        </button>
      </div>
      {error && <p className="text-sm text-red-400 mb-4">{error}</p>}

      {!rows ? (
        <div className="card p-6 text-muted text-sm">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="card p-8 text-center text-muted">No keywords tracked yet — add one above.</div>
      ) : (
        <div className="space-y-2">
          {rows.map((row) => (
            <div key={row.id} className="card p-4">
              <div className="flex items-center justify-between gap-4">
                <button onClick={() => toggleHistory(row)} className="text-left flex-1 min-w-0">
                  <div className="font-medium truncate">{row.keyword}</div>
                  <div className="text-xs text-muted mt-1">
                    {row.has_data ? `Position ${row.current_position} (best: ${row.best_position})` : "No GSC data yet"}
                  </div>
                </button>
                <button onClick={() => removeKeyword(row.id)} className="text-xs text-muted hover:text-red-400 shrink-0">
                  Remove
                </button>
              </div>
              {expanded === row.id && history && (
                <div className="mt-3 pt-3 border-t border-border">
                  {!history.has_data ? (
                    <p className="text-sm text-muted">{history.reason}</p>
                  ) : (
                    <div className="space-y-1">
                      {history.history.map((point) => (
                        <div key={point.date} className="flex justify-between text-xs text-muted">
                          <span>{point.date}</span>
                          <span>
                            pos {point.position} · {point.clicks} clicks · {point.impressions} impressions
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
