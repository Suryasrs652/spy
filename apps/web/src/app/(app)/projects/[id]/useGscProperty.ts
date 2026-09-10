"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import type { GscProperty } from "@/lib/api";

export function useGscProperty(projectId: string) {
  const [properties, setProperties] = useState<GscProperty[] | null>(null);
  const [linking, setLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const props = await apiGet<GscProperty[]>("gsc/properties");
      setProperties(props);
    } catch {
      setProperties([]);
    }
  }, []);

  useEffect(() => {
    // load() only sets state after its own await resolves (a plain
    // fetch-on-mount), not synchronously within this effect body.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function linkProperty(propertyId: string) {
    setError(null);
    setLinking(true);
    try {
      await apiPost(`gsc/properties/${propertyId}/connect`, { project_id: projectId });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't link that property.");
    } finally {
      setLinking(false);
    }
  }

  const property = properties?.find((p) => p.project_id === projectId && p.selected) ?? null;
  // Only properties with no project at all — one already linked+selected
  // elsewhere would be silently reassigned away from that other project
  // (a GscProperty has at most one project_id), so it's excluded here.
  const unlinked = properties?.filter((p) => !p.project_id) ?? [];

  return { properties, property, unlinked, loading: properties === null, linking, error, linkProperty };
}
