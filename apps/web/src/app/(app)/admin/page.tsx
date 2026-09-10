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

interface Revenue {
  total_revenue_minor: number;
  total_paid_purchases: number;
  revenue_last_n_days_minor: number;
  paid_purchases_last_n_days: number;
  days: number;
  mrr_minor: number;
  active_subscriptions: number;
  revenue_by_product_type: { product_type: string; amount_minor: number; count: number }[];
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
  recent_webhook_errors: { id: string; event_type: string; error: string | null; received_at: string }[];
}

function rupees(minor: number): string {
  return `₹${(minor / 100).toLocaleString("en-IN")}`;
}

export default function AdminPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [revenue, setRevenue] = useState<Revenue | null>(null);
  const [queue, setQueue] = useState<QueueHealth | null>(null);
  const [errors, setErrors] = useState<ErrorSummary | null>(null);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    Promise.all([
      apiGet<Overview>("admin/overview"),
      apiGet<Revenue>("admin/revenue"),
      apiGet<QueueHealth>("admin/queue"),
      apiGet<ErrorSummary>("admin/errors"),
    ])
      .then(([o, r, q, e]) => {
        setOverview(o);
        setRevenue(r);
        setQueue(q);
        setErrors(e);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) setForbidden(true);
      });
  }, []);

  if (forbidden) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-semibold text-red-400">Admin access required</h1>
        <p className="text-muted mt-2">Your account doesn&apos;t have platform-admin access.</p>
      </div>
    );
  }

  if (!overview || !revenue || !queue || !errors) return <div className="p-8 text-muted">Loading…</div>;

  return (
    <div className="p-8 max-w-6xl space-y-10">
      <div>
        <h1 className="text-2xl font-semibold">Admin</h1>
        <p className="text-muted text-sm mt-1">Platform-wide overview — visible only to super admins.</p>
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
        <h2 className="text-lg font-semibold mb-4">Revenue</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="card p-5">
            <div className="text-2xl font-bold">{rupees(revenue.total_revenue_minor)}</div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">Total Revenue</div>
          </div>
          <div className="card p-5">
            <div className="text-2xl font-bold">{rupees(revenue.revenue_last_n_days_minor)}</div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">Last {revenue.days} Days</div>
          </div>
          <div className="card p-5">
            <div className="text-2xl font-bold">{rupees(revenue.mrr_minor)}</div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">MRR</div>
          </div>
          <div className="card p-5">
            <div className="text-2xl font-bold">{revenue.active_subscriptions}</div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">Active Subscriptions</div>
          </div>
        </div>
        {revenue.revenue_by_product_type.length > 0 && (
          <div className="card p-4">
            <div className="text-xs text-muted uppercase tracking-wide mb-2">By Product</div>
            <div className="space-y-1">
              {revenue.revenue_by_product_type.map((row) => (
                <div key={row.product_type} className="flex justify-between text-sm">
                  <span>{row.product_type}</span>
                  <span className="text-muted">{rupees(row.amount_minor)} ({row.count})</span>
                </div>
              ))}
            </div>
          </div>
        )}
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
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
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
          <div className="card p-5">
            <div className="text-2xl font-bold">{errors.recent_webhook_errors.length}</div>
            <div className="text-xs text-muted uppercase tracking-wide mt-1">Webhook Errors</div>
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
