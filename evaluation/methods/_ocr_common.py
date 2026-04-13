from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def validate_ocr_python(python_executable: str) -> None:
    if not python_executable:
        raise RuntimeError("PADDLEOCR_PYTHON is empty.")

    if not Path(python_executable).exists():
        raise RuntimeError(
            f"PADDLEOCR_PYTHON does not exist: {python_executable}"
        )


def decode_ocr_subprocess_output(returncode: int, stdout: str, stderr: str) -> dict[str, str]:
    if returncode != 0:
        detail = (stderr or stdout or "").strip()
        raise RuntimeError(f"OCR subprocess failed: {detail[:500]}")

    try:
        payload = json.loads((stdout or "").strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"OCR subprocess returned invalid JSON: {(stdout or '')[:200]}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError("OCR subprocess returned a non-dict payload.")

    return {str(k): (v if isinstance(v, str) else "") for k, v in payload.items()}


def collect_ocr_stats(
    raw_texts_by_path: dict[str, str],
    fallback_text: str,
) -> dict[str, Any]:
    final_texts = [text if text else fallback_text for text in raw_texts_by_path.values()]
    non_empty_raw_count = sum(1 for text in raw_texts_by_path.values() if text.strip())
    fallback_count = sum(1 for text in final_texts if text == fallback_text)
    unique_final_text_count = len(set(final_texts))

    return {
        "total_count": len(final_texts),
        "non_empty_raw_count": non_empty_raw_count,
        "fallback_count": fallback_count,
        "unique_final_text_count": unique_final_text_count,
    }


def assert_ocr_stats_healthy(stats: dict[str, Any], context: str) -> None:
    total_count = int(stats["total_count"])
    non_empty_raw_count = int(stats["non_empty_raw_count"])
    fallback_count = int(stats["fallback_count"])
    unique_final_text_count = int(stats["unique_final_text_count"])

    if total_count == 0:
        raise RuntimeError(f"OCR index build produced no records for {context}.")

    if non_empty_raw_count == 0:
        raise RuntimeError(
            f"OCR index build collapsed for {context}: all OCR results are empty."
        )

    if fallback_count == total_count:
        raise RuntimeError(
            f"OCR index build collapsed for {context}: all records became fallback text."
        )

    if total_count > 1 and unique_final_text_count <= 1:
        raise RuntimeError(
            f"OCR index build collapsed for {context}: all OCR texts are identical."
        )


def is_ocr_index_healthy(
    documents: Iterable[str] | None,
    fallback_text: str,
) -> bool:
    if not documents:
        return False

    docs = [doc for doc in documents if isinstance(doc, str)]
    if not docs:
        return False

    if all(doc == fallback_text for doc in docs):
        return False

    if len(docs) > 1 and len(set(docs)) <= 1:
        return False

    return True
