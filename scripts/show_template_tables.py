from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSPECTION_PATH = ROOT / "template_inspection.json"


def main() -> None:
    data = json.loads(INSPECTION_PATH.read_text(encoding="utf-8"))
    for table in data["tables"]:
        print(f'=== table {table["index"]} ({table["rows"]}x{table["cols"]}) ===')
        for ridx, row in enumerate(table["cells"], start=1):
            print(f"{ridx:>3}: {row}")


if __name__ == "__main__":
    main()
