#!/usr/bin/env python3
"""
构建 Baseline CLIP Retrieval 的向量索引脚本。

该脚本从数据库中读取所有图像记录，使用 qwen3-vl-embedding 模型
将图像编码为向量，并存入独立的 ChromaDB 集合中。

使用方式：
    python -m evaluation.build_clip_index

注意：需要确保后端数据库已包含图像记录，并且 qwen3-vl-embedding 模型可用。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from typing import List, Dict, Any

from backend.app.data.database import SessionLocal
from backend.app.data.models import ImageRecord
from evaluation.methods.baseline_clip_retrieval import build_vector_index, check_vector_index


def get_all_image_records() -> List[Dict[str, Any]]:
    """
    从数据库中获取所有图像记录。

    Returns:
        List[Dict[str, Any]]: 图像记录列表，每个记录包含：
            - id: 图像 ID
            - file_path: 图像文件路径
            - description: 图像描述（如果已生成）
    """
    db = SessionLocal()
    try:
        # 获取所有状态为 Completed 的图像记录
        records = db.query(ImageRecord).filter(
            ImageRecord.status == "Completed"
        ).all()

        image_records = []
        for record in records:
            image_records.append({
                "id": record.id,
                "file_path": record.file_path,
                "description": record.generated_description or ""
            })

        print(f"Found {len(image_records)} completed image records in database")
        return image_records
    finally:
        db.close()


def main() -> None:
    """主函数：构建 Baseline CLIP 向量索引"""
    print("=" * 60)
    print("Building Baseline CLIP Retrieval Vector Index")
    print("=" * 60)

    # 检查是否已构建索引
    if check_vector_index():
        print("Vector index already exists. Do you want to rebuild it?")
        response = input("Type 'yes' to rebuild, anything else to cancel: ")
        if response.lower() != 'yes':
            print("Operation cancelled.")
            return

    # 获取图像记录
    print("\n1. Fetching image records from database...")
    image_records = get_all_image_records()

    if not image_records:
        print("No image records found in database. Please upload images first.")
        return

    # 检查图像文件是否存在
    print("\n2. Checking image files...")
    missing_files = []
    valid_records = []

    for record in image_records:
        file_path = Path(record["file_path"])
        if file_path.exists():
            valid_records.append(record)
        else:
            missing_files.append(record["file_path"])

    if missing_files:
        print(f"Warning: {len(missing_files)} image files not found:")
        for path in missing_files[:5]:  # 只显示前5个
            print(f"  - {path}")
        if len(missing_files) > 5:
            print(f"  ... and {len(missing_files) - 5} more")

    if not valid_records:
        print("No valid image files found. Cannot build vector index.")
        return

    print(f"Found {len(valid_records)} valid image files")

    # 构建向量索引
    print("\n3. Building vector index using qwen3-vl-embedding...")
    try:
        build_vector_index(valid_records)
        print("\n✅ Vector index built successfully!")
        print(f"   Collection: images_multimodal_embedding")
        print(f"   Total images: {len(valid_records)}")
    except Exception as e:
        print(f"\n❌ Failed to build vector index: {e}")
        print("\nPossible reasons:")
        print("1. qwen3-vl-embedding model not available")
        print("2. DashScope API key not configured")
        print("3. Network connection issues")
        print("\nPlease check your .env configuration and try again.")
        sys.exit(1)

    # 验证索引
    print("\n4. Verifying vector index...")
    if check_vector_index():
        print("✅ Vector index verification passed")
    else:
        print("❌ Vector index verification failed - collection is empty")


if __name__ == "__main__":
    main()