from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSPECTION_PATH = ROOT / "template_inspection.json"


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python scripts/show_template_range.py <start> <end>")

    start = int(sys.argv[1])
    end = int(sys.argv[2])
    data = json.loads(INSPECTION_PATH.read_text(encoding="utf-8"))
    for item in data["paragraphs"]:
        if start <= item["index"] <= end:
            print(f'{item["index"]:>4} | {item["style"]} | {item["text"]}')


if __name__ == "__main__":
    main()
