"use client";

import { useState } from "react";
import { apiGet } from "@/lib/api";

export default function SettingsPage() {
  const [loading, setLoading] = useState(false);

  async function connectGsc() {
    setLoading(true);
    try {
      const result = await apiGet<{ authorization_url: string }>("integrations/gsc/connect");
      window.location.href = result.authorization_url;
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-semibold mb-6">Settings</h1>

      <div className="card p-6">
        <h2 className="font-semibold mb-1">Google Search Console</h2>
        <p className="text-sm text-muted mb-4">
          Connect your Search Console property to see clicks, impressions and query data
          alongside your Spy audit results.
        </p>
        <button onClick={connectGsc} disabled={loading} className="btn-secondary">
          {loading ? "Redirecting…" : "Connect Search Console"}
        </button>
      </div>
    </div>
  );
}
