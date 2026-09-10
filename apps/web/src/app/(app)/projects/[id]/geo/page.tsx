import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import { getLatestCompletedAudit } from "@/lib/latestAudit";
import type { Project } from "@/lib/api";

function Pct({ value }: { value: number | null | undefined }) {
  if (value === undefined || value === null) return <span className="text-muted">—</span>;
  return <span>{value.toFixed(0)}%</span>;
}

export default async function GeoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [project, audit] = await Promise.all([
    serverApiGet<Project>(`projects/${id}`),
    getLatestCompletedAudit(id),
  ]);

  if (!project) {
    return <div className="p-8 text-muted">Project not found.</div>;
  }

  const geo = audit?.evidence?.geo;

  return (
    <div className="p-8 max-w-4xl">
      <Link href={`/projects/${id}`} className="text-sm text-muted hover:text-accent">← Back to project</Link>
      <h1 className="text-2xl font-semibold mt-2 mb-1">GEO</h1>
      <p className="text-muted text-sm mb-8">
        {project.canonical_origin} — Generative Engine Optimization: how clearly this site&apos;s entity identity is
        described for AI systems to recognize, disambiguate and cite consistently.
      </p>

      {!audit ? (
        <div className="card p-8 text-center text-muted">
          No completed audit yet. Run an audit from the project page to see GEO readiness.
        </div>
      ) : !geo || geo.reason ? (
        <div className="card p-8 text-center text-muted">
          {geo?.reason ?? "GEO evidence is not available for this audit."}
        </div>
      ) : (
        <>
          <div className="card p-6 mb-8 flex items-center gap-6">
            <div className="text-4xl font-bold">{audit.geo_score !== null ? audit.geo_score.toFixed(0) : "—"}</div>
            <div>
              <div className="text-sm font-medium">GEO Score</div>
              <div className="text-xs text-muted mt-1">
                Based on {audit.evidence.total_pages_scored ?? "—"} scored pages of {audit.evidence.urls_processed ?? "—"} crawled.
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="card p-5">
              <div className="text-2xl font-bold">{geo.has_organization_schema ? "Yes" : "No"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Organization Schema Present</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">{geo.has_person_or_product_schema ? "Yes" : "No"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Person/Product Schema Present</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold"><Pct value={geo.schema_coverage_pct} /></div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Schema Coverage</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold"><Pct value={geo.citation_readiness_pct} /></div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Citation Readiness</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold"><Pct value={geo.org_field_completeness_pct} /></div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Org Field Completeness</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold"><Pct value={geo.entity_name_consistency_pct} /></div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Entity Name Consistency</div>
            </div>
          </div>

          <div className="card p-6 text-sm text-muted">
            GEO evaluates how unambiguously this site&apos;s entity (organization, person, or product) is described
            via structured data — a prerequisite for generative engines to recognize and cite it consistently. Spy
            does not guarantee inclusion in any AI-generated answer.
          </div>
        </>
      )}
    </div>
  );
}
