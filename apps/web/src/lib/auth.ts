/**
 * Auth.js v5 as the session layer only (see plan §"Auth owner").
 *
 * It never touches a password hash or the users table directly — Credentials
 * `authorize()` and the Google `signIn` callback both call FastAPI's
 * `/internal/auth/*` endpoints (guarded by a shared service token that never
 * reaches the browser) and store the FastAPI-issued access/refresh tokens
 * inside the encrypted session JWT. The Credentials provider forces JWT
 * sessions (no database-session adapter is possible), which is exactly what
 * keeps FastAPI as the single owner of the users table.
 */
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://api:8000";
const INTERNAL_SERVICE_TOKEN = process.env.INTERNAL_SERVICE_TOKEN ?? "";

interface InternalUserOut {
  user_id: string;
  email: string;
  email_verified: boolean;
  default_organization_id: string;
  access_token: string;
  refresh_token: string;
}

async function callInternalAuth(path: string, body: Record<string, unknown>): Promise<InternalUserOut | null> {
  const res = await fetch(`${API_BASE_URL}/internal/auth/${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Token": INTERNAL_SERVICE_TOKEN,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as InternalUserOut;
}

async function refreshAccessToken(refreshToken: string): Promise<string | null> {
  const res = await fetch(`${API_BASE_URL}/internal/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Internal-Token": INTERNAL_SERVICE_TOKEN },
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { access_token: string };
  return data.access_token;
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  session: { strategy: "jwt" },
  pages: {
    signIn: "/login",
  },
  providers: [
    Credentials({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;
        const result = await callInternalAuth("verify-credentials", {
          email: credentials.email,
          password: credentials.password,
        });
        if (!result) return null;
        return {
          id: result.user_id,
          email: result.email,
          emailVerified: result.email_verified,
          organizationId: result.default_organization_id,
          accessToken: result.access_token,
          refreshToken: result.refresh_token,
        } as never;
      },
    }),
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
  ],
  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider === "google") {
        const result = await callInternalAuth("oauth-upsert", {
          email: user.email,
          google_sub: account.providerAccountId,
          name: user.name,
        });
        if (!result) return false;
        // Stash FastAPI's identity onto the `user` object so the jwt()
        // callback below (which runs right after signIn) can read it.
        (user as Record<string, unknown>).id = result.user_id;
        (user as Record<string, unknown>).organizationId = result.default_organization_id;
        (user as Record<string, unknown>).accessToken = result.access_token;
        (user as Record<string, unknown>).refreshToken = result.refresh_token;
        (user as Record<string, unknown>).emailVerified = result.email_verified;
      }
      return true;
    },
    async jwt({ token, user }) {
      if (user) {
        const u = user as Record<string, unknown>;
        token.userId = u.id;
        token.organizationId = u.organizationId;
        token.accessToken = u.accessToken;
        token.refreshToken = u.refreshToken;
        token.emailVerified = u.emailVerified;
        // FastAPI access tokens are short-lived (§115
        // ACCESS_TOKEN_TTL_MINUTES=15); track expiry so we know when to
        // refresh rather than forwarding a stale token to the BFF proxy.
        token.accessTokenExpiresAt = Date.now() + 14 * 60 * 1000;
        return token;
      }

      if (typeof token.accessTokenExpiresAt === "number" && Date.now() < token.accessTokenExpiresAt) {
        return token;
      }

      if (typeof token.refreshToken === "string") {
        const newAccessToken = await refreshAccessToken(token.refreshToken);
        if (newAccessToken) {
          token.accessToken = newAccessToken;
          token.accessTokenExpiresAt = Date.now() + 14 * 60 * 1000;
        }
      }
      return token;
    },
    async session({ session, token }) {
      session.user.id = token.userId as string;
      session.organizationId = token.organizationId as string;
      session.accessToken = token.accessToken as string;
      session.emailVerified = token.emailVerified as boolean;
      return session;
    },
  },
});
