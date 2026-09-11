/**
 * Client-side fetch helpers. Everything goes through `/api/proxy/*`
 * (same-origin — see route.ts there), which forwards to FastAPI. Spy is
 * self-hosted and single-user, so there is no session or token involved.
 */

export class ApiError extends Error {
  code: string;
  status: number;
  requestId?: string;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

async function parseErrorOrThrow(res: Response): Promise<never> {
  let code = "UNKNOWN_ERROR";
  let message = `Request failed with status ${res.status}`;
  let requestId: string | undefined;
  try {
    const data = await res.json();
    if (data?.error) {
      code = data.error.code ?? code;
      message = data.error.message ?? message;
      requestId = data.error.request_id;
    }
  } catch {
    // non-JSON error body — keep the generic message
  }
  throw new ApiError(res.status, code, message, requestId);
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api/proxy/${path}`, { cache: "no-store" });
  if (!res.ok) return parseErrorOrThrow(res);
  return (await res.json()) as T;
}

export async function apiPost<T>(path: string, body?: unknown, opts?: { idempotencyKey?: string }): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts?.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
  const res = await fetch(`/api/proxy/${path}`, {
    method: "POST",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) return parseErrorOrThrow(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/proxy/${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) return parseErrorOrThrow(res);
  return (await res.json()) as T;
}

export async function apiDelete(path: string): Promise<void> {
  const res = await fetch(`/api/proxy/${path}`, { method: "DELETE", cache: "no-store" });
  if (!res.ok) await parseErrorOrThrow(res);
}

// ── Domain types (mirrors services/api/app/modules/*/schemas.py) ────────
export interface Project {
  id: string;
  name: string;
  domain: string;
  canonical_origin: string;
  status: string;
}

export interface Audit {
  id: string;
  project_id: string;
  status: string;
  max_urls: number;
  spy_score: number | null;
  technical_score: number | null;
  seo_score: number | null;
  content_score: number | null;
  performance_score: number | null;
  authority_score: number | null;
  aeo_score: number | null;
  geo_score: number | null;
  confidence: number | null;
  score_version: string;
  evidence: AuditEvidence;
  failure_category: string | null;
  failure_code: string | null;
  failure_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface AuditEvidence {
  weights_used?: Record<string, number>;
  architecture_score?: number;
  authority?: {
    referring_domains?: number;
    total_backlinks?: number;
    reason?: string;
  };
  aeo?: {
    schema_coverage_pct?: number;
    clean_heading_pct?: number;
    question_coverage_pct?: number;
    structured_content_pct?: number;
    byline_coverage_pct?: number;
    has_faq_schema?: boolean;
    reason?: string;
  };
  geo?: {
    has_organization_schema?: boolean;
    schema_coverage_pct?: number;
    org_field_completeness_pct?: number | null;
    entity_name_consistency_pct?: number | null;
    has_person_or_product_schema?: boolean;
    citation_readiness_pct?: number;
    reason?: string;
  };
  total_pages_scored?: number;
  urls_processed?: number;
}

export interface AuditPage {
  id: string;
  url: string;
  normalized_url: string;
  status_code: number | null;
  title: string | null;
  meta_description: string | null;
  h1: string | null;
  canonical_url: string | null;
  indexable: boolean;
  word_count: number | null;
  crawl_depth: number;
  internal_pagerank: number | null;
  response_ms: number | null;
  redirect_count: number;
  robots_allowed: boolean;
  from_sitemap: boolean;
  h1_count: number;
  h2_count: number;
  h3_count: number;
  heading_order_valid: boolean;
  has_schema: boolean;
  schema_types: string[];
  question_heading_count: number;
  list_count: number;
  table_count: number;
  has_definition_list: boolean;
  has_author_byline: boolean;
  images_missing_alt: number;
}

export interface AuditProgress {
  status: string;
  progress: number;
  urls_discovered: number;
  urls_processed: number;
  heartbeat_at: string | null;
  error_code: string | null;
  error_detail: string | null;
}

export interface AuditIssue {
  id: string;
  rule_id: string;
  category: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
  title: string;
  description: string;
  recommendation: string;
  affected_count: number;
  score_impact: number;
}

export interface Recommendation {
  id: string;
  category: string;
  title: string;
  description: string;
  impact: number;
  confidence: number;
  effort: number;
  priority_score: number;
  status: string;
  group: string;
}

export interface ScoreDelta {
  baseline: number | null;
  current: number | null;
  delta: number | null;
}

export interface IssueSummary {
  rule_id: string;
  category: string;
  severity: string;
  title: string;
  affected_count: number;
}

export interface AuditComparison {
  baseline_audit_id: string;
  current_audit_id: string;
  baseline_created_at: string;
  current_created_at: string;
  score_deltas: Record<string, ScoreDelta>;
  new_issues: IssueSummary[];
  resolved_issues: IssueSummary[];
  persisting_issues: IssueSummary[];
  page_count_baseline: number;
  page_count_current: number;
}

export interface BacklinkSummary {
  domain: string;
  total_backlinks: number;
  referring_domains: number;
  followed_backlinks: number;
}

export interface Backlink {
  id: string;
  source_url: string;
  source_domain: string;
  target_url: string;
  anchor_text: string | null;
  nofollow: boolean;
  created_at: string;
  updated_at: string;
}

export interface RankOverviewRow {
  id: string;
  keyword: string;
  added_at: string;
  has_data: boolean;
  current_position: number | null;
  best_position: number | null;
}

export interface RankHistoryPoint {
  date: string;
  position: number;
  clicks: number;
  impressions: number;
}

export interface RankHistory {
  keyword: string;
  has_data: boolean;
  reason: string | null;
  current_position: number | null;
  best_position: number | null;
  history: RankHistoryPoint[];
}

export interface Competitor {
  id: string;
  name: string;
  domain: string;
  status: "PENDING" | "CRAWLING" | "COMPLETED" | "FAILED";
  last_crawled_at: string | null;
  failure_message: string | null;
  spy_score: number | null;
  technical_score: number | null;
  seo_score: number | null;
  content_score: number | null;
  performance_score: number | null;
  aeo_score: number | null;
  geo_score: number | null;
  created_at: string;
}

export interface CompetitorComparison {
  competitor: Competitor;
  your_latest_audit_id: string | null;
  comparisons: { field: string; your_score: number | null; competitor_score: number | null; delta: number | null }[];
}

export interface ContentGap {
  has_data: boolean;
  reason: string | null;
  your_terms: string[];
  competitor_terms: string[];
  gap_terms: string[];
  methodology: string | null;
}

export interface GscProperty {
  id: string;
  project_id: string | null;
  site_url: string;
  permission_level: string;
  selected: boolean;
}

export interface GscPerformanceSummary {
  period: [string, string];
  clicks: number;
  impressions: number;
  ctr: number;
  average_position: number;
  source: string;
}

export interface GscQueryRow {
  query?: string | null;
  page?: string | null;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface GscOpportunityKeyword {
  query: string;
  clicks: number;
  impressions: number;
  position: number;
  actual_ctr?: number;
  spy_expected_ctr?: number;
}

export interface GscPeriodChange {
  query?: string;
  page?: string;
  current_clicks: number;
  previous_clicks: number;
  delta: number;
  pct_change: number;
}

export interface GscPositionChange {
  query: string;
  current_position: number;
  previous_position: number;
  delta: number;
}

export interface GscCannibalization {
  query: string;
  competing_pages: { page: string; clicks: number; impressions: number }[];
}

export interface GscOpportunities {
  period: { current: [string, string]; previous: [string, string] };
  striking_distance_keywords: GscOpportunityKeyword[];
  low_ctr_opportunities: GscOpportunityKeyword[];
  high_impressions_no_clicks: GscOpportunityKeyword[];
  declining_keywords: GscPeriodChange[];
  rising_keywords: GscPeriodChange[];
  declining_pages: GscPeriodChange[];
  rising_pages: GscPeriodChange[];
  position_gains: GscPositionChange[];
  position_losses: GscPositionChange[];
  keyword_cannibalization: GscCannibalization[];
}
