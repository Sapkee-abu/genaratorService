"""Template Service HTTP client (change.md Blocker 2).

The real `template_ps` MongoDB metadata is correct, but `originalFile.path`
points to a file on a different machine's filesystem than this Generator
Service instance can read. A teammate's server now exposes a real, tested
HTTP API for downloading the template file itself:

    GET {template_service_url}/api/templates/{version}/download

Mirrors monitor/client.py's explicit-failure-mode style: timeout,
connection failure, 404, and 5xx are all raised as TemplateDownloadError
with a specific message - never silently swallowed into a stale/local
fallback (change.md: "ห้าม silent fallback ไปที่ template เก่า/local").
"""

from __future__ import annotations

import httpx

from common.config import get_settings


class TemplateDownloadError(RuntimeError):
    """Raised whenever the Template Service can't provide the requested
    template version, for any reason - caller must fail clearly, never
    fall back to a stale/local template."""


async def download_template(version: int) -> bytes:
    settings = get_settings()
    if not settings.template_service_url:
        raise TemplateDownloadError("TEMPLATE_SERVICE_URL is not configured")

    url = f"{settings.template_service_url.rstrip('/')}/api/templates/{version}/download"

    try:
        async with httpx.AsyncClient(timeout=settings.template_service_timeout_seconds) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise TemplateDownloadError(
            f"Template Service request timed out after {settings.template_service_timeout_seconds}s: {exc}"
        ) from exc
    except httpx.RequestError as exc:
        raise TemplateDownloadError(
            f"Template Service connection failed ({type(exc).__name__}): {exc}"
        ) from exc

    if response.status_code == 404:
        raise TemplateDownloadError(f"Template Service has no template version {version} (HTTP 404)")
    if response.status_code >= 500:
        raise TemplateDownloadError(f"Template Service returned HTTP {response.status_code} for version {version}")
    if response.status_code >= 400:
        raise TemplateDownloadError(
            f"Template Service returned HTTP {response.status_code} for version {version} "
            "(client-side integration error)"
        )

    return response.content
