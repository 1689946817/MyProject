from pathlib import Path
from typing import Literal

from app.core.config import settings


ImageSplit = Literal["train", "val", "test", "custom"]


BASE_STORAGE_DIR = Path("storage") / "images"


def ensure_storage_dir() -> None:
    BASE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def get_image_path(image_id: str, split: ImageSplit = "custom") -> Path:
    ensure_storage_dir()
    split_dir = BASE_STORAGE_DIR / split
    split_dir.mkdir(parents=True, exist_ok=True)
    return split_dir / f"{image_id}.jpg"

