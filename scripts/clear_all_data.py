"""
清空所有数据库中的旧数据，包括：
  - SQLite：清空 image_records 表
  - ChromaDB：删除四个集合（images_main_kb, images_coco_proposed, images_multimodal_embedding, images_ocr_text）
  - 存储文件：清空 backend/storage/images/ 下的图片文件（可选）

用法（在项目根目录）：
  python scripts/clear_all_data.py
  python scripts/clear_all_data.py --keep-files   # 保留图片文件，只清数据库
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.data.models import ImageRecord, Base

# 直接指向 backend/app.db，不依赖工作目录
_db_path = Path(__file__).parent.parent / "backend" / "app.db"
_engine = create_engine(f"sqlite:///{_db_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=_engine)
engine = _engine

import chromadb
from chromadb.config import Settings as ChromaSettings


CHROMA_COLLECTIONS = [
    settings.MAIN_IMAGE_COLLECTION_NAME,
    settings.COCO_PROPOSED_COLLECTION_NAME,
    "images_multimodal_embedding",
    "images_ocr_text",
]


def clear_sqlite() -> None:
    print("Clearing SQLite image_records ...")
    # 确保表存在（后端首次启动时才会创建）
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        count = db.query(ImageRecord).count()
        db.query(ImageRecord).delete()
        db.commit()
        print(f"  Deleted {count} records.")
    finally:
        db.close()


def clear_chroma() -> None:
    print("Clearing ChromaDB collections ...")
    client = chromadb.Client(
        ChromaSettings(
            is_persistent=True,
            persist_directory=settings.CHROMA_PERSIST_DIR,
        )
    )
    existing = [c.name for c in client.list_collections()]
    for name in CHROMA_COLLECTIONS:
        if name in existing:
            client.delete_collection(name)
            print(f"  Deleted collection: {name}")
        else:
            print(f"  Collection not found (skip): {name}")


def clear_storage() -> None:
    storage_dir = Path(__file__).parent.parent / "backend" / "storage" / "images"
    if not storage_dir.exists():
        print(f"  Storage dir not found (skip): {storage_dir}")
        return
    count = 0
    for f in storage_dir.rglob("*"):
        if f.is_file():
            f.unlink()
            count += 1
    print(f"  Deleted {count} image files from {storage_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear all database data.")
    parser.add_argument("--keep-files", action="store_true", help="保留图片文件，只清数据库")
    args = parser.parse_args()

    print("=== Clearing all data ===\n")
    clear_sqlite()
    clear_chroma()
    if not args.keep_files:
        clear_storage()
    else:
        print("Skipping image file deletion (--keep-files).")

    print("\nDone. All data cleared.")


if __name__ == "__main__":
    main()
