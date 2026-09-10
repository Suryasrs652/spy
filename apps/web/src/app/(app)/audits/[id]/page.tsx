"use client";

import { useCallback, useEffect, useState } from "react";
import { use as usePromise } from "react";
import Link from "next/link";
import { apiGet, apiPost } from "@/lib/api";
import type { Audit, AuditIssue, AuditProgress, Recommendation } from "@/lib/api";

const SCORE_CARDS: { key: keyof Audit; label: string }[] = [
  { key: "spy_score", label: "Spy Score" },
  { key: "seo_score", label: "SEO" },
  { key: "technical_score", label: "Technical" },
  { key: "content_score", label: "Content" },
  { key: "performance_score", label: "Performance" },
  { key: "authority_score", label: "Authority" },
  { key: "aeo_score", label: "AEO" },
  { key: "geo_score", label: "GEO" },
];

function scoreBand(score: number | null): string {
  if (score === null) return "text-muted";
  if (score >= 90) return "text-green-400";
  if (score >= 75) return "text-blue-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-orange-400";
  return "text-red-400";
}

const SEV_COLOR: Record<string, string> = {
  CRITICAL: "bg-red-600", HIGH: "bg-orange-600", MEDIUM: "bg-yellow-600", LOW: "bg-blue-600", INFO: "bg-gray-600",
};

export default function AuditResultsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = usePromise(params);
  const [audit, setAudit] = useState<Audit | null>(null);
  const [progress, setProgress] = useState<AuditProgress | null>(null);
  const [issues, setIssues] = useState<AuditIssue[] | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isTerminal = audit && ["COMPLETED", "FAILED", "CANCELLED"].includes(audit.status);

  const refresh = useCallback(async () => {
    try {
      const [a, p] = await Promise.all([
        apiGet<Audit>(`audits/${id}`),
        apiGet<AuditProgress>(`audits/${id}/progress`),
      ]);
      setAudit(a);
      setProgress(p);
      if (a.status === "COMPLETED") {
        const [i, r] = await Promise.all([
          apiGet<AuditIssue[]>(`audits/${id}/issues`),
          apiGet<Recommendation[]>(`audits/${id}/recommendations`),
        ]);
        setIssues(i);
        setRecommendations(r);
      }
    } catch {
      setError("Couldn't load this audit.");
    }
  }, [id]);

  useEffect(() => {
    refresh();
    const interval = setInterval(() => {
      setAudit((current) => {
        if (current && ["COMPLETED", "FAILED", "CANCELLED"].includes(current.status)) {
          clearInterval(interval);
        } else {
          refresh();
        }
        return current;
      });
    }, 2000);
    return () => clearInterval(interval);
  }, [refresh]);

  async function downloadReport() {
    const result = await apiGet<{ url: string }>(`audits/${id}/report/download`);
    window.open(result.url, "_blank");
  }

  if (error) return <div className="p-8 text-red-400">{error}</div>;
  if (!audit) return <div className="p-8 text-muted">Loading…</div>;

  if (!isTerminal) {
    const pct = progress?.progress ?? 0;
    return (
      <div className="p-8 max-w-2xl">
        <h1 className="text-2xl font-semibold mb-2">Auditing your site…</h1>
        <p className="text-muted mb-6">{audit.status.replace(/_/g, " ").toLowerCase()}</p>
        <div className="card p-6">
          <div className="w-full bg-white/5 rounded-full h-2 mb-3">
            <div className="bg-accent h-2 rounded-full transition-all" style={{ width: `${pct}%` }} />
          </div>
          <div className="text-sm text-muted">
            {progress ? `${progress.urls_processed} / ${progress.urls_discovered} pages` : "Starting…"}
          </div>
        </div>
      </div>
    );
  }

  if (audit.status === "FAILED") {
    return (
      <div className="p-8 max-w-2xl">
        <h1 className="text-2xl font-semibold text-red-400 mb-2">Audit failed</h1>
        <p className="text-muted mb-1">{audit.failure_message}</p>
        <p className="text-xs text-muted">Code: {audit.failure_code}</p>
        <Link href="/dashboard" className="btn-secondary inline-block mt-6">Back to dashboard</Link>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Audit Results</h1>
          <p className="text-muted text-sm mt-1">
            Score version {audit.score_version} · Confidence {audit.confidence}%
          </p>
        </div>
        <button onClick={downloadReport} className="btn-secondary">Download PDF</button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
        {SCORE_CARDS.map(({ key, label }) => {
          const value = audit[key] as number | null;
          return (
            <div key={String(key)} className="card p-5 text-center">
              <div className={`text-3xl font-bold ${scoreBand(value)}`}>{value ?? "N/A"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">{label}</div>
            </div>
          );
        })}
      </div>

      <h2 className="text-lg font-semibold mb-4">Issues ({issues?.length ?? 0})</h2>
      <div className="space-y-3 mb-10">
        {issues?.map((issue) => (
          <div key={issue.id} className="card p-4">
            <div className="flex items-center gap-3">
              <span className={`text-[10px] uppercase font-semibold text-white rounded px-2 py-0.5 ${SEV_COLOR[issue.severity]}`}>
                {issue.severity}
              </span>
              <span className="font-medium">{issue.title}</span>
              <span className="text-xs text-muted ml-auto">{issue.affected_count} page(s)</span>
            </div>
            <p className="text-sm text-muted mt-2">{issue.description}</p>
            <p className="text-sm mt-2"><strong>Fix:</strong> {issue.recommendation}</p>
          </div>
        ))}
        {issues?.length === 0 && <div className="card p-6 text-muted text-sm">No issues found — great work.</div>}
      </div>

      <h2 className="text-lg font-semibold mb-4">90-Day Growth Plan</h2>
      <div className="space-y-2">
        {recommendations?.map((rec) => (
          <div key={rec.id} className="card p-4 flex items-center justify-between">
            <div>
              <div className="font-medium">{rec.title}</div>
              <div className="text-sm text-muted mt-1">{rec.description}</div>
            </div>
            <div className="text-right shrink-0 ml-4">
              <div className="text-lg font-bold text-accent">{rec.priority_score}</div>
              <div className="text-[10px] text-muted uppercase">{rec.group.replace(/_/g, " ")}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
