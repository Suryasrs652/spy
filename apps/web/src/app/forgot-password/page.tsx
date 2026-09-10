"use client";

import { useState } from "react";
import Link from "next/link";
import { publicAuthPost } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await publicAuthPost("forgot-password", { email });
    } finally {
      setLoading(false);
      setSent(true); // never reveal whether the account exists
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-6">
      <div className="card p-8 max-w-md w-full">
        {sent ? (
          <>
            <h1 className="text-xl font-semibold">Check your email</h1>
            <p className="mt-3 text-muted text-sm">
              If an account exists for {email}, a reset link is on its way.
            </p>
          </>
        ) : (
          <form onSubmit={onSubmit}>
            <h1 className="text-xl font-semibold mb-6">Reset your password</h1>
            <label className="label" htmlFor="email">Email</label>
            <input
              id="email" type="email" required className="input mb-6"
              value={email} onChange={(e) => setEmail(e.target.value)}
            />
            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? "Sending…" : "Send reset link"}
            </button>
          </form>
        )}
        <p className="mt-4 text-sm text-muted text-center">
          <Link href="/login" className="text-accent">Back to login</Link>
        </p>
      </div>
    </main>
  );
}
