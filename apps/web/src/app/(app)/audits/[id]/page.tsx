"use client";

import { useCallback, useEffect, useState } from "react";
import { use as usePromise } from "react";
import Link from "next/link";
import { apiGet, apiPost } from "@/lib/api";
import type { Audit, AuditIssue, AuditProgress, Recommendation } from "@/lib/api";
import { SubScores } from "@/components/SubScores";
import { CompareSelector } from "./CompareSelector";

// The three scores answer different questions, so they get their own row
// rather than sitting in a grid of eight equal-looking numbers.
const HEADLINE_CARDS: { key: keyof Audit; label: string; blurb: string }[] = [
  { key: "seo_score", label: "SEO", blurb: "Can a search engine crawl, index and rank it?" },
  { key: "aeo_score", label: "AEO", blurb: "Can an answer engine lift an answer out of it?" },
  { key: "geo_score", label: "GEO", blurb: "Can a generative system tell who wrote it?" },
];

// The seven components of the SEO score, with the weight each carries.
const SEO_CARDS: { key: keyof Audit; label: string; weight: string }[] = [
  { key: "technical_score", label: "Technical", weight: "25%" },
  { key: "onpage_score", label: "On-page", weight: "20%" },
  { key: "content_score", label: "Content", weight: "20%" },
  { key: "internal_links_score", label: "Internal links", weight: "10%" },
  { key: "structured_data_score", label: "Structured data", weight: "10%" },
  { key: "performance_score", label: "Performance", weight: "10%" },
  { key: "authority_score", label: "Authority", weight: "5%" },
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
    // refresh() only sets state after its own awaits resolve (a plain
    // fetch-on-mount), not synchronously within this effect body.
    // eslint-disable-next-line react-hooks/set-state-in-effect
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

      <div className="card p-6 mb-4 text-center">
        <div className={`text-5xl font-bold ${scoreBand(audit.spy_score)}`}>{audit.spy_score ?? "N/A"}</div>
        <div className="text-xs text-muted uppercase tracking-wide mt-2">Overall Digital Search Score</div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        {HEADLINE_CARDS.map(({ key, label, blurb }) => {
          const value = audit[key] as number | null;
          return (
            <div key={String(key)} className="card p-5 text-center">
              <div className={`text-3xl font-bold ${scoreBand(value)}`}>{value ?? "N/A"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">{label}</div>
              <div className="text-xs text-muted mt-2">{blurb}</div>
            </div>
          );
        })}
      </div>

      <h2 className="text-lg font-semibold mb-3 mt-8">SEO breakdown</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
        {SEO_CARDS.map(({ key, label, weight }) => {
          const value = audit[key] as number | null;
          return (
            <div key={String(key)} className="card p-5 text-center">
              <div className={`text-2xl font-bold ${scoreBand(value)}`}>{value ?? "N/A"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">{label}</div>
              <div className="text-[10px] text-muted mt-0.5">{weight} of SEO</div>
            </div>
          );
        })}
        <div className="card p-5 text-center">
          <div className={`text-2xl font-bold ${scoreBand(audit.acrs_score)}`}>{audit.acrs_score ?? "N/A"}</div>
          <div className="text-xs text-muted uppercase tracking-wide mt-1">ACRS</div>
          <div className="text-[10px] text-muted mt-0.5">reported separately</div>
        </div>
      </div>
      {audit.authority_score === null && (
        <p className="text-xs text-muted mb-10">
          Authority reads &ldquo;N/A&rdquo; because Spy&rsquo;s backlink index is built from its own crawls and has
          nothing for this domain yet — that is not measured, not zero. Its weight is spread across the
          other six components rather than counted as a failure.
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-10 mt-6">
        <SubScores title="AEO — answer engine readiness" section={audit.evidence?.aeo} />
        <SubScores title="GEO — generative engine readiness" section={audit.evidence?.geo} />
      </div>

      <CompareSelector auditId={audit.id} projectId={audit.project_id} />

      <h2 className="text-lg font-semibold mb-4">Issues ({issues?.length ?? 0})</h2>
      <div className="space-y-3 mb-10">
        {issues?.map((issue) => (
          <div key={issue.id} className="card p-4">
            <div className="flex items-center gap-3">
              <span className={`text-[10px] uppercase font-semibold text-white rounded px-2 py-0.5 ${SEV_COLOR[issue.severity]}`}>
                {issue.severity}
              </span>
              <span className="font-medium">{issue.title}</span>
              {issue.validated === true && (
                <span
                  className="text-[10px] uppercase font-semibold rounded px-2 py-0.5 border border-green-600 text-green-700"
                  title={issue.validation_note ?? "Checked against the live site and confirmed."}
                >
                  Verified
                </span>
              )}
              {issue.validated === false && (
                <span
                  className="text-[10px] uppercase font-semibold rounded px-2 py-0.5 border border-muted text-muted"
                  title={issue.validation_note ?? "Checked against the live site and did not hold up."}
                >
                  Not confirmed
                </span>
              )}
              {issue.validated === null && issue.confidence < 1 && (
                <span
                  className="text-[10px] uppercase font-semibold rounded px-2 py-0.5 border border-amber-500 text-amber-700"
                  title={`This rule infers the problem rather than observing it directly (${Math.round(
                    issue.confidence * 100
                  )}% confidence). Check a page before acting on it.`}
                >
                  Verify first
                </span>
              )}
              <span className="text-xs text-muted ml-auto">{issue.affected_count} page(s)</span>
            </div>
            <p className="text-sm text-muted mt-2">{issue.description}</p>
            <p className="text-sm mt-2"><strong>Fix:</strong> {issue.recommendation}</p>
            {issue.validated === false && issue.validation_note && (
              <p className="text-sm text-muted mt-2"><strong>Checked:</strong> {issue.validation_note}</p>
            )}
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
