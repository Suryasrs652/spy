"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { publicAuthPost, ApiError } from "@/lib/api";

function VerifyEmailContent() {
  const params = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState<"loading" | "success" | "error">(token ? "loading" : "error");
  const [message, setMessage] = useState(token ? "" : "Missing verification token.");

  useEffect(() => {
    if (!token) return;
    publicAuthPost("verify-email", { token })
      .then(() => setStatus("success"))
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof ApiError ? err.message : "Verification failed.");
      });
  }, [token]);

  return (
    <div className="card p-8 max-w-md w-full text-center">
      {status === "loading" && <p className="text-muted">Verifying your email…</p>}
      {status === "success" && (
        <>
          <h1 className="text-xl font-semibold">Email verified</h1>
          <p className="mt-3 text-muted text-sm">Your free audit is now unlocked.</p>
          <Link href="/login" className="btn-primary inline-block mt-6">Log in</Link>
        </>
      )}
      {status === "error" && (
        <>
          <h1 className="text-xl font-semibold text-red-400">Verification failed</h1>
          <p className="mt-3 text-muted text-sm">{message}</p>
          <Link href="/login" className="btn-secondary inline-block mt-6">Back to login</Link>
        </>
      )}
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <main className="min-h-screen flex items-center justify-center px-6">
      {/* useSearchParams() opts a client component out of static rendering
          unless wrapped in Suspense — Next.js requires this boundary so the
          rest of the page can still prerender (build fails without it). */}
      <Suspense fallback={<div className="card p-8 max-w-md w-full text-center text-muted">Loading…</div>}>
        <VerifyEmailContent />
      </Suspense>
    </main>
  );
}
