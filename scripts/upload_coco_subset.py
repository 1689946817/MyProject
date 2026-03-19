"""
批量上传 COCO val2017 子集图片到知识库。

支持两种模式：
  1. 本地模式：图片已下载到本地，直接上传
  2. 自动下载模式：只需提供 captions JSON，脚本自动从 COCO 官网按需下载图片

用法（在项目根目录）：

  # 模式1：本地图片
  python scripts/upload_coco_subset.py \
      --coco-dir data/val2017 \
      --captions-json data/annotations/captions_val2017.json \
      --num-images 100

  # 模式2：自动下载（只需 captions JSON，不需要提前下载图片）
  python scripts/upload_coco_subset.py \
      --captions-json data/annotations/captions_val2017.json \
      --num-images 100 \
      --auto-download \
      --download-dir data/val2017_subset
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import requests

COCO_IMAGE_URL = "http://images.cocodataset.org/val2017/{filename}"


def download_image(coco_id: int, save_dir: Path, retries: int = 3) -> Path | None:
    """从 COCO 官网下载单张图片，返回本地路径，失败返回 None。"""
    filename = f"{coco_id:012d}.jpg"
    save_path = save_dir / filename
    if save_path.exists():
        return save_path
    url = COCO_IMAGE_URL.format(filename=filename)
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                save_path.write_bytes(resp.content)
                return save_path
            print(f"  [WARN] Download HTTP {resp.status_code} for {filename}")
        except Exception as e:
            print(f"  [WARN] Download attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    return None


def upload_image(img_path: Path, api_url: str, retries: int = 3) -> str | None:
    """上传单张图片到知识库，返回系统分配的 UUID，失败返回 None。"""
    for attempt in range(retries):
        try:
            with open(img_path, "rb") as f:
                resp = requests.post(
                    f"{api_url}/api/knowledge-base/upload",
                    files={"file": (img_path.name, f, "image/jpeg")},
                    timeout=60,
                )
            if resp.status_code == 200:
                return resp.json()["id"]
            print(f"  [WARN] Upload HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"  [WARN] Upload attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload COCO subset to knowledge base.")
    parser.add_argument("--captions-json", required=True, help="captions_val2017.json 路径")
    parser.add_argument("--coco-dir", default=None, help="本地 val2017 图片目录（本地模式）")
    parser.add_argument("--auto-download", action="store_true", help="自动从 COCO 官网下载图片")
    parser.add_argument("--download-dir", default="data/val2017_subset", help="自动下载时的保存目录")
    parser.add_argument("--num-images", type=int, default=100, help="抽取图片数量")
    parser.add_argument("--output-mapping", default="data/coco_id_to_uuid.json", help="映射文件输出路径")
    parser.add_argument("--api-url", default="http://localhost:9090", help="后端 API 地址")
    parser.add_argument("--seed", type=int, default=42, help="随机种子，保证可复现")
    args = parser.parse_args()

    if not args.auto_download and args.coco_dir is None:
        parser.error("请指定 --coco-dir（本地模式）或 --auto-download（自动下载模式）")

    captions_path = Path(args.captions_json)
    output_path = Path(args.output_mapping)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 读取 captions，获取所有 image_id
    print(f"Loading captions from {captions_path} ...")
    data = json.loads(captions_path.read_text(encoding="utf-8"))
    all_image_ids = list({img["id"] for img in data["images"]})

    if args.auto_download:
        # 自动下载模式：从全部 image_id 中随机抽取
        download_dir = Path(args.download_dir)
        download_dir.mkdir(parents=True, exist_ok=True)
        random.seed(args.seed)
        selected = random.sample(all_image_ids, min(args.num_images, len(all_image_ids)))
        print(f"Auto-download mode: will download {len(selected)} images to {download_dir}")
    else:
        # 本地模式：只从已存在的图片中抽取
        coco_dir = Path(args.coco_dir)
        available = [iid for iid in all_image_ids if (coco_dir / f"{iid:012d}.jpg").exists()]
        print(f"Found {len(available)} images in {coco_dir}")
        if len(available) < args.num_images:
            print(f"[WARN] Only {len(available)} images available, using all.")
        random.seed(args.seed)
        selected = random.sample(available, min(args.num_images, len(available)))

    # 加载已有映射（支持断点续传）
    mapping: dict[str, str] = {}
    if output_path.exists():
        mapping = json.loads(output_path.read_text(encoding="utf-8"))
        print(f"Resuming: {len(mapping)} already uploaded.")

    success = 0
    for i, coco_id in enumerate(selected):
        str_id = str(coco_id)
        if str_id in mapping:
            success += 1
            continue

        # 确定图片本地路径
        if args.auto_download:
            print(f"[{i+1}/{len(selected)}] Downloading {coco_id:012d}.jpg ...", end=" ", flush=True)
            img_path = download_image(coco_id, download_dir)
            if img_path is None:
                print("DOWNLOAD FAILED, skipping.")
                continue
            print("OK", end=" | ", flush=True)
        else:
            img_path = Path(args.coco_dir) / f"{coco_id:012d}.jpg"

        print(f"Uploading ...", end=" ", flush=True)
        uuid = upload_image(img_path, args.api_url)
        if uuid:
            mapping[str_id] = uuid
            success += 1
            print(f"OK -> {uuid}")
        else:
            print("UPLOAD FAILED")

        # 每 10 张保存一次，防止中途崩溃丢失进度
        if (i + 1) % 10 == 0:
            output_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")

    output_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone. {success}/{len(selected)} uploaded. Mapping saved to {output_path}")


if __name__ == "__main__":
    main()
