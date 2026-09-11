"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiPost, ApiError, Audit } from "@/lib/api";

export function RunAuditButton({
  projectId, canRun, reason,
}: { projectId: string; canRun: boolean; reason: string | null }) {
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
      if (err instanceof ApiError && err.code === "AUDIT_PAYMENT_REQUIRED") {
        router.push("/billing");
        return;
      }
      if (err instanceof ApiError && err.code === "ADMIN_DAILY_LIMIT_REACHED") {
        setError(err.message);
        return;
      }
      setError(err instanceof ApiError ? err.message : "Couldn't start the audit.");
    } finally {
      setLoading(false);
    }
  }

  if (!canRun && reason === "EMAIL_NOT_VERIFIED") {
    return <span className="text-sm text-muted">Verify your email to run an audit.</span>;
  }

  if (!canRun && reason === "ADMIN_DAILY_LIMIT_REACHED") {
    return <span className="text-sm text-muted">Daily free audit limit reached — resets at UTC midnight.</span>;
  }

  return (
    <div className="text-right">
      <button onClick={runAudit} disabled={loading} className="btn-primary">
        {loading ? "Starting…" : canRun ? "Run Audit" : "Buy a Credit"}
      </button>
      {error && <div className="text-xs text-red-400 mt-2">{error}</div>}
    </div>
  );
}
