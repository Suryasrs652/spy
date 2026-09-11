import type { NextConfig } from "next";

// §104 security hardening. The CSP is production-only: `next dev`'s Fast
// Refresh relies on eval() and inline scripts that a real CSP would block,
// so enforcing it in dev would just break hot reload without protecting
// anything (dev never faces real users). script-src/frame-src allow
// Razorpay's checkout widget (apps/web/src/app/(app)/billing/page.tsx
// loads https://checkout.razorpay.com/v1/checkout.js and opens its iframe)
// and Google's OAuth/GSC-connect redirects; everything else defaults shut.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' https://checkout.razorpay.com",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  "font-src 'self' data:",
  "connect-src 'self' https://api.razorpay.com https://lumberjack.razorpay.com",
  "frame-src 'self' https://api.razorpay.com https://checkout.razorpay.com",
  "object-src 'none'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), camera=(), microphone=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  ...(process.env.NODE_ENV === "production" ? [{ key: "Content-Security-Policy", value: CSP }] : []),
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // "standalone" packages a self-contained Node server for our own Docker
  // image (infra/docker/Dockerfile.web) — Vercel's own build pipeline
  // produces its own serverless/edge output and conflicts with it (a
  // standalone build's trace files aren't in the shape Vercel's builder
  // expects), so it's skipped when VERCEL is set.
  ...(process.env.VERCEL ? {} : { output: "standalone" }),
  // Dev-only: lets `next dev`'s HMR/Fast Refresh accept requests from
  // spy.local (a hosts-file alias to localhost used for local testing) —
  // without this, Next's dev-origin protection silently blocks the HMR
  // websocket and the page never finishes hydrating. No effect in
  // production (allowedDevOrigins is a dev-server-only option).
  allowedDevOrigins: ["spy.local"],
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
