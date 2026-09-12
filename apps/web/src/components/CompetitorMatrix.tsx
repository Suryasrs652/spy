"use client";

import type { CompetitorMatrix as Matrix } from "@/lib/api";

/**
 * The side-by-side table and the signals behind it.
 *
 * The heading over the advantages says "Where they are ahead of you", not
 * "why they outrank you". Spy reads markup and prose; it has no ranking data
 * for a competitor's site and cannot attribute a search position to a cause.
 * What it can say — and what is actually useful — is exactly which measured
 * signals differ and by how much.
 */
export function CompetitorMatrix({ matrix }: { matrix: Matrix }) {
  if (!matrix.has_data) {
    return <div className="card p-8 text-center text-muted text-sm">{matrix.reason}</div>;
  }

  const rivals = matrix.competitors;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold mb-3">Matrix</h2>
        <div className="card p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left font-normal text-muted py-3 px-4">Factor</th>
                <th className="text-right font-medium py-3 px-4 whitespace-nowrap">Your site</th>
                {rivals.map((c) => (
                  <th key={c.id} className="text-right font-normal text-muted py-3 px-4 whitespace-nowrap">
                    {c.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.factors.map((factor) => (
                <tr key={factor.key} className="border-b border-border last:border-0">
                  <td className="py-3 px-4 text-muted whitespace-nowrap">{factor.label}</td>
                  <td
                    className={`py-3 px-4 text-right tabular-nums font-medium ${
                      factor.gap_to_best !== null && factor.gap_to_best < 0 ? "text-orange-400" : ""
                    }`}
                  >
                    {factor.your_score ?? <span className="text-muted text-xs">Not measured</span>}
                  </td>
                  {rivals.map((c) => {
                    const value = factor.competitor_scores[c.id];
                    const isBest = factor.best_competitor_id === c.id;
                    return (
                      <td
                        key={c.id}
                        className={`py-3 px-4 text-right tabular-nums ${isBest ? "font-medium" : "text-muted"}`}
                      >
                        {value === null || value === undefined ? (
                          <span className="text-muted text-xs">Not measured</span>
                        ) : (
                          value
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {matrix.advantages.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-1">Where they are ahead of you</h2>
          <p className="text-xs text-muted mb-3">
            Measured differences in on-page evidence, biggest first. Spy has no ranking data for a
            competitor&rsquo;s site, so these are not an explanation of anyone&rsquo;s search position — they are
            the specific signals the two sites differ on, and what to do about each.
          </p>
          <ol className="space-y-3">
            {matrix.advantages.map((advantage, i) => (
              <li key={advantage.key} className="card p-4">
                <div className="flex items-baseline gap-3">
                  <span className="text-muted text-sm tabular-nums">{i + 1}</span>
                  <div className="flex-1">
                    <div className="flex items-baseline gap-3 flex-wrap">
                      <span className="font-medium">{advantage.label}</span>
                      <span className="text-xs text-muted">
                        {advantage.gap.toFixed(0)} point gap
                        {advantage.competitors_ahead > 1 &&
                          ` · ${advantage.competitors_ahead} competitors ahead`}
                      </span>
                    </div>
                    <p className="text-sm mt-2">{advantage.finding}</p>
                    <p className="text-sm text-muted mt-2">
                      <strong className="text-foreground">Do:</strong> {advantage.what_to_do}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {matrix.advantages.length === 0 && (
        <div className="card p-6 text-sm text-muted">
          No competitor leads you by enough on any measured signal to be worth acting on. That is a
          real result, not a missing one.
        </div>
      )}

      {matrix.size && (
        <div className="card p-4">
          <div className="font-medium text-sm">Site size</div>
          <p className="text-sm mt-2">{matrix.size.finding}</p>
          <p className="text-sm text-muted mt-2">
            <strong className="text-foreground">Do:</strong> {matrix.size.what_to_do}
          </p>
        </div>
      )}

      {matrix.not_comparable.length > 0 && (
        <div className="card p-4">
          <div className="font-medium text-sm">Left out of the matrix</div>
          <ul className="mt-2 space-y-1">
            {matrix.not_comparable.map((x) => (
              <li key={x.competitor_id} className="text-sm text-muted">
                <strong className="text-foreground">{x.name}</strong> — {x.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {matrix.methodology && <p className="text-xs text-muted">{matrix.methodology}</p>}
    </div>
  );
}
