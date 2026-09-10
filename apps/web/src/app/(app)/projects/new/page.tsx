"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiPost, ApiError, Project } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const project = await apiPost<Project>("projects", { name, url });
      router.push(`/projects/${project.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "BLOCKED_TARGET") {
        setError("That URL can't be audited — it points to a private or internal address.");
      } else if (err instanceof ApiError && err.code === "CONFLICT") {
        setError("You already have a project for this domain.");
      } else {
        setError(err instanceof ApiError ? err.message : "Something went wrong.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-8 max-w-lg">
      <h1 className="text-2xl font-semibold mb-6">Add a Project</h1>
      <form onSubmit={onSubmit} className="card p-6">
        {error && (
          <div className="mb-4 text-sm text-red-400 bg-red-950/30 border border-red-900 rounded-md p-3">
            {error}
          </div>
        )}

        <label className="label" htmlFor="name">Project name</label>
        <input id="name" required className="input mb-4" value={name} onChange={(e) => setName(e.target.value)} />

        <label className="label" htmlFor="url">Website URL</label>
        <input
          id="url" type="url" required placeholder="https://example.com" className="input mb-2"
          value={url} onChange={(e) => setUrl(e.target.value)}
        />
        <p className="text-xs text-muted mb-6">Any URL on the site — we&apos;ll audit the whole domain.</p>

        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? "Adding…" : "Add Project"}
        </button>
      </form>
    </div>
  );
}
