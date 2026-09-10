"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet } from "@/lib/api";
import type { Audit } from "@/lib/api";

export function CompareSelector({ auditId, projectId }: { auditId: string; projectId: string }) {
  const router = useRouter();
  const [others, setOthers] = useState<Audit[] | null>(null);
  const [selected, setSelected] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    apiGet<Audit[]>(`projects/${projectId}/audits`)
      .then((all) => {
        if (cancelled) return;
        const candidates = all.filter((a) => a.id !== auditId && a.status === "COMPLETED");
        setOthers(candidates);
        if (candidates.length > 0) setSelected(candidates[0].id);
      })
      .catch(() => {
        if (!cancelled) setOthers([]);
      });
    return () => {
      cancelled = true;
    };
  }, [auditId, projectId]);

  if (!others || others.length === 0) return null;

  return (
    <div className="card p-4 mb-10 flex items-center gap-3">
      <span className="text-sm text-muted shrink-0">Compare against</span>
      <select value={selected} onChange={(e) => setSelected(e.target.value)} className="input flex-1">
        {others.map((a) => (
          <option key={a.id} value={a.id}>
            {new Date(a.created_at).toLocaleDateString()} — Spy Score {a.spy_score ?? "N/A"}
          </option>
        ))}
      </select>
      <button
        onClick={() => router.push(`/audits/${auditId}/compare/${selected}`)}
        className="btn-secondary shrink-0"
        disabled={!selected}
      >
        Compare
      </button>
    </div>
  );
}
