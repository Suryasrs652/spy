"use client";

import { useEffect, useState } from "react";
import { apiGet, ApiError } from "@/lib/api";

interface Overview {
  registered_users: number;
  verified_users: number;
  total_audits: number;
  completed_audits: number;
  audit_completion_rate: number | null;
}

interface QueueHealth {
  jobs_by_status: Record<string, number>;
  oldest_queued_job_age_seconds: number | null;
  stuck_jobs: { audit_id: string; status: string; heartbeat_age_seconds: number | null }[];
}

interface ErrorSummary {
  days: number;
  total_terminal_audits: number;
  total_failed_audits: number;
  failure_rate: number | null;
  failures_by_code: { failure_code: string; count: number }[];
}

export default function AdminPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [queue, setQueue] = useState<QueueHealth | null>(null);
  const [errors, setErrors] = useState<ErrorSummary | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiGet<Overview>("admin/overview"),
      apiGet<QueueHealth>("admin/queue"),
      apiGet<ErrorSummary>("admin/errors"),
    ])
      .then(([o, q, e]) => {
        setOverview(o);
        setQueue(q);
        setErrors(e);
      })
      .catch((err) => {
        setFailed(err instanceof ApiError ? err.message : "Couldn't load the admin dashboards.");
      });
  }, []);

  if (failed) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-semibold text-red-400">Admin</h1>
        <p className="text-muted mt-2">{failed}</p>
      </div>
    );
  }

  if (!overview || !queue || !errors) return <div className="p-8 text-muted">Loading…</div>;

  return (
    <div className="p-8 max-w-6xl space-y-10">
      <div>
        <h1 className="text-2xl font-semibold">Admin</h1>
        <p className="text-muted text-sm mt-1">Instance-wide health for this self-hosted deployment.</p>
      </div>

      <section>
        <h2 className="text-lg font-semibold mb-4">Overview</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="card p-5">
            <div className="text-2xl font-bold">{overview.registered_users}</div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">Registered Users</div>
          </div>
          <div className="card p-5">
            <div className="text-2xl font-bold">{overview.verified_users}</div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">Verified Users</div>
          </div>
          <div className="card p-5">
            <div className="text-2xl font-bold">{overview.total_audits}</div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">Total Audits</div>
          </div>
          <div className="card p-5">
            <div className="text-2xl font-bold">{overview.audit_completion_rate ?? "N/A"}%</div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">Completion Rate</div>
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-4">Queue Health</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          {Object.entries(queue.jobs_by_status).map(([status, count]) => (
            <div key={status} className="card p-5">
              <div className="text-2xl font-bold">{count}</div>
              <div className="text-xs text-muted uppercase tracking-wide mt-1">{status.replace(/_/g, " ")}</div>
            </div>
          ))}
        </div>
        {queue.stuck_jobs.length > 0 && (
          <div className="card p-4 border-red-600/50">
            <div className="text-xs text-red-400 uppercase tracking-wide mb-2">Stuck Jobs</div>
            <div className="space-y-1">
              {queue.stuck_jobs.map((j) => (
                <div key={j.audit_id} className="flex justify-between text-sm">
                  <span className="font-mono text-xs">{j.audit_id}</span>
                  <span className="text-muted">
                    {j.status} · {j.heartbeat_age_seconds ? `${Math.round(j.heartbeat_age_seconds / 60)}m stale` : "no heartbeat"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-4">Errors (last {errors.days} days)</h2>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="card p-5">
            <div className="text-2xl font-bold">{errors.total_failed_audits}</div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">Failed Audits</div>
          </div>
          <div className="card p-5">
            <div className="text-2xl font-bold">
              {errors.failure_rate !== null ? `${(errors.failure_rate * 100).toFixed(1)}%` : "N/A"}
            </div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">Failure Rate</div>
          </div>
        </div>
        {errors.failures_by_code.length > 0 && (
          <div className="card p-4">
            <div className="text-xs text-muted uppercase tracking-wide mb-2">By Failure Code</div>
            <div className="space-y-1">
              {errors.failures_by_code.map((row) => (
                <div key={row.failure_code} className="flex justify-between text-sm">
                  <span>{row.failure_code}</span>
                  <span className="text-muted">{row.count}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
