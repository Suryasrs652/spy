import Link from "next/link";
import { serverApiGet } from "@/lib/serverApi";
import { getLatestCompletedAudit } from "@/lib/latestAudit";
import type { Project } from "@/lib/api";
import { SubScores } from "@/components/SubScores";

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

          <SubScores title="The seven signals" section={aeo} />

          <div className="h-8" />

          <div className="card p-6 text-sm text-muted">
            AEO asks whether an answer engine could lift an answer out of this site. <strong>Answerability</strong>
            is the one to read first: it counts only pages that both pose something — a question heading, a
            definition list, a table — <em>and</em> carry at least one paragraph that survives being quoted away
            from its neighbours. Either half alone is not an answer, which is why adding headings without
            rewriting the prose beneath them rarely moves this score.
            <br /><br />
            <strong>FAQ implementation</strong> reads &ldquo;Not measured&rdquo; when no page poses a question in a heading —
            there is no Q&amp;A content for the markup to be missing from, and a catalogue is not worse for
            lacking it. Spy measures readiness to be cited; it cannot observe whether any engine cited you, and
            does not guarantee inclusion in any AI-generated answer.
          </div>
        </>
      )}
    </div>
  );
}
