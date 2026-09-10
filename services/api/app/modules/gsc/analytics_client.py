"""§32-§33 Google Search Console — Search Analytics API access + token
refresh. Same rationale as gsc/service.py's OAuth calls: these hit Google's
own well-known API hosts, not a user-supplied URL, so a plain httpx client
is used rather than the crawler's SSRF-guarded SafeFetcher (§107's guard is
specifically for arbitrary, user-controlled crawl targets).
"""
from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import decrypt_secret

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SEARCH_ANALYTICS_ROW_LIMIT = 25000  # Google's documented per-request max


class GscApiError(AppError):
    status_code = 502
    code = "GSC_API_ERROR"


async def refresh_access_token(encrypted_refresh_token: str) -> str:
    """Exchanges a stored, encrypted refresh token for a fresh access
    token. Called before every sync run — access tokens are short-lived
    (~1 hour) and never persisted, only the refresh token is (§106).
    """
    settings = get_settings()
    refresh_token = decrypt_secret(encrypted_refresh_token)

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code != 200:
        raise GscApiError(f"Failed to refresh Google access token: {response.status_code}")

    access_token = response.json().get("access_token")
    if not access_token:
        raise GscApiError("Google token refresh response had no access_token.")
    return access_token


async def query_search_analytics(
    *,
    access_token: str,
    site_url: str,
    start_date: str,
    end_date: str,
    dimensions: list[str],
    row_limit: int = SEARCH_ANALYTICS_ROW_LIMIT,
) -> list[dict]:
    """Fetches every row for the given date range/dimensions, paginating
    with `startRow` until Google returns fewer than a full page (§33).

    Google's Search Analytics API returns the *top* rows by default rather
    than a guaranteed-complete dataset for very high-traffic sites (§32) —
    this is documented API behavior, not a bug in this sync; it's the same
    limitation any GSC integration has.
    """
    import urllib.parse

    encoded_site = urllib.parse.quote(site_url, safe="")
    url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/searchAnalytics/query"

    all_rows: list[dict] = []
    start_row = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            body = {
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": dimensions,
                "rowLimit": row_limit,
                "startRow": start_row,
                "dataState": "all",
            }
            response = await client.post(
                url, json=body, headers={"Authorization": f"Bearer {access_token}"}
            )
            if response.status_code != 200:
                raise GscApiError(f"Search Analytics query failed: {response.status_code} {response.text[:200]}")

            payload = response.json()
            rows = payload.get("rows", [])
            all_rows.extend(rows)

            if len(rows) < row_limit:
                break
            start_row += row_limit

    return all_rows
