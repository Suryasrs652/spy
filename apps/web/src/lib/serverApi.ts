/**
 * Server Component / server-action fetch helper — calls FastAPI directly
 * (same auth attachment as the BFF proxy route, just without the extra
 * in-container hop) using the current request's session.
 */
import { auth } from "@/lib/auth";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://api:8000";

export async function serverApiGet<T>(path: string): Promise<T | null> {
  const session = await auth();
  if (!session?.accessToken) return null;

  const res = await fetch(`${API_BASE_URL}/api/v1/${path}`, {
    headers: {
      Authorization: `Bearer ${session.accessToken}`,
      "X-Organization-Id": session.organizationId,
    },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as T;
}
