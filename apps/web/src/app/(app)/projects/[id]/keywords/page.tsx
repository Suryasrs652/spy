"use client";

import { useEffect, useState } from "react";
import { use as usePromise } from "react";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { GscQueryRow } from "@/lib/api";
import { useGscProperty } from "../useGscProperty";
import { GscPropertyPicker } from "../GscPropertyPicker";

const DAY_OPTIONS = [7, 28, 90];

export default function KeywordsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = usePromise(params);
  const { properties, property, unlinked, loading, linking, error, linkProperty } = useGscProperty(id);
  const [days, setDays] = useState(28);
  const [rows, setRows] = useState<GscQueryRow[] | null>(null);

  useEffect(() => {
    if (!property) return;
    let cancelled = false;
    apiGet<GscQueryRow[]>(`gsc/queries?property_id=${property.id}&days=${days}`)
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      });
    return () => {
      cancelled = true;
    };
  }, [property, days]);

  return (
    <div className="p-8 max-w-5xl">
      <Link href={`/projects/${id}`} className="text-sm text-muted hover:text-accent">← Back to project</Link>
      <h1 className="text-2xl font-semibold mt-2 mb-1">Keywords</h1>
      <p className="text-muted text-sm mb-8">
        Queries this site actually ranks for, pulled straight from Google Search Console — not an estimated
        keyword universe.
      </p>

      {loading ? (
        <div className="card p-6 text-muted text-sm">Loading…</div>
      ) : !property ? (
        <GscPropertyPicker
          allProperties={properties ?? []}
          unlinked={unlinked}
          linking={linking}
          error={error}
          onLink={linkProperty}
        />
      ) : (
        <>
          <div className="flex items-center gap-2 mb-6">
            {DAY_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`text-xs px-3 py-1.5 rounded border ${
                  d === days ? "border-accent text-accent" : "border-border text-muted"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>

          {rows === null ? (
            <div className="card p-6 text-muted text-sm">Loading queries…</div>
          ) : rows.length === 0 ? (
            <div className="card p-8 text-center text-muted">
              No query data for {property.site_url} in the last {days} days. Try a wider window, or sync from
              Settings if this property was just connected.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted border-b border-border">
                  <th className="py-2 pr-4 font-normal">Query</th>
                  <th className="py-2 pr-4 font-normal">Clicks</th>
                  <th className="py-2 pr-4 font-normal">Impressions</th>
                  <th className="py-2 pr-4 font-normal">CTR</th>
                  <th className="py-2 pr-4 font-normal">Avg. Position</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.query} className="border-b border-border/50 hover:bg-white/5">
                    <td className="py-2.5 pr-4">{r.query}</td>
                    <td className="py-2.5 pr-4">{r.clicks}</td>
                    <td className="py-2.5 pr-4">{r.impressions}</td>
                    <td className="py-2.5 pr-4">{(r.ctr * 100).toFixed(1)}%</td>
                    <td className="py-2.5 pr-4">{r.position.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
