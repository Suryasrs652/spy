import type { ScoreSection } from "@/lib/api";

// Terms that are acronyms, not words. Without this, `faq_implementation`
// renders as "Faq implementation".
const ACRONYMS: Record<string, string> = {
  faq: "FAQ", ai: "AI", acrs: "ACRS", seo: "SEO", aeo: "AEO", geo: "GEO", html: "HTML",
};

export function titleCase(key: string): string {
  return key
    .split("_")
    .map((word, i) => ACRONYMS[word] ?? (i === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(" ");
}

/**
 * Renders the components of a sub-score.
 *
 * The rule the whole engine turns on: `null` is *not measured*, and renders
 * as those words. It must never render as 0, or as an empty bar, or be
 * quietly skipped — a reader cannot tell "we didn't look" from "you failed"
 * unless the page says which.
 */
export function SubScores({
  title,
  section,
  emptyLabel = "Not computed.",
}: {
  title: string;
  section?: ScoreSection;
  emptyLabel?: string;
}) {
  const components = section?.components;

  if (!components || Object.keys(components).length === 0) {
    return (
      <div className="card p-4">
        <h3 className="font-medium mb-2">{title}</h3>
        <p className="text-sm text-muted">{section?.reason ?? emptyLabel}</p>
      </div>
    );
  }

  return (
    <div className="card p-4">
      <h3 className="font-medium mb-3">{title}</h3>
      <div className="space-y-1.5">
        {Object.entries(components).map(([key, value]) => (
          <div key={key} className="flex items-center gap-3 text-sm">
            <span className="w-44 shrink-0 text-muted">{titleCase(key)}</span>
            <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
              {value !== null && (
                <div
                  className="h-full bg-accent rounded-full"
                  style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
                />
              )}
            </div>
            <span
              className={`w-28 text-right tabular-nums ${value === null ? "text-muted text-xs" : ""}`}
            >
              {value === null ? "Not measured" : value}
            </span>
          </div>
        ))}
      </div>
      {section?.not_measured && section.not_measured.length > 0 && (
        <ul className="mt-3 space-y-1">
          {section.not_measured.map((reason) => (
            <li key={reason} className="text-xs text-muted">
              — {reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
