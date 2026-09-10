import { serverApiGet } from "@/lib/serverApi";
import type { Audit } from "@/lib/api";

export async function getLatestCompletedAudit(projectId: string): Promise<Audit | null> {
  const audits = await serverApiGet<Audit[]>(`projects/${projectId}/audits`);
  return audits?.find((a) => a.status === "COMPLETED") ?? null;
}
