"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { publicAuthPost, ApiError } from "@/lib/api";

export default function VerifyEmailPage() {
  const params = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Missing verification token.");
      return;
    }
    publicAuthPost("verify-email", { token })
      .then(() => setStatus("success"))
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof ApiError ? err.message : "Verification failed.");
      });
  }, [token]);

  return (
    <main className="min-h-screen flex items-center justify-center px-6">
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
    </main>
  );
}
