from __future__ import annotations

import json
from pathlib import Path

import win32com.client


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "docs" / "东北大学本科生毕业设计（论文）模版.docx"
OUTPUT_PATH = ROOT / "template_inspection.json"


def clean(text: str) -> str:
    return text.replace("\r", "\\r").replace("\n", "\\n").strip()


def main() -> None:
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    doc = word.Documents.Open(str(TEMPLATE_PATH))
    try:
        paragraphs = []
        for idx, para in enumerate(doc.Paragraphs, start=1):
            text = clean(para.Range.Text)
            if text:
                paragraphs.append(
                    {
                        "index": idx,
                        "text": text,
                        "style": str(para.Range.Style),
                    }
                )

        tables = []
        for t_idx, table in enumerate(doc.Tables, start=1):
            rows = table.Rows.Count
            cols = table.Columns.Count
            cells = []
            for r in range(1, rows + 1):
                row_vals = []
                for c in range(1, cols + 1):
                    try:
                        row_vals.append(clean(table.Cell(r, c).Range.Text))
                    except Exception:
                        row_vals.append("")
                cells.append(row_vals)
            tables.append({"index": t_idx, "rows": rows, "cols": cols, "cells": cells})

        payload = {"paragraphs": paragraphs, "tables": tables}
        OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote: {OUTPUT_PATH}")
        print(f"paragraphs: {len(paragraphs)}")
        print(f"tables: {len(tables)}")
    finally:
        doc.Close(False)
        word.Quit()


if __name__ == "__main__":
    main()
