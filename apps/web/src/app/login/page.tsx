"use client";

import { useState } from "react";
import Link from "next/link";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const result = await signIn("credentials", { email, password, redirect: false });
    setLoading(false);
    if (result?.error) {
      setError("Invalid email or password.");
      return;
    }
    router.push("/dashboard");
    router.refresh();
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-6">
      <form onSubmit={onSubmit} className="card p-8 max-w-md w-full">
        <h1 className="text-xl font-semibold mb-6">Log in to Spy</h1>

        {error && (
          <div className="mb-4 text-sm text-red-400 bg-red-950/30 border border-red-900 rounded-md p-3">
            {error}
          </div>
        )}

        <label className="label" htmlFor="email">Email</label>
        <input
          id="email" type="email" required className="input mb-4"
          value={email} onChange={(e) => setEmail(e.target.value)}
        />

        <label className="label" htmlFor="password">Password</label>
        <input
          id="password" type="password" required className="input mb-2"
          value={password} onChange={(e) => setPassword(e.target.value)}
        />
        <div className="text-right mb-6">
          <Link href="/forgot-password" className="text-xs text-muted hover:text-accent">Forgot password?</Link>
        </div>

        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? "Logging in…" : "Log in"}
        </button>

        <button
          type="button"
          onClick={() => signIn("google", { callbackUrl: "/dashboard" })}
          className="btn-secondary w-full mt-3"
        >
          Continue with Google
        </button>

        <p className="mt-4 text-sm text-muted text-center">
          No account yet? <Link href="/signup" className="text-accent">Sign up free</Link>
        </p>
      </form>
    </main>
  );
}
