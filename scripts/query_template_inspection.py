from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSPECTION_PATH = ROOT / "template_inspection.json"


def main() -> None:
    data = json.loads(INSPECTION_PATH.read_text(encoding="utf-8"))
    patterns = sys.argv[1:] or ["摘  要", "ABSTRACT", "目  录", "第1章", "参考文献", "致谢"]
    for pattern in patterns:
        print(f"=== {pattern} ===")
        matched = False
        for item in data["paragraphs"]:
            text = item["text"]
            if pattern in text:
                matched = True
                print(f'{item["index"]:>4} | {item["style"]} | {text}')
        if not matched:
            print("not found")


if __name__ == "__main__":
    main()
