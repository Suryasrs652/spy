"use client";

import { useEffect, useState } from "react";
import { use as usePromise } from "react";
import Link from "next/link";
import { apiGet, ApiError } from "@/lib/api";
import type { AuditComparison, IssueSummary } from "@/lib/api";

const SCORE_LABELS: Record<string, string> = {
  spy_score: "Overall", seo_score: "SEO", aeo_score: "AEO", geo_score: "GEO",
  acrs_score: "ACRS", technical_score: "Technical", onpage_score: "On-page",
  content_score: "Content", internal_links_score: "Internal links",
  structured_data_score: "Structured data", performance_score: "Performance",
  authority_score: "Authority", confidence: "Confidence",
};

const SEV_COLOR: Record<string, string> = {
  CRITICAL: "bg-red-600", HIGH: "bg-orange-600", MEDIUM: "bg-yellow-600", LOW: "bg-blue-600", INFO: "bg-gray-600",
};

function DeltaBadge({ delta }: { delta: number | null }) {
  if (delta === null) return <span className="text-xs text-muted">—</span>;
  if (delta === 0) return <span className="text-xs text-muted">no change</span>;
  const up = delta > 0;
  return (
    <span className={`text-xs font-semibold ${up ? "text-green-400" : "text-red-400"}`}>
      {up ? "▲" : "▼"} {Math.abs(delta)}
    </span>
  );
}

function IssueList({ title, issues, tone }: { title: string; issues: IssueSummary[]; tone: string }) {
  return (
    <div>
      <h3 className={`text-sm font-semibold mb-3 ${tone}`}>{title} ({issues.length})</h3>
      {issues.length === 0 ? (
        <div className="card p-4 text-sm text-muted">None</div>
      ) : (
        <div className="space-y-2">
          {issues.map((issue) => (
            <div key={issue.rule_id} className="card p-3">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] uppercase font-semibold text-white rounded px-1.5 py-0.5 ${SEV_COLOR[issue.severity]}`}>
                  {issue.severity}
                </span>
                <span className="text-sm font-medium">{issue.title}</span>
              </div>
              <div className="text-xs text-muted mt-1">{issue.affected_count} page(s) affected</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AuditComparePage({ params }: { params: Promise<{ id: string; otherId: string }> }) {
  const { id, otherId } = usePromise(params);
  const [comparison, setComparison] = useState<AuditComparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<AuditComparison>(`audits/${id}/compare/${otherId}`)
      .then(setComparison)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load this comparison."));
  }, [id, otherId]);

  if (error) {
    return (
      <div className="p-8 max-w-2xl">
        <p className="text-red-400">{error}</p>
        <Link href={`/audits/${id}`} className="btn-secondary inline-block mt-6">Back to audit</Link>
      </div>
    );
  }
  if (!comparison) return <div className="p-8 text-muted">Loading…</div>;

  return (
    <div className="p-8 max-w-5xl">
      <Link href={`/audits/${id}`} className="text-sm text-muted hover:text-accent">← Back to audit</Link>
      <h1 className="text-2xl font-semibold mt-2 mb-1">Audit Comparison</h1>
      <p className="text-muted text-sm mb-8">
        {new Date(comparison.baseline_created_at).toLocaleDateString()} → {new Date(comparison.current_created_at).toLocaleDateString()}
        {" · "}{comparison.page_count_baseline} → {comparison.page_count_current} pages crawled
      </p>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-10">
        {Object.entries(comparison.score_deltas).map(([key, d]) => (
          <div key={key} className="card p-4">
            <div className="text-xs text-muted uppercase tracking-wide">{SCORE_LABELS[key] ?? key}</div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-2xl font-bold">{d.current ?? "N/A"}</span>
              <span className="text-xs text-muted">from {d.baseline ?? "N/A"}</span>
            </div>
            <DeltaBadge delta={d.delta} />
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <IssueList title="New Issues" issues={comparison.new_issues} tone="text-red-400" />
        <IssueList title="Resolved" issues={comparison.resolved_issues} tone="text-green-400" />
        <IssueList title="Still Present" issues={comparison.persisting_issues} tone="text-yellow-400" />
      </div>
    </div>
  );
}
