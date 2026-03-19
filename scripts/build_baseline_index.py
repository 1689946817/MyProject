"""
为 baseline 方法构建向量索引。

在运行 baseline_clip 和 baseline_ocr 评估前，需要先执行此脚本。
脚本从 SQLite 读取已上传图片记录，分别构建：
  - images_multimodal_embedding（baseline_clip 用）
  - images_ocr_text（baseline_ocr 用）

用法（在项目根目录，后端无需启动）：

  # 构建两个 baseline 的索引
  python scripts/build_baseline_index.py --method all

  # 只构建 clip baseline
  python scripts/build_baseline_index.py --method clip

  # 只构建 ocr baseline
  python scripts/build_baseline_index.py --method ocr

  # 只处理 mapping 文件中的图片（评估子集）
  python scripts/build_baseline_index.py --method all \
      --mapping data/coco_id_to_uuid.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 将 backend 加入路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.data.database import SessionLocal
from app.data.models import ImageRecord


def get_image_records(uuid_filter: set[str] | None = None) -> list[dict]:
    """从 SQLite 读取已完成的图片记录。"""
    db = SessionLocal()
    try:
        query = db.query(ImageRecord).filter(ImageRecord.status == "Completed")
        records = query.all()
    finally:
        db.close()

    result = []
    for r in records:
        if uuid_filter and r.id not in uuid_filter:
            continue
        result.append({
            "id": r.id,
            "file_path": r.file_path,
            "description": r.generated_description or "",
        })
    return result


def build_clip(records: list[dict]) -> None:
    from evaluation.methods.baseline_clip_retrieval import build_vector_index
    print(f"Building CLIP index for {len(records)} images ...")
    build_vector_index(records)


def build_ocr(records: list[dict]) -> None:
    from evaluation.methods.baseline_ocr_rag import build_ocr_index
    print(f"Building OCR index for {len(records)} images ...")
    build_ocr_index(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build baseline vector indexes.")
    parser.add_argument(
        "--method",
        choices=["clip", "ocr", "all"],
        default="all",
        help="要构建的索引类型",
    )
    parser.add_argument(
        "--mapping",
        default=None,
        help="coco_id_to_uuid.json 路径，若指定则只处理映射中的图片",
    )
    args = parser.parse_args()

    # 确定 UUID 过滤集合
    uuid_filter: set[str] | None = None
    if args.mapping:
        mapping_path = Path(args.mapping)
        if not mapping_path.exists():
            print(f"[ERROR] Mapping file not found: {mapping_path}")
            return
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        uuid_filter = set(mapping.values())
        print(f"Filtering to {len(uuid_filter)} images from mapping.")

    records = get_image_records(uuid_filter)
    if not records:
        print("[ERROR] No completed image records found in database.")
        return
    print(f"Loaded {len(records)} image records from SQLite.")

    if args.method in ("clip", "all"):
        build_clip(records)

    if args.method in ("ocr", "all"):
        build_ocr(records)

    print("\nDone.")


if __name__ == "__main__":
    main()
