"""
OCR 公共工具模块。

提供多个 OCR 基线方法共用的辅助函数，包括：
- OCR 子进程 Python 解释器路径验证
- OCR 子进程输出解码与错误处理
- OCR 结果统计与健康性检查

本模块被 unidoc_ocr.py、baseline_ocr_rag.py 等 OCR 相关方法共享引用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def validate_ocr_python(python_executable: str) -> None:
    """验证 OCR 子进程使用的 Python 解释器路径是否有效。

    检查 PADDLEOCR_PYTHON 环境变量指定的 Python 解释器是否存在，
    防止因路径错误导致子进程启动失败。

    Args:
        python_executable: Python 解释器的可执行文件路径。

    Raises:
        RuntimeError: 路径为空或文件不存在。
    """
    if not python_executable:
        raise RuntimeError("PADDLEOCR_PYTHON is empty.")

    if not Path(python_executable).exists():
        raise RuntimeError(
            f"PADDLEOCR_PYTHON does not exist: {python_executable}"
        )


def decode_ocr_subprocess_output(returncode: int, stdout: str, stderr: str) -> dict[str, str]:
    """解码 OCR 子进程的标准输出，返回 {image_path: ocr_text} 映射。

    子进程通过 stdout 输出 JSON 格式的 OCR 结果字典。
    本函数负责：检查返回码、解析 JSON、验证数据类型。

    Args:
        returncode: 子进程退出码，非 0 表示执行失败。
        stdout: 子进程标准输出内容（JSON 字符串）。
        stderr: 子进程标准错误输出（用于错误诊断）。

    Returns:
        dict[str, str]: 图像路径到 OCR 识别文本的映射，值为空字符串时替换为 ""。

    Raises:
        RuntimeError: 子进程返回码非 0、输出非 JSON、或 JSON 非字典类型。
    """
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

    # 确保所有值均为字符串类型，非字符串值转为空字符串
    return {str(k): (v if isinstance(v, str) else "") for k, v in payload.items()}


def collect_ocr_stats(
    raw_texts_by_path: dict[str, str],
    fallback_text: str,
) -> dict[str, Any]:
    """统计 OCR 识别结果的健康指标。

    计算四个关键统计量，用于判断 OCR 索引构建是否正常：
    - 总记录数、非空原始文本数、回退文本数、唯一文本数

    Args:
        raw_texts_by_path: {图像路径: OCR 原始文本} 映射。
        fallback_text: OCR 为空时使用的替代文本（如 "[no text]"）。

    Returns:
        dict: 包含 total_count、non_empty_raw_count、fallback_count、
              unique_final_text_count 的统计字典。
    """
    # 对空 OCR 结果使用 fallback_text 填充，得到最终文本列表
    final_texts = [text if text else fallback_text for text in raw_texts_by_path.values()]
    # 统计原始 OCR 结果非空的数量（即 OCR 实际识别出文字的图片数）
    non_empty_raw_count = sum(1 for text in raw_texts_by_path.values() if text.strip())
    # 统计最终使用 fallback_text 的数量（OCR 完全失败的图片数）
    fallback_count = sum(1 for text in final_texts if text == fallback_text)
    # 统计去重后的唯一文本数量（若全部相同说明 OCR 崩溃）
    unique_final_text_count = len(set(final_texts))

    return {
        "total_count": len(final_texts),
        "non_empty_raw_count": non_empty_raw_count,
        "fallback_count": fallback_count,
        "unique_final_text_count": unique_final_text_count,
    }


def assert_ocr_stats_healthy(stats: dict[str, Any], context: str) -> None:
    """断言 OCR 统计结果处于健康状态，否则抛出异常中止流程。

    检查四种异常模式：
    1. 总记录数为 0 — 没有任何图片被处理
    2. 非空原始文本数为 0 — OCR 完全失败，所有图片识别为空
    3. 全部记录都使用了 fallback — OCR 未能识别出任何有效文字
    4. 所有文本完全相同 — OCR 可能崩溃返回了重复默认值

    Args:
        stats: collect_ocr_stats 返回的统计字典。
        context: 上下文标识（如集合名），用于错误消息。

    Raises:
        RuntimeError: 任一健康检查失败。
    """
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
    """检查已构建的 OCR 索引内容是否健康（非破坏性检查）。

    与 assert_ocr_stats_healthy 不同，本函数不抛异常，而是返回布尔值。
    用于 check_index 类场景，从已有 ChromaDB 集合中抽样验证。

    判断不健康的条件：
    1. 文档列表为空
    2. 所有文档都等于 fallback_text
    3. 多个文档但内容完全相同

    Args:
        documents: 待检查的文档文本列表（通常来自 ChromaDB peek）。
        fallback_text: OCR 回退文本标记。

    Returns:
        bool: True 表示索引健康，False 表示索引异常。
    """
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
