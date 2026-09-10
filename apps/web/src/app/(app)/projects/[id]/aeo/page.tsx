import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import { getLatestCompletedAudit } from "@/lib/latestAudit";
import type { Project } from "@/lib/api";

function Pct({ value }: { value: number | undefined }) {
  if (value === undefined || value === null) return <span className="text-muted">—</span>;
  return <span>{value.toFixed(0)}%</span>;
}

export default async function AeoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [project, audit] = await Promise.all([
    serverApiGet<Project>(`projects/${id}`),
    getLatestCompletedAudit(id),
  ]);

  if (!project) {
    return <div className="p-8 text-muted">Project not found.</div>;
  }

  const aeo = audit?.evidence?.aeo;

  return (
    <div className="p-8 max-w-4xl">
      <Link href={`/projects/${id}`} className="text-sm text-muted hover:text-accent">← Back to project</Link>
      <h1 className="text-2xl font-semibold mt-2 mb-1">AEO</h1>
      <p className="text-muted text-sm mb-8">
        {project.canonical_origin} — AI Engine Optimization: how well this site&apos;s content is structured for AI
        answer engines to parse and cite. This measures AI visibility readiness, not a placement guarantee.
      </p>

      {!audit ? (
        <div className="card p-8 text-center text-muted">
          No completed audit yet. Run an audit from the project page to see AEO readiness.
        </div>
      ) : !aeo || aeo.reason ? (
        <div className="card p-8 text-center text-muted">
          {aeo?.reason ?? "AEO evidence is not available for this audit."}
        </div>
      ) : (
        <>
          <div className="card p-6 mb-8 flex items-center gap-6">
            <div className="text-4xl font-bold">{audit.aeo_score !== null ? audit.aeo_score.toFixed(0) : "—"}</div>
            <div>
              <div className="text-sm font-medium">AEO Score</div>
              <div className="text-xs text-muted mt-1">
                Based on {audit.evidence.total_pages_scored ?? "—"} scored pages of {audit.evidence.urls_processed ?? "—"} crawled.
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="card p-5">
              <div className="text-2xl font-bold"><Pct value={aeo.schema_coverage_pct} /></div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Schema Coverage</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold"><Pct value={aeo.clean_heading_pct} /></div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Clean Heading Structure</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold"><Pct value={aeo.question_coverage_pct} /></div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Question Coverage</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold"><Pct value={aeo.structured_content_pct} /></div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Structured Content</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold"><Pct value={aeo.byline_coverage_pct} /></div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Byline Coverage</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{aeo.has_faq_schema ? "Yes" : "No"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">FAQ Schema Present</div>
            </div>
          </div>

          <div className="card p-6 text-sm text-muted">
            AEO evaluates structural signals AI answer engines use to extract and cite content: FAQ/Q&amp;A schema,
            clean heading hierarchies, question-style headings, structured lists/tables, and clear authorship. Spy
            does not guarantee inclusion in any AI-generated answer.
          </div>
        </>
      )}
    </div>
  );
}
