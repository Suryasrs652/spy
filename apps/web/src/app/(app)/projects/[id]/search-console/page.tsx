"use client";

import { useEffect, useState } from "react";
import { use as usePromise } from "react";
import Link from "next/link";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import type { GscOpportunities, GscPerformanceSummary, GscQueryRow } from "@/lib/api";
import { useGscProperty } from "../useGscProperty";
import { GscPropertyPicker } from "../GscPropertyPicker";

const DAY_OPTIONS = [7, 28, 90];

type Tab = "queries" | "pages" | "opportunities";

export default function SearchConsolePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = usePromise(params);
  const { properties, property, unlinked, loading, linking, error, linkProperty } = useGscProperty(id);
  const [days, setDays] = useState(28);
  const [tab, setTab] = useState<Tab>("queries");
  const [summary, setSummary] = useState<GscPerformanceSummary | null>(null);
  const [queries, setQueries] = useState<GscQueryRow[] | null>(null);
  const [pages, setPages] = useState<GscQueryRow[] | null>(null);
  const [opportunities, setOpportunities] = useState<GscOpportunities | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!property) return;
    let cancelled = false;
    Promise.all([
      apiGet<GscPerformanceSummary>(`gsc/performance?property_id=${property.id}&days=${days}`),
      apiGet<GscQueryRow[]>(`gsc/queries?property_id=${property.id}&days=${days}`),
      apiGet<GscQueryRow[]>(`gsc/pages?property_id=${property.id}&days=${days}`),
      apiGet<GscOpportunities>(`gsc/opportunities?property_id=${property.id}`),
    ])
      .then(([s, q, p, o]) => {
        if (cancelled) return;
        setSummary(s);
        setQueries(q);
        setPages(p);
        setOpportunities(o);
      })
      .catch(() => {
        if (cancelled) return;
        setSummary(null);
        setQueries([]);
        setPages([]);
        setOpportunities(null);
      });
    return () => {
      cancelled = true;
    };
  }, [property, days]);

  async function syncNow() {
    setSyncing(true);
    setSyncMsg(null);
    try {
      const result = await apiPost<{ synced: number; failed: number; total: number }>("gsc/sync");
      setSyncMsg(`Synced ${result.synced}/${result.total} properties.`);
    } catch (err) {
      setSyncMsg(err instanceof ApiError ? err.message : "Sync failed.");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="p-8 max-w-6xl">
      <Link href={`/projects/${id}`} className="text-sm text-muted hover:text-accent">← Back to project</Link>
      <h1 className="text-2xl font-semibold mt-2 mb-1">Search Console</h1>
      <p className="text-muted text-sm mb-8">
        Real performance data and opportunity analysis from Google Search Console — striking-distance keywords,
        low-CTR pages, and rank movement, all computed off data you&apos;ve synced.
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
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
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
            <div className="flex items-center gap-3">
              {syncMsg && <span className="text-xs text-muted">{syncMsg}</span>}
              <button onClick={syncNow} disabled={syncing} className="btn-secondary text-xs px-3 py-1.5">
                {syncing ? "Syncing…" : "Sync Now"}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4 mb-8">
            <div className="card p-5">
              <div className="text-2xl font-bold">{summary?.clicks ?? "—"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Clicks</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{summary?.impressions ?? "—"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Impressions</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{summary ? `${(summary.ctr * 100).toFixed(1)}%` : "—"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Avg. CTR</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{summary?.average_position?.toFixed(1) ?? "—"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Avg. Position</div>
            </div>
          </div>

          <div className="flex gap-4 mb-4 text-sm border-b border-border">
            {(["queries", "pages", "opportunities"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`pb-2 capitalize ${tab === t ? "text-accent border-b-2 border-accent" : "text-muted"}`}
              >
                {t}
              </button>
            ))}
          </div>

          {tab === "queries" && <QueryTable rows={queries} labelCol="Query" field="query" />}
          {tab === "pages" && <QueryTable rows={pages} labelCol="Page" field="page" />}
          {tab === "opportunities" && <OpportunitiesPanel data={opportunities} />}
        </>
      )}
    </div>
  );
}

function QueryTable({ rows, labelCol, field }: { rows: GscQueryRow[] | null; labelCol: string; field: "query" | "page" }) {
  if (rows === null) return <div className="card p-6 text-muted text-sm">Loading…</div>;
  if (rows.length === 0) return <div className="card p-8 text-center text-muted">No data for this period.</div>;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-muted border-b border-border">
          <th className="py-2 pr-4 font-normal">{labelCol}</th>
          <th className="py-2 pr-4 font-normal">Clicks</th>
          <th className="py-2 pr-4 font-normal">Impressions</th>
          <th className="py-2 pr-4 font-normal">CTR</th>
          <th className="py-2 pr-4 font-normal">Avg. Position</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r[field]}-${i}`} className="border-b border-border/50 hover:bg-white/5">
            <td className="py-2.5 pr-4 max-w-md truncate">{r[field]}</td>
            <td className="py-2.5 pr-4">{r.clicks}</td>
            <td className="py-2.5 pr-4">{r.impressions}</td>
            <td className="py-2.5 pr-4">{(r.ctr * 100).toFixed(1)}%</td>
            <td className="py-2.5 pr-4">{r.position.toFixed(1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Section({ title, empty, children }: { title: string; empty: boolean; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <h3 className="text-sm font-semibold mb-3">{title}</h3>
      {empty ? <div className="card p-4 text-sm text-muted">Nothing here for this property right now.</div> : children}
    </div>
  );
}

function OpportunitiesPanel({ data }: { data: GscOpportunities | null }) {
  if (!data) return <div className="card p-8 text-center text-muted">No opportunity data available.</div>;

  return (
    <div>
      <p className="text-xs text-muted mb-6">
        Comparing {data.period.current[0]} → {data.period.current[1]} against the prior period{" "}
        {data.period.previous[0]} → {data.period.previous[1]}.
      </p>

      <Section title="Striking Distance Keywords (positions 4–20)" empty={data.striking_distance_keywords.length === 0}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="py-2 pr-4 font-normal">Query</th>
              <th className="py-2 pr-4 font-normal">Position</th>
              <th className="py-2 pr-4 font-normal">Clicks</th>
              <th className="py-2 pr-4 font-normal">Impressions</th>
            </tr>
          </thead>
          <tbody>
            {data.striking_distance_keywords.map((k) => (
              <tr key={k.query} className="border-b border-border/50">
                <td className="py-2 pr-4">{k.query}</td>
                <td className="py-2 pr-4">{k.position.toFixed(1)}</td>
                <td className="py-2 pr-4">{k.clicks}</td>
                <td className="py-2 pr-4">{k.impressions}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Low CTR Opportunities" empty={data.low_ctr_opportunities.length === 0}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="py-2 pr-4 font-normal">Query</th>
              <th className="py-2 pr-4 font-normal">Actual CTR</th>
              <th className="py-2 pr-4 font-normal">Expected CTR</th>
              <th className="py-2 pr-4 font-normal">Position</th>
            </tr>
          </thead>
          <tbody>
            {data.low_ctr_opportunities.map((k) => (
              <tr key={k.query} className="border-b border-border/50">
                <td className="py-2 pr-4">{k.query}</td>
                <td className="py-2 pr-4">{k.actual_ctr !== undefined ? `${(k.actual_ctr * 100).toFixed(1)}%` : "—"}</td>
                <td className="py-2 pr-4">{k.spy_expected_ctr !== undefined ? `${(k.spy_expected_ctr * 100).toFixed(1)}%` : "—"}</td>
                <td className="py-2 pr-4">{k.position.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="High Impressions, No Clicks" empty={data.high_impressions_no_clicks.length === 0}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted border-b border-border">
              <th className="py-2 pr-4 font-normal">Query</th>
              <th className="py-2 pr-4 font-normal">Impressions</th>
              <th className="py-2 pr-4 font-normal">Position</th>
            </tr>
          </thead>
          <tbody>
            {data.high_impressions_no_clicks.map((k) => (
              <tr key={k.query} className="border-b border-border/50">
                <td className="py-2 pr-4">{k.query}</td>
                <td className="py-2 pr-4">{k.impressions}</td>
                <td className="py-2 pr-4">{k.position.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <div className="grid grid-cols-2 gap-8">
        <Section title="Rising Keywords" empty={data.rising_keywords.length === 0}>
          <ChangeList rows={data.rising_keywords} field="query" positive />
        </Section>
        <Section title="Declining Keywords" empty={data.declining_keywords.length === 0}>
          <ChangeList rows={data.declining_keywords} field="query" positive={false} />
        </Section>
        <Section title="Rising Pages" empty={data.rising_pages.length === 0}>
          <ChangeList rows={data.rising_pages} field="page" positive />
        </Section>
        <Section title="Declining Pages" empty={data.declining_pages.length === 0}>
          <ChangeList rows={data.declining_pages} field="page" positive={false} />
        </Section>
        <Section title="Position Gains" empty={data.position_gains.length === 0}>
          <PositionList rows={data.position_gains} positive />
        </Section>
        <Section title="Position Losses" empty={data.position_losses.length === 0}>
          <PositionList rows={data.position_losses} positive={false} />
        </Section>
      </div>

      <Section title="Keyword Cannibalization" empty={data.keyword_cannibalization.length === 0}>
        <div className="space-y-3">
          {data.keyword_cannibalization.map((c) => (
            <div key={c.query} className="card p-4">
              <div className="text-sm font-medium mb-2">{c.query}</div>
              <div className="space-y-1">
                {c.competing_pages.map((p) => (
                  <div key={p.page} className="flex justify-between text-xs text-muted">
                    <span className="truncate max-w-md">{p.page}</span>
                    <span>{p.clicks} clicks · {p.impressions} impressions</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

function ChangeList({
  rows, field, positive,
}: {
  rows: { query?: string; page?: string; current_clicks: number; previous_clicks: number; delta: number; pct_change: number }[];
  field: "query" | "page";
  positive: boolean;
}) {
  return (
    <div className="space-y-1.5">
      {rows.map((r, i) => (
        <div key={i} className="flex justify-between text-sm">
          <span className="truncate max-w-[60%]">{r[field]}</span>
          <span className={positive ? "text-green-400" : "text-red-400"}>
            {r.previous_clicks} → {r.current_clicks} ({r.pct_change > 0 ? "+" : ""}{(r.pct_change * 100).toFixed(0)}%)
          </span>
        </div>
      ))}
    </div>
  );
}

function PositionList({
  rows, positive,
}: {
  rows: { query: string; current_position: number; previous_position: number; delta: number }[];
  positive: boolean;
}) {
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.query} className="flex justify-between text-sm">
          <span className="truncate max-w-[60%]">{r.query}</span>
          <span className={positive ? "text-green-400" : "text-red-400"}>
            {r.previous_position.toFixed(1)} → {r.current_position.toFixed(1)}
          </span>
        </div>
      ))}
    </div>
  );
}
