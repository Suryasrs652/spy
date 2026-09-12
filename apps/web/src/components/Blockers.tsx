import type { AuditSummary } from "@/lib/api";

const BUCKETS = [
  { key: "critical", label: "Critical issues", tone: "text-red-400" },
  { key: "high", label: "High priority", tone: "text-orange-400" },
  { key: "medium", label: "Medium priority", tone: "text-yellow-400" },
  { key: "opportunities", label: "Opportunities", tone: "text-blue-400" },
] as const;

const EFFORT_TONE: Record<string, string> = {
  Low: "border-green-600 text-green-500",
  Medium: "border-yellow-600 text-yellow-500",
  High: "border-orange-600 text-orange-500",
};

export function IssueCounts({ summary }: { summary: AuditSummary }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {BUCKETS.map(({ key, label, tone }) => {
        const bucket = summary.issue_counts[key];
        return (
          <div key={key} className="card p-5">
            <div className={`text-3xl font-bold ${bucket.issues > 0 ? tone : "text-muted"}`}>
              {bucket.issues}
            </div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">{label}</div>
            <div className="text-xs text-muted mt-1">
              {bucket.pages === 0
                ? "no pages affected"
                : `across ${bucket.pages} page${bucket.pages === 1 ? "" : "s"}`}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * The five things costing the most score.
 *
 * Deliberately not the same list as the growth plan below it. That one is
 * ordered by leverage — what to do first, cheapest useful thing first. This
 * one is ordered by magnitude, and draws on the score components no rule
 * watches, which is where a site's real constraint usually turns out to be.
 */
export function TopBlockers({ summary }: { summary: AuditSummary }) {
  if (summary.blockers.length === 0) {
    return (
      <div className="card p-6 text-sm text-muted">
        Nothing is holding this site&rsquo;s score down by a material amount. That is a result, not a
        missing one.
      </div>
    );
  }

  return (
    <ol className="space-y-3">
      {summary.blockers.map((blocker, i) => (
        <li key={blocker.key} className="card p-4">
          <div className="flex items-baseline gap-3">
            <span className="text-muted text-sm tabular-nums shrink-0">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="font-medium">{blocker.title}</span>
                <span
                  className={`text-[10px] uppercase font-semibold rounded px-2 py-0.5 border ${
                    EFFORT_TONE[blocker.effort_label] ?? "border-border text-muted"
                  }`}
                >
                  {blocker.effort_label} effort
                </span>
                <span className="text-xs text-muted">
                  worth {blocker.points_recoverable.toFixed(1)} pts
                  {blocker.rule_id && ` · ${blocker.rule_id}`}
                </span>
              </div>
              <p className="text-sm text-muted mt-2">{blocker.detail}</p>
              <p className="text-sm mt-2">
                <strong>Do:</strong> {blocker.what_to_do}
              </p>
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
