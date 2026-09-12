import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import { getLatestCompletedAudit } from "@/lib/latestAudit";
import type { Project } from "@/lib/api";
import { SubScores } from "@/components/SubScores";

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

          <SubScores title="The ten dimensions" section={geo} />

          <div className="grid grid-cols-2 gap-4 mt-4 mb-8">
            <div className="card p-5">
              <div className="text-2xl font-bold">{geo.has_organization_schema ? "Yes" : "No"}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Organization Schema Present</div>
            </div>
            <div className="card p-5">
              <div className="text-2xl font-bold">
                {geo.org_field_completeness_pct === null || geo.org_field_completeness_pct === undefined
                  ? <span className="text-muted text-base">Not measured</span>
                  : `${geo.org_field_completeness_pct.toFixed(0)}%`}
              </div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">Org Field Completeness</div>
            </div>
          </div>

          <div className="card p-6 text-sm text-muted">
            GEO asks whether a generative system can tell who wrote this and reuse it. Read the dimensions in two
            groups: <strong>entity recognition</strong>, <strong>knowledge graph signals</strong> and{" "}
            <strong>AI-readable structure</strong> are markup problems someone can fix this afternoon;{" "}
            <strong>fact density</strong>, <strong>citation readiness</strong> and <strong>topical authority</strong>{" "}
            are writing problems, and no amount of schema will move them.
            <br /><br />
            <strong>Original information gain</strong> is always &ldquo;Not measured&rdquo;. Establishing that information
            appears nowhere else needs a corpus to compare against, so it is listed as a real dimension and
            deliberately left unscored rather than estimated. <strong>Topical authority</strong> covers the on-site
            half only — depth and breadth of this site&apos;s own content; whether the wider web treats it as an
            authority is not measured. Spy does not guarantee inclusion in any AI-generated answer.
          </div>
        </>
      )}
    </div>
  );
}
