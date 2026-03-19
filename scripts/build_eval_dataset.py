"""
根据 COCO captions 和上传映射，生成检索评估数据集 JSON。

用法（在项目根目录）：
    python scripts/build_eval_dataset.py \
        --captions-json data/annotations/captions_val2017.json \
        --mapping data/coco_id_to_uuid.json \
        --output data/coco_subset_eval.json
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build eval dataset from COCO captions + UUID mapping.")
    parser.add_argument("--captions-json", required=True, help="captions_val2017.json 路径")
    parser.add_argument("--mapping", default="data/coco_id_to_uuid.json", help="coco_id_to_uuid.json 路径")
    parser.add_argument("--output", default="data/coco_subset_eval.json", help="输出路径")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    captions_path = Path(args.captions_json)
    mapping_path = Path(args.mapping)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 读取映射
    mapping: dict[str, str] = json.loads(mapping_path.read_text(encoding="utf-8"))
    print(f"Loaded {len(mapping)} uploaded images from {mapping_path}")

    # 读取 captions，按 image_id 分组
    data = json.loads(captions_path.read_text(encoding="utf-8"))
    id_to_captions: dict[str, list[str]] = {}
    for ann in data["annotations"]:
        iid = str(ann["image_id"])
        if iid in mapping:
            id_to_captions.setdefault(iid, []).append(ann["caption"])

    # 构建评估样本
    random.seed(args.seed)
    samples = []
    for coco_id, uuid in mapping.items():
        captions = id_to_captions.get(coco_id, [])
        if not captions:
            continue
        # 随机打乱，第一条作为 query，其余拼接为 reference_answer
        random.shuffle(captions)
        query = captions[0]
        reference_answer = " ".join(captions[1:]) if len(captions) > 1 else ""
        samples.append({
            "query": query,
            "relevant_ids": [uuid],
            "reference_answer": reference_answer,
        })

    output_path.write_text(json.dumps(samples, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Done. {len(samples)} samples saved to {output_path}")


if __name__ == "__main__":
    main()
