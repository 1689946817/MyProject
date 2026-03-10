"""
文件存储管理模块

该模块负责管理图像文件的存储路径，包括：
- 定义存储目录结构
- 确保存储目录存在
- 根据图像ID和数据集分割获取图像路径

支持不同数据集分割的存储管理（train、val、test、custom）。
"""
from pathlib import Path
from typing import Literal, TypeAlias

from app.core.config import settings


# 图像数据集分割类型
ImageSplit: TypeAlias = Literal["train", "val", "test", "custom"]


# 基础存储目录路径
BASE_STORAGE_DIR = Path("storage") / "images"


def ensure_storage_dir() -> None:
    """确保存储目录存在
    
    创建基础存储目录及其父目录，若目录已存在则不做操作。
    """
    BASE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def get_image_path(image_id: str, split: ImageSplit = "custom") -> Path:
    """获取图像文件路径
    
    根据图像ID和数据集分割类型，生成并返回图像文件的完整路径。
    会自动创建所需的目录结构。
    
    Args:
        image_id: 图像唯一标识符
        split: 数据集分割类型，默认为 "custom"（自定义上传）
    
    Returns:
        Path: 图像文件的完整路径
    """
    # 确保基础存储目录存在
    ensure_storage_dir()
    
    # 构建分割目录路径
    split_dir = BASE_STORAGE_DIR / split
    # 确保分割目录存在
    split_dir.mkdir(parents=True, exist_ok=True)
    
    # 返回图像文件路径，使用 JPG 格式
    return split_dir / f"{image_id}.jpg"

