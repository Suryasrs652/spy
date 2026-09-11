/**
 * Server Component / server-action fetch helper — calls FastAPI directly,
 * skipping the in-container hop the browser's /api/proxy route needs.
 *
 * Spy is self-hosted and single-user, so there is no session to attach:
 * the API resolves every request to the one local workspace.
 */
const API_BASE_URL = process.env.API_BASE_URL ?? "http://api:8000";

export async function serverApiGet<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_BASE_URL}/api/v1/${path}`, { cache: "no-store" });
  if (!res.ok) return null;
  return (await res.json()) as T;
}
