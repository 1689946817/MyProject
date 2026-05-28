"""Baidu Qianfan web search fallback client.

The client is intentionally small: it only wraps the non-streaming
``web_summary`` endpoint and normalizes the answer summary plus references for
Agentic RAG's CRAG fallback path.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

BAIDU_WEB_SEARCH_PROVIDER = "baidu_qianfan"


def _stringify_content(value: Any) -> str:
    """Normalize possible text/list message content into a plain string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text is not None:
                    parts.append(str(text))
        return "\n".join(part.strip() for part in parts if part and part.strip())
    return str(value).strip()


def _extract_summary(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                return _stringify_content(message.get("content"))
            return _stringify_content(first.get("content"))
    return _stringify_content(payload.get("content") or payload.get("answer"))


def _extract_references(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    references = payload.get("references")
    if not isinstance(references, list):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    references = message.get("references")
                if not isinstance(references, list):
                    references = first.get("references")
    if not isinstance(references, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(references, start=1):
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link") or item.get("source_url") or item.get("href")
        title = item.get("title") or item.get("name") or item.get("site_name") or url
        content = (
            item.get("content")
            or item.get("snippet")
            or item.get("summary")
            or item.get("text")
            or item.get("description")
        )
        site_name = item.get("site_name") or item.get("site") or item.get("source") or item.get("hostname")
        published_at = item.get("date") or item.get("publish_time") or item.get("published_at")
        normalized.append(
            {
                "index": index,
                "title": str(title).strip() if title is not None else f"网页来源 {index}",
                "url": str(url).strip() if url is not None else "",
                "content": _stringify_content(content),
                "site_name": str(site_name).strip() if site_name is not None else "",
                "published_at": str(published_at).strip() if published_at is not None else "",
                "raw": item,
            }
        )
    return normalized


class BaiduWebSearchClient:
    """Minimal async client for Baidu Qianfan ``web_summary``."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else settings.BAIDU_WEB_SEARCH_API_KEY) or ""
        self.endpoint = endpoint or settings.BAIDU_WEB_SEARCH_ENDPOINT
        self.timeout_seconds = int(timeout_seconds or settings.BAIDU_WEB_SEARCH_TIMEOUT_SECONDS or 30)

    async def web_summary(self, query: str, *, top_k: Optional[int] = None) -> Dict[str, Any]:
        """Call Baidu web_summary once and normalize its response.

        Exceptions are converted into an ``error`` field so the RAG flow can
        safely continue with local context.
        """
        query = query.strip()
        resolved_top_k = int(top_k or settings.BAIDU_WEB_SEARCH_TOP_K or 5)
        result: Dict[str, Any] = {
            "provider": BAIDU_WEB_SEARCH_PROVIDER,
            "request_id": None,
            "summary": "",
            "references": [],
            "error": None,
            "raw": None,
        }
        if not self.api_key.strip():
            result["error"] = "missing_api_key"
            return result
        if not self.endpoint.strip():
            result["error"] = "missing_endpoint"
            return result
        if not query:
            result["error"] = "empty_query"
            return result

        request_payload = {
            "messages": [{"role": "user", "content": query}],
            "stream": False,
            "resource_type_filter": [{"type": "web", "top_k": resolved_top_k}],
        }
        headers = {
            "Content-Type": "application/json",
            "X-Appbuilder-Authorization": f"Bearer {self.api_key.strip()}",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
                response = await client.post(self.endpoint, headers=headers, json=request_payload)
            result["request_id"] = response.headers.get("x-bce-request-id") or response.headers.get("x-request-id")
            if response.status_code >= 400:
                result["error"] = f"http_{response.status_code}: {response.text[:300]}"
                return result
            payload = response.json()
            if isinstance(payload, dict):
                result["raw"] = payload
                result["request_id"] = payload.get("id") or payload.get("request_id") or result["request_id"]
                result["summary"] = _extract_summary(payload)
                result["references"] = _extract_references(payload)[:resolved_top_k]
            else:
                result["error"] = "invalid_response"
        except Exception as exc:  # pragma: no cover - network errors are mocked in tests
            result["error"] = str(exc).strip() or type(exc).__name__
        return result


async def search_baidu_web_summary(query: str, *, top_k: Optional[int] = None) -> Dict[str, Any]:
    """Convenience wrapper used by Agentic RAG."""
    client = BaiduWebSearchClient()
    return await client.web_summary(query, top_k=top_k)
