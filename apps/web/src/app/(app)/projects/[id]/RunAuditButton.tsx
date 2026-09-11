"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiPost, ApiError, Audit } from "@/lib/api";

export function RunAuditButton({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runAudit() {
    setError(null);
    setLoading(true);
    try {
      const audit = await apiPost<Audit>(
        "audits",
        { project_id: projectId },
        { idempotencyKey: `run-audit-${projectId}-${Date.now()}` },
      );
      router.push(`/audits/${audit.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start the audit.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="text-right">
      <button onClick={runAudit} disabled={loading} className="btn-primary">
        {loading ? "Starting…" : "Run Audit"}
      </button>
      {error && <div className="text-xs text-red-400 mt-2">{error}</div>}
    </div>
  );
}
