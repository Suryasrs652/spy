"use client";

import { useState } from "react";
import { apiGet, ApiError } from "@/lib/api";

interface ReportDownload {
  url: string;
  expires_in_seconds: number;
}

export function DownloadReportButton({ auditId }: { auditId: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setError(null);
    setLoading(true);
    try {
      const res = await apiGet<ReportDownload>(`audits/${auditId}/report/download`);
      window.open(res.url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't get the download link.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="text-right">
      <button onClick={download} disabled={loading} className="btn-primary text-xs px-3 py-1.5">
        {loading ? "Preparing…" : "Download PDF"}
      </button>
      {error && <div className="text-xs text-red-400 mt-1">{error}</div>}
    </div>
  );
}
