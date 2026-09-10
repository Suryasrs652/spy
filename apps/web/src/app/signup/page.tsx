"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { publicAuthPost, ApiError } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await publicAuthPost("signup", { email, password, name: name || undefined });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <main className="min-h-screen flex items-center justify-center px-6">
        <div className="card p-8 max-w-md w-full text-center">
          <h1 className="text-xl font-semibold">Check your email</h1>
          <p className="mt-3 text-muted text-sm">
            We sent a verification link to <strong>{email}</strong>. Verify your email to unlock
            your free audit.
          </p>
          <Link href="/login" className="btn-secondary inline-block mt-6">Go to login</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-6">
      <form onSubmit={onSubmit} className="card p-8 max-w-md w-full">
        <h1 className="text-xl font-semibold mb-1">Create your Spy account</h1>
        <p className="text-sm text-muted mb-6">One free audit, no credit card required.</p>

        {error && (
          <div className="mb-4 text-sm text-red-400 bg-red-950/30 border border-red-900 rounded-md p-3">
            {error}
          </div>
        )}

        <label className="label" htmlFor="name">Your name (optional)</label>
        <input id="name" className="input mb-4" value={name} onChange={(e) => setName(e.target.value)} />

        <label className="label" htmlFor="email">Email</label>
        <input
          id="email" type="email" required className="input mb-4"
          value={email} onChange={(e) => setEmail(e.target.value)}
        />

        <label className="label" htmlFor="password">Password</label>
        <input
          id="password" type="password" required minLength={8} className="input mb-6"
          value={password} onChange={(e) => setPassword(e.target.value)}
        />

        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? "Creating account…" : "Sign up"}
        </button>

        <p className="mt-4 text-sm text-muted text-center">
          Already have an account? <Link href="/login" className="text-accent">Log in</Link>
        </p>
      </form>
    </main>
  );
}
