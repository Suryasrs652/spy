"use client";

import { useState } from "react";
import { signOut } from "next-auth/react";
import { apiDelete, apiGet, ApiError } from "@/lib/api";

export default function SettingsPage() {
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function connectGsc() {
    setLoading(true);
    try {
      const result = await apiGet<{ authorization_url: string }>("integrations/gsc/connect");
      window.location.href = result.authorization_url;
    } finally {
      setLoading(false);
    }
  }

  async function deleteAccount() {
    setDeleteError(null);
    setDeleting(true);
    try {
      await apiDelete("auth/me");
      await signOut({ callbackUrl: "/" });
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Couldn't delete your account.");
      setDeleting(false);
    }
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-semibold mb-6">Settings</h1>

      <div className="card p-6 mb-6">
        <h2 className="font-semibold mb-1">Google Search Console</h2>
        <p className="text-sm text-muted mb-4">
          Connect your Search Console property to see clicks, impressions and query data
          alongside your Spy audit results.
        </p>
        <button onClick={connectGsc} disabled={loading} className="btn-secondary">
          {loading ? "Redirecting…" : "Connect Search Console"}
        </button>
      </div>

      <div className="card p-6 border-red-600/50">
        <h2 className="font-semibold mb-1 text-red-400">Danger Zone</h2>
        <p className="text-sm text-muted mb-4">
          Permanently delete your account. Your email and password are removed and can never be
          recovered. If you&apos;re the sole owner of a workspace with other members, transfer
          ownership or remove them first.
        </p>
        {!confirming ? (
          <button onClick={() => setConfirming(true)} className="btn-secondary border-red-600 text-red-400">
            Delete My Account
          </button>
        ) : (
          <div className="space-y-3">
            <p className="text-sm">Are you sure? This cannot be undone.</p>
            <div className="flex gap-3">
              <button
                onClick={deleteAccount}
                disabled={deleting}
                className="btn-secondary border-red-600 text-red-400 disabled:opacity-50"
              >
                {deleting ? "Deleting…" : "Yes, delete my account"}
              </button>
              <button onClick={() => setConfirming(false)} disabled={deleting} className="btn-secondary">
                Cancel
              </button>
            </div>
            {deleteError && <p className="text-sm text-red-400">{deleteError}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
