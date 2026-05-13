from __future__ import annotations

import shutil
from pathlib import Path

import win32com.client

from build_thesis_docx import (
    POINTS_PER_CM,
    WD_ALIGN_CENTER,
    WD_ALIGN_LEFT,
    WD_STYLE_NORMAL,
    format_range_font,
    insert_paragraph,
    parse_markdown,
    sanitize_inline,
    set_body_format,
)


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_PATH = ROOT / "docs" / "张琪-答辩问答-多模态RAG系统.md"
OUTPUT_PATH = ROOT / "docs" / "张琪-答辩问答-多模态RAG系统.docx"
TEMP_OUTPUT_PATH = ROOT / "docs" / "张琪-答辩问答-多模态RAG系统-构建中.docx"


def _set_page_margins(section) -> None:
    setup = section.PageSetup
    setup.TopMargin = 2.5 * POINTS_PER_CM
    setup.BottomMargin = 2.5 * POINTS_PER_CM
    setup.LeftMargin = 3.0 * POINTS_PER_CM
    setup.RightMargin = 2.5 * POINTS_PER_CM


def _set_qa_body_format(rng) -> None:
    set_body_format(rng)
    rng.ParagraphFormat.FirstLineIndent = 0
    rng.ParagraphFormat.Alignment = WD_ALIGN_LEFT


def _render_title(doc, text: str) -> None:
    para = insert_paragraph(doc, sanitize_inline(text))
    para.Range.Style = WD_STYLE_NORMAL
    format_range_font(para.Range, "黑体", 18, bold=True, alignment=WD_ALIGN_CENTER)
    para.Range.ParagraphFormat.SpaceBefore = 0
    para.Range.ParagraphFormat.SpaceAfter = 18
    para.Range.ParagraphFormat.FirstLineIndent = 0


def _render_heading(doc, text: str, level: int) -> None:
    para = insert_paragraph(doc, sanitize_inline(text))
    para.Range.Style = WD_STYLE_NORMAL
    if level == 1:
        format_range_font(para.Range, "黑体", 16, bold=True, alignment=WD_ALIGN_LEFT)
        para.Range.ParagraphFormat.SpaceBefore = 12
        para.Range.ParagraphFormat.SpaceAfter = 8
    else:
        format_range_font(para.Range, "黑体", 14, bold=True, alignment=WD_ALIGN_LEFT)
        para.Range.ParagraphFormat.SpaceBefore = 8
        para.Range.ParagraphFormat.SpaceAfter = 6
    para.Range.ParagraphFormat.FirstLineIndent = 0


def _style_label_prefix(para, label: str) -> None:
    prefix_range = para.Range.Duplicate
    prefix_range.SetRange(para.Range.Start, para.Range.Start + len(label))
    prefix_range.Font.Bold = -1
    try:
        prefix_range.Font.NameFarEast = "黑体"
    except Exception:
        pass
    prefix_range.Font.Name = "Times New Roman"


def _render_body(doc, text: str) -> None:
    clean_text = sanitize_inline(text)
    para = insert_paragraph(doc, clean_text)
    para.Range.Style = WD_STYLE_NORMAL
    _set_qa_body_format(para.Range)
    for label in ("说明：", "参考回答：", "追问提示："):
        if clean_text.startswith(label):
            _style_label_prefix(para, label)
            break


def _load_blocks():
    text = MARKDOWN_PATH.read_text(encoding="utf-8")
    return parse_markdown(text)


def build_docx() -> None:
    if not MARKDOWN_PATH.exists():
        raise FileNotFoundError(f"未找到 Markdown 源文件: {MARKDOWN_PATH}")

    if TEMP_OUTPUT_PATH.exists():
        TEMP_OUTPUT_PATH.unlink()

    blocks = _load_blocks()
    if not blocks:
        raise RuntimeError("答辩问答 Markdown 为空")

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    doc = word.Documents.Add()
    try:
        _set_page_margins(doc.Sections(1))

        title_rendered = False
        for block in blocks:
            if block.kind == "h1" and not title_rendered:
                _render_title(doc, block.text)
                title_rendered = True
            elif block.kind == "h2":
                _render_heading(doc, block.text, level=1)
            elif block.kind == "h3":
                _render_heading(doc, block.text, level=2)
            elif block.kind in {"p", "bullet", "numbered"}:
                body_text = block.text
                if block.kind == "bullet":
                    body_text = f"- {body_text}"
                _render_body(doc, body_text)

        doc.SaveAs2(str(TEMP_OUTPUT_PATH))
        doc.Close(False)
        doc = None
    finally:
        if doc is not None:
            doc.Close(False)
        word.Quit()

    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()
    shutil.move(str(TEMP_OUTPUT_PATH), str(OUTPUT_PATH))


if __name__ == "__main__":
    build_docx()
