"use client";

import { useState } from "react";
import Link from "next/link";
import type { GscProperty } from "@/lib/api";

export function GscPropertyPicker({
  allProperties, unlinked, linking, error, onLink,
}: {
  allProperties: GscProperty[];
  unlinked: GscProperty[];
  linking: boolean;
  error: string | null;
  onLink: (propertyId: string) => void;
}) {
  const [selected, setSelected] = useState(unlinked[0]?.id ?? "");

  if (allProperties.length === 0) {
    return (
      <div className="card p-8 text-center text-muted">
        Google Search Console isn&apos;t connected yet.{" "}
        <Link href="/settings" className="text-accent hover:underline">Connect it in Settings</Link>, then come back
        here to link a property to this project.
      </div>
    );
  }

  if (unlinked.length === 0) {
    return (
      <div className="card p-8 text-center text-muted">
        All of your connected Search Console properties are already linked to other projects.{" "}
        <Link href="/settings" className="text-accent hover:underline">Connect another property in Settings</Link> to
        use it here.
      </div>
    );
  }

  return (
    <div className="card p-6">
      <p className="text-sm text-muted mb-4">
        No Search Console property is linked to this project yet. Choose one of your connected properties below.
      </p>
      <div className="flex items-center gap-3">
        <select
          className="input flex-1"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          {unlinked.map((p) => (
            <option key={p.id} value={p.id}>{p.site_url}</option>
          ))}
        </select>
        <button
          onClick={() => selected && onLink(selected)}
          disabled={linking || !selected}
          className="btn-primary shrink-0"
        >
          {linking ? "Linking…" : "Link Property"}
        </button>
      </div>
      {error && <p className="text-xs text-red-400 mt-3">{error}</p>}
    </div>
  );
}
