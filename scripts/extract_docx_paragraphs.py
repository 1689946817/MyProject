from __future__ import annotations

import sys
from pathlib import Path

import win32com.client


def clean(text: str) -> str:
    return text.replace("\r", "\\r").replace("\n", "\\n").strip()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python scripts/extract_docx_paragraphs.py <docx-path> [max_paragraphs]")

    docx_path = Path(sys.argv[1]).resolve()
    max_paragraphs = int(sys.argv[2]) if len(sys.argv) > 2 else 120

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    doc = word.Documents.Open(str(docx_path))
    try:
        count = 0
        for idx, para in enumerate(doc.Paragraphs, start=1):
            text = clean(para.Range.Text)
            if text:
                print(f"{idx:>4} | {para.Range.Style} | {text}")
                count += 1
                if count >= max_paragraphs:
                    break
    finally:
        doc.Close(False)
        word.Quit()


if __name__ == "__main__":
    main()
