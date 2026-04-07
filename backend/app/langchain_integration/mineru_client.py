"""MinerU 官方解析 API 客户端。"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

from app.core.config import settings


def _client_kwargs(timeout: Optional[int] = None) -> dict[str, Any]:
    return {
        "base_url": settings.MINERU_API_BASE_URL.rstrip("/"),
        "timeout": timeout or settings.MINERU_TIMEOUT_SECONDS,
        "trust_env": False,
    }


@dataclass
class MinerUTaskStatus:
    state: str
    progress_pages: int = 0
    total_pages: int = 0
    full_zip_url: Optional[str] = None
    err_msg: str = ""


@dataclass
class MinerUParseResult:
    markdown_text: str
    images: list[tuple[str, bytes]]
    raw_metadata: dict[str, Any]
    zip_bytes: bytes
    markdown_file_name: str = "full.md"


class MinerUClient:
    """封装 MinerU 精准解析 API。"""

    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.MINERU_API_TOKEN

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise ValueError("MinerU API token 未配置")
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    async def create_upload_task(self, file_name: str, data_id: str) -> tuple[str, str]:
        payload = {
            "files": [{"name": file_name, "data_id": data_id}],
            "model_version": settings.MINERU_MODEL_VERSION,
        }
        async with httpx.AsyncClient(**_client_kwargs()) as client:
            response = await client.post("/api/v4/file-urls/batch", headers=self._headers(), json=payload)
            response.raise_for_status()
            data = response.json()
        if data.get("code") != 0:
            raise ValueError(f"MinerU 创建上传任务失败: {data.get('msg')}")
        result = data.get("data") or {}
        batch_id = str(result.get("batch_id") or "").strip()
        file_urls = result.get("file_urls") or []
        if not batch_id or not file_urls:
            raise ValueError("MinerU 返回的 batch_id 或 file_urls 为空")
        return batch_id, str(file_urls[0])

    async def upload_file(self, signed_url: str, file_bytes: bytes) -> None:
        async with httpx.AsyncClient(timeout=settings.MINERU_TIMEOUT_SECONDS, trust_env=False) as client:
            response = await client.put(signed_url, content=file_bytes)
            response.raise_for_status()

    async def get_batch_result(self, batch_id: str, file_name: str) -> MinerUTaskStatus:
        async with httpx.AsyncClient(**_client_kwargs()) as client:
            response = await client.get(f"/api/v4/extract-results/batch/{batch_id}", headers=self._headers())
            response.raise_for_status()
            data = response.json()
        if data.get("code") != 0:
            raise ValueError(f"MinerU 查询任务结果失败: {data.get('msg')}")
        batch_data = data.get("data") or {}
        extract_result = batch_data.get("extract_result") or []
        matched = None
        for item in extract_result:
            if str(item.get("file_name") or "").strip() == file_name:
                matched = item
                break
        if matched is None and extract_result:
            matched = extract_result[0]
        if matched is None:
            return MinerUTaskStatus(state="pending")
        progress = matched.get("extract_progress") or {}
        return MinerUTaskStatus(
            state=str(matched.get("state") or "pending"),
            progress_pages=int(progress.get("extracted_pages") or 0),
            total_pages=int(progress.get("total_pages") or 0),
            full_zip_url=matched.get("full_zip_url"),
            err_msg=str(matched.get("err_msg") or ""),
        )

    async def download_result_zip(self, full_zip_url: str) -> MinerUParseResult:
        async with httpx.AsyncClient(timeout=settings.MINERU_TIMEOUT_SECONDS, trust_env=False) as client:
            response = await client.get(full_zip_url)
            response.raise_for_status()
            zip_bytes = response.content

        markdown_text = ""
        markdown_file_name = "full.md"
        images: list[tuple[str, bytes]] = []
        raw_metadata: dict[str, Any] = {"full_zip_url": full_zip_url, "files": []}
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            names = archive.namelist()
            raw_metadata["files"] = names
            md_candidates = [name for name in names if name.lower().endswith(".md")]
            if md_candidates:
                preferred = next((name for name in md_candidates if Path(name).name.lower() == "full.md"), md_candidates[0])
                markdown_file_name = Path(preferred).name
                markdown_text = archive.read(preferred).decode("utf-8", errors="ignore")
            for name in names:
                lowered = name.lower()
                if lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
                    images.append((Path(name).name, archive.read(name)))
            json_candidates = [name for name in names if name.lower().endswith(".json")]
            if json_candidates:
                try:
                    raw_metadata["json_preview"] = json.loads(archive.read(json_candidates[0]).decode("utf-8", errors="ignore"))
                except Exception:
                    pass

        if not markdown_text:
            raise ValueError("MinerU 结果压缩包中未找到 Markdown 内容")
        return MinerUParseResult(
            markdown_text=markdown_text,
            images=images,
            raw_metadata=raw_metadata,
            zip_bytes=zip_bytes,
            markdown_file_name=markdown_file_name,
        )
