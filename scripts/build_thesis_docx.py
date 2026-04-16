from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import win32com.client
from win32com.client import constants


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "docs" / "东北大学本科生毕业设计（论文）模版.docx"
OUTPUT_PATH = ROOT / "docs" / "张琪-本科毕业论文-定稿.docx"
TEMP_OUTPUT_PATH = ROOT / "docs" / "张琪-本科毕业论文-构建中.docx"

METADATA = {
    "title_cn": "基于语义描述桥接的多模态RAG系统设计与实现",
    "title_en": "Design and Implementation of a Multimodal RAG System Based on Semantic Description Bridging",
    "college": "计算机科学与工程学院",
    "major": "计算机科学与技术",
    "student_id": "20225928",
    "student_name_cn": "张琪",
    "student_name_en": "Zhang Qi",
    "advisor_cn": "吴刚 教授",
    "advisor_en_name": "Wu Gang",
    "advisor_en_title": "Professor",
    "date_cn": "2026年6月",
    "date_en": "June 2026",
}

CHAPTER_FILES = [
    ROOT / "chapter_1_intro.md",
    ROOT / "chapter_2_related_tech.md",
    ROOT / "chapter_3_analysis.md",
    ROOT / "chapter_4_design.md",
    ROOT / "chapter_5_implementation.md",
    ROOT / "chapter_6_experiments.md",
    ROOT / "chapter_7_conclusion.md",
]

FRONT_MATTER_PATH = ROOT / "front_matter.md"
REFERENCES_PATH = ROOT / "references.md"

WD_STYLE_HEADING_1 = -2
WD_STYLE_HEADING_2 = -3
WD_STYLE_HEADING_3 = -4
WD_STYLE_NORMAL = -1
WD_ALIGN_LEFT = 0
WD_ALIGN_CENTER = 1
WD_ALIGN_JUSTIFY = 3
WD_LINE_SPACE_EXACTLY = 4
WD_OUTLINE_LEVEL_1 = 1
WD_OUTLINE_LEVEL_2 = 2
WD_OUTLINE_LEVEL_3 = 3
WD_OUTLINE_LEVEL_BODY = 10
WD_PAGE_BREAK = 7
WD_SECTION_BREAK_NEXT_PAGE = 2
WD_SEPARATE_BY_TABS = 1
WD_ALIGN_ROW_CENTER = 1
WD_CELL_ALIGN_VERTICAL_CENTER = 1
WD_HEADER_FOOTER_PRIMARY = 1
WD_HEADER_FOOTER_FIRST_PAGE = 2
WD_HEADER_FOOTER_EVEN_PAGES = 3
WD_PAGE_NUMBER_ROMAN = 1
WD_PAGE_NUMBER_ARABIC = 0
WD_TAB_ALIGN_RIGHT = 2
WD_TAB_LEADER_SPACES = 0
WD_BORDER_BOTTOM = -3
WD_LINE_STYLE_SINGLE = 1
WD_GO_TO_PAGE = 1
WD_GO_TO_ABSOLUTE = 1
WD_INFO_PAGE_NUMBER = 3
POINTS_PER_CM = 28.3464567
HEADER_TEXT = "东北大学本科生毕业设计（论文）"
CITATION_RE = re.compile(r"\[(\d+(?:[-,]\d+)*)\]")


@dataclass
class Block:
    kind: str
    text: str = ""
    rows: list[list[str]] | None = None


def clean_line(text: str) -> str:
    return text.rstrip("\r\n")


def clean_word_text(text: str) -> str:
    return text.replace("\r", " ").replace("\n", " ").replace("\x07", " ").strip()


def sanitize_inline(text: str) -> str:
    return text.replace("`", "").replace("**", "")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_section(text: str, start_heading: str, end_heading: str | None = None) -> str:
    start = text.index(start_heading) + len(start_heading)
    tail = text[start:]
    if end_heading and end_heading in tail:
        tail = tail[: tail.index(end_heading)]
    return tail.strip()


def split_front_matter() -> tuple[str, str, str, str, str]:
    text = read_text(FRONT_MATTER_PATH)
    abstract_cn = extract_section(text, "# 中文摘要", "# Abstract")
    abstract_en = extract_section(text, "# Abstract", "# 致谢")
    acknowledgement = extract_section(text, "# 致谢", None)

    kw_cn_match = re.search(r"\*\*关键词：\*\*\s*(.+)", abstract_cn)
    kw_en_match = re.search(r"\*\*Keywords:\*\*\s*(.+)", abstract_en)
    if not kw_cn_match or not kw_en_match:
        raise RuntimeError("front_matter.md 中未找到关键词行")

    keywords_cn = kw_cn_match.group(1).strip()
    keywords_en = kw_en_match.group(1).strip()

    abstract_cn = re.sub(r"\*\*关键词：\*\*.+", "", abstract_cn).strip()
    abstract_en = re.sub(r"\*\*Keywords:\*\*.+", "", abstract_en).strip()
    return abstract_cn, keywords_cn, abstract_en, keywords_en, acknowledgement


def parse_markdown(text: str) -> list[Block]:
    lines = [clean_line(line) for line in text.splitlines()]
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if line.startswith("|") and line.endswith("|"):
            table_lines = []
            while i < len(lines):
                current = lines[i].strip()
                if current.startswith("|") and current.endswith("|"):
                    table_lines.append(current)
                    i += 1
                else:
                    break
            rows = []
            for idx, table_line in enumerate(table_lines):
                if idx == 1 and re.fullmatch(r"\|\s*[-:| ]+\|", table_line):
                    continue
                cells = [cell.strip() for cell in table_line.strip("|").split("|")]
                rows.append(cells)
            if rows:
                blocks.append(Block(kind="table", rows=rows))
            continue

        if line.startswith("# "):
            blocks.append(Block(kind="h1", text=line[2:].strip()))
        elif line.startswith("## "):
            blocks.append(Block(kind="h2", text=line[3:].strip()))
        elif line.startswith("### "):
            blocks.append(Block(kind="h3", text=line[4:].strip()))
        elif re.match(r"^\d+\.\s+", line):
            blocks.append(Block(kind="numbered", text=line))
        elif line.startswith("- "):
            blocks.append(Block(kind="bullet", text=line[2:].strip()))
        else:
            blocks.append(Block(kind="p", text=line))
        i += 1
    return blocks


def parse_chapters() -> list[Block]:
    blocks: list[Block] = []
    for path in CHAPTER_FILES:
        blocks.extend(parse_markdown(read_text(path)))
    blocks.append(Block(kind="h1", text="参考文献"))
    refs = [line.strip() for line in read_text(REFERENCES_PATH).splitlines() if line.strip() and not line.startswith("#")]
    for ref in refs:
        blocks.append(Block(kind="reference", text=ref))
    _, _, _, _, acknowledgement = split_front_matter()
    blocks.append(Block(kind="h1", text="致谢"))
    for para in [p.strip() for p in acknowledgement.split("\n\n") if p.strip()]:
        blocks.append(Block(kind="p", text=para))
    return blocks


def find_paragraph(doc, marker: str, occurrence: int = 1):
    count = 0
    for para in doc.Paragraphs:
        text = str(para.Range.Text).replace("\r", "").replace("\x07", "").strip()
        if marker in text:
            count += 1
            if count == occurrence:
                return para
    raise RuntimeError(f"未找到段落标记: {marker}")


def set_paragraph_text(para, text: str) -> None:
    para.Range.Text = text + "\r"


def set_cell_text(cell, text: str) -> None:
    cell.Range.Text = text


def format_range_font(rng, font_name: str, size: int, bold: bool = False, alignment: int | None = None) -> None:
    try:
        rng.Font.NameFarEast = font_name
    except Exception:
        pass
    rng.Font.Name = font_name
    rng.Font.Size = size
    rng.Font.Bold = -1 if bold else 0
    if alignment is not None:
        rng.ParagraphFormat.Alignment = alignment


def set_body_format(rng) -> None:
    rng.Font.NameFarEast = "宋体"
    rng.Font.Name = "Times New Roman"
    rng.Font.Size = 12
    rng.Font.Bold = 0
    rng.ParagraphFormat.LineSpacingRule = WD_LINE_SPACE_EXACTLY
    rng.ParagraphFormat.LineSpacing = 23
    rng.ParagraphFormat.FirstLineIndent = 2 * 12
    rng.ParagraphFormat.Alignment = WD_ALIGN_JUSTIFY
    rng.ParagraphFormat.SpaceBefore = 0
    rng.ParagraphFormat.SpaceAfter = 0


def apply_inline_formatting(para, text: str) -> None:
    for match in CITATION_RE.finditer(text):
        citation_range = para.Range.Duplicate
        citation_range.SetRange(para.Range.Start + match.start(), para.Range.Start + match.end())
        citation_range.Font.Superscript = True


def style_keywords_prefix(para, prefix: str, font_name_far_east: str, font_name: str) -> None:
    prefix_range = para.Range.Duplicate
    prefix_range.SetRange(para.Range.Start, para.Range.Start + len(prefix))
    try:
        prefix_range.Font.NameFarEast = font_name_far_east
    except Exception:
        pass
    prefix_range.Font.Name = font_name
    prefix_range.Font.Size = 12
    prefix_range.Font.Bold = -1


def is_caption(text: str) -> bool:
    stripped = sanitize_inline(text).strip()
    return bool(re.match(r"^(表|图)\s*\d+-\d+", stripped))


def end_range(doc):
    end = doc.Content.End - 1
    return doc.Range(end, end)


def page_range(doc, page_number: int):
    start_range = doc.GoTo(What=WD_GO_TO_PAGE, Which=WD_GO_TO_ABSOLUTE, Count=page_number)
    start = start_range.Start
    total_pages = doc.ComputeStatistics(2)
    if page_number < total_pages:
        next_range = doc.GoTo(What=WD_GO_TO_PAGE, Which=WD_GO_TO_ABSOLUTE, Count=page_number + 1)
        return doc.Range(start, next_range.Start - 1)
    return doc.Range(start, doc.Content.End)


def insert_text(doc, text: str):
    rng = end_range(doc)
    start = rng.Start
    rng.InsertAfter(text)
    return doc.Range(start, start + len(text))


def insert_paragraph(doc, text: str):
    return insert_text(doc, text + "\r").Paragraphs(1)


def render_heading(doc, text: str, level: int, section_break_before: bool = False) -> None:
    if section_break_before:
        end_range(doc).InsertBreak(WD_SECTION_BREAK_NEXT_PAGE)
    para = insert_paragraph(doc, sanitize_inline(text))
    if level == 1:
        para.Range.Style = WD_STYLE_HEADING_1
        format_range_font(para.Range, "黑体", 18, bold=True, alignment=WD_ALIGN_LEFT)
        para.OutlineLevel = WD_OUTLINE_LEVEL_1
        para.Range.ParagraphFormat.SpaceBefore = 14
        para.Range.ParagraphFormat.SpaceAfter = 8
    elif level == 2:
        para.Range.Style = WD_STYLE_HEADING_2
        format_range_font(para.Range, "黑体", 14, bold=True, alignment=WD_ALIGN_LEFT)
        para.OutlineLevel = WD_OUTLINE_LEVEL_2
        para.Range.ParagraphFormat.SpaceBefore = 8
        para.Range.ParagraphFormat.SpaceAfter = 8
    else:
        para.Range.Style = WD_STYLE_HEADING_3
        format_range_font(para.Range, "黑体", 12, bold=True, alignment=WD_ALIGN_LEFT)
        para.OutlineLevel = WD_OUTLINE_LEVEL_3
        para.Range.ParagraphFormat.SpaceBefore = 6
        para.Range.ParagraphFormat.SpaceAfter = 6


def render_body_paragraph(doc, text: str) -> None:
    clean_text = sanitize_inline(text)
    para = insert_paragraph(doc, clean_text)
    para.Range.Style = WD_STYLE_NORMAL
    set_body_format(para.Range)
    apply_inline_formatting(para, clean_text)


def render_caption(doc, text: str) -> None:
    clean_text = sanitize_inline(text)
    para = insert_paragraph(doc, clean_text)
    para.Range.Style = WD_STYLE_NORMAL
    set_body_format(para.Range)
    para.Range.ParagraphFormat.Alignment = WD_ALIGN_CENTER
    para.Range.ParagraphFormat.FirstLineIndent = 0


def render_numbered(doc, text: str) -> None:
    clean_text = sanitize_inline(text)
    para = insert_paragraph(doc, clean_text)
    para.Range.Style = WD_STYLE_NORMAL
    set_body_format(para.Range)
    para.Range.ParagraphFormat.FirstLineIndent = 0
    para.Range.ParagraphFormat.LeftIndent = 0
    apply_inline_formatting(para, clean_text)


def render_bullet(doc, text: str) -> None:
    clean_text = "• " + sanitize_inline(text)
    para = insert_paragraph(doc, clean_text)
    para.Range.Style = WD_STYLE_NORMAL
    set_body_format(para.Range)
    para.Range.ParagraphFormat.FirstLineIndent = 0
    para.Range.ParagraphFormat.LeftIndent = 0
    apply_inline_formatting(para, clean_text)


def render_reference(doc, text: str) -> None:
    clean_text = sanitize_inline(text)
    para = insert_paragraph(doc, clean_text)
    para.Range.Style = WD_STYLE_NORMAL
    set_body_format(para.Range)
    para.Range.ParagraphFormat.FirstLineIndent = -24
    para.Range.ParagraphFormat.LeftIndent = 24


def render_table(doc, rows: list[list[str]]) -> None:
    if not rows:
        return
    tsv = "\r".join("\t".join(row) for row in rows) + "\r"
    rng = insert_text(doc, tsv)
    table = rng.ConvertToTable(
        Separator=WD_SEPARATE_BY_TABS,
        NumRows=len(rows),
        NumColumns=max(len(row) for row in rows),
    )
    table.Borders.Enable = True
    table.Rows.Alignment = WD_ALIGN_ROW_CENTER
    table.Range.Font.NameFarEast = "宋体"
    table.Range.Font.Name = "Times New Roman"
    table.Range.Font.Size = 10.5
    table.Range.ParagraphFormat.Alignment = WD_ALIGN_CENTER
    for row_idx in range(1, table.Rows.Count + 1):
        for col_idx in range(1, table.Columns.Count + 1):
            cell = table.Cell(row_idx, col_idx)
            cell.VerticalAlignment = WD_CELL_ALIGN_VERTICAL_CENTER
            if row_idx == 1:
                cell.Range.Font.Bold = True
    insert_text(doc, "\r")


def render_blocks(doc, blocks: Iterable[Block]) -> None:
    first_h1 = True
    for block in blocks:
        if block.kind == "h1":
            render_heading(doc, block.text, 1, section_break_before=not first_h1)
            first_h1 = False
        elif block.kind == "h2":
            render_heading(doc, block.text, 2)
        elif block.kind == "h3":
            render_heading(doc, block.text, 3)
        elif block.kind == "p":
            if is_caption(block.text):
                render_caption(doc, block.text)
            else:
                render_body_paragraph(doc, block.text)
        elif block.kind == "numbered":
            render_numbered(doc, block.text)
        elif block.kind == "bullet":
            render_bullet(doc, block.text)
        elif block.kind == "reference":
            render_reference(doc, block.text)
        elif block.kind == "table":
            render_table(doc, block.rows or [])


def replace_cover(doc) -> None:
    table = doc.Tables(1)
    set_cell_text(table.Cell(1, 2), METADATA["title_cn"])
    set_cell_text(table.Cell(2, 2), METADATA["college"])
    set_cell_text(table.Cell(3, 2), METADATA["major"])
    set_cell_text(table.Cell(4, 2), METADATA["student_name_cn"])
    set_cell_text(table.Cell(5, 2), METADATA["advisor_cn"])
    set_cell_text(table.Cell(8, 1), "二○二六年 六月")

    replacements = {
        "基于NeRF技术的三维重建系统的设计与实现": METADATA["title_cn"],
        "学 院 名 称  ：XXX XXX": f"学 院 名 称  ：{METADATA['college']}",
        "专 业 名 称  ：XXX XXX": f"专 业 名 称  ：{METADATA['major']}",
        "学 生 姓 名  ：XXX": f"学 生 姓 名  ：{METADATA['student_name_cn']}",
        "指 导 教 师  ：XXX  教授": f"指 导 教 师  ：{METADATA['advisor_cn']}",
        "XXX  职称（如有双导师）": "",
        "20XX年6月": METADATA["date_cn"],
        "Design and Implementation of 3D Reconstruction System Based on NeRF": METADATA["title_en"],
        "by Zhang San": f"by {METADATA['student_name_en']}",
        "Professor": METADATA["advisor_en_title"],
        "Li Si": METADATA["advisor_en_name"],
        "Associate Supervisor:": "",
        "Senior Engineer": "",
        "Wang Wu": "",
        "June 20XX": METADATA["date_en"],
        "学号________________                                密级________________": f"学号 {METADATA['student_id']}                                密级 公开",
    }

    for para in doc.Paragraphs:
        text = str(para.Range.Text).replace("\r", "").replace("\x07", "").strip()
        for source, target in replacements.items():
            if text == source:
                set_paragraph_text(para, target)
                break


def rebuild_after_statement(doc) -> None:
    abstract_marker = find_paragraph(doc, "摘  要")
    delete_rng = doc.Range(abstract_marker.Range.Start, doc.Content.End - 1)
    delete_rng.Delete()

    abstract_cn, keywords_cn, abstract_en, keywords_en, _ = split_front_matter()

    # Reuse an already-empty tail section from the template when present,
    # otherwise create a new section for the front matter.
    if first_nonempty_paragraph_text(doc.Sections(doc.Sections.Count)):
        end_range(doc).InsertBreak(WD_SECTION_BREAK_NEXT_PAGE)
    abs_cn_para = insert_paragraph(doc, "摘  要")
    format_range_font(abs_cn_para.Range, "黑体", 18, bold=True, alignment=WD_ALIGN_CENTER)
    abs_cn_para.OutlineLevel = WD_OUTLINE_LEVEL_BODY
    for para_text in [p.strip() for p in abstract_cn.split("\n\n") if p.strip()]:
        render_body_paragraph(doc, para_text)
    kw_para = insert_paragraph(doc, f"关键词：{keywords_cn}")
    set_body_format(kw_para.Range)
    kw_para.Range.ParagraphFormat.Alignment = WD_ALIGN_LEFT
    kw_para.Range.ParagraphFormat.FirstLineIndent = 0
    style_keywords_prefix(kw_para, "关键词：", "黑体", "宋体")

    end_range(doc).InsertBreak(WD_PAGE_BREAK)

    abs_para = insert_paragraph(doc, "ABSTRACT")
    format_range_font(abs_para.Range, "Times New Roman", 18, bold=True, alignment=WD_ALIGN_CENTER)
    abs_para.OutlineLevel = WD_OUTLINE_LEVEL_BODY
    for para_text in [p.strip() for p in abstract_en.split("\n\n") if p.strip()]:
        para = insert_paragraph(doc, para_text)
        para.Range.Font.Name = "Times New Roman"
        para.Range.Font.Size = 12
        para.Range.Font.Bold = 0
        para.Range.ParagraphFormat.LineSpacingRule = WD_LINE_SPACE_EXACTLY
        para.Range.ParagraphFormat.LineSpacing = 23
        para.Range.ParagraphFormat.Alignment = WD_ALIGN_JUSTIFY
        para.Range.ParagraphFormat.FirstLineIndent = 2 * 12
        para.Range.ParagraphFormat.SpaceBefore = 0
        para.Range.ParagraphFormat.SpaceAfter = 0
    key_para = insert_paragraph(doc, f"Keywords: {keywords_en}")
    key_para.Range.Font.Name = "Times New Roman"
    key_para.Range.Font.Size = 12
    key_para.Range.Font.Bold = 0
    key_para.Range.ParagraphFormat.Alignment = WD_ALIGN_LEFT
    key_para.Range.ParagraphFormat.FirstLineIndent = 0
    key_para.Range.ParagraphFormat.LineSpacingRule = WD_LINE_SPACE_EXACTLY
    key_para.Range.ParagraphFormat.LineSpacing = 23
    style_keywords_prefix(key_para, "Keywords:", "Times New Roman", "Times New Roman")

    end_range(doc).InsertBreak(WD_PAGE_BREAK)

    toc_heading = insert_paragraph(doc, "目  录")
    format_range_font(toc_heading.Range, "黑体", 18, bold=True, alignment=WD_ALIGN_CENTER)
    toc_heading.OutlineLevel = WD_OUTLINE_LEVEL_BODY
    toc_range = end_range(doc)
    toc_range.InsertParagraphAfter()

    end_range(doc).InsertBreak(WD_SECTION_BREAK_NEXT_PAGE)

    render_blocks(doc, parse_chapters())

    # TOC after body content is ready.
    toc_para = find_paragraph(doc, "目  录")
    toc_insert = doc.Range(toc_para.Range.End, toc_para.Range.End)
    doc.TablesOfContents.Add(
        Range=toc_insert,
        UseHeadingStyles=True,
        UpperHeadingLevel=1,
        LowerHeadingLevel=3,
        RightAlignPageNumbers=True,
        UseHyperlinks=True,
        HidePageNumbersInWeb=True,
    )

    configure_sections(doc)


def first_nonempty_paragraph_text(section) -> str:
    for para in section.Range.Paragraphs:
        text = clean_word_text(str(para.Range.Text))
        if text:
            return text
    return ""


def clear_section_header_footer(section) -> None:
    section.PageSetup.DifferentFirstPageHeaderFooter = False
    section.PageSetup.OddAndEvenPagesHeaderFooter = False
    for kind in (WD_HEADER_FOOTER_PRIMARY, WD_HEADER_FOOTER_FIRST_PAGE, WD_HEADER_FOOTER_EVEN_PAGES):
        header = section.Headers(kind)
        footer = section.Footers(kind)
        try:
            header.LinkToPrevious = False
        except Exception:
            pass
        try:
            footer.LinkToPrevious = False
        except Exception:
            pass
        header.Range.Text = ""
        footer.Range.Text = ""
        while footer.PageNumbers.Count:
            footer.PageNumbers(1).Delete()


def set_section_header(section, title: str) -> None:
    header = section.Headers(WD_HEADER_FOOTER_PRIMARY)
    header.Range.Text = f"{HEADER_TEXT}\t{title}"
    para = header.Range.Paragraphs(1)
    para.Range.Font.NameFarEast = "宋体"
    para.Range.Font.Name = "Times New Roman"
    para.Range.Font.Size = 9
    para.Range.Font.Bold = 0
    para.Range.ParagraphFormat.Alignment = WD_ALIGN_LEFT
    para.Range.ParagraphFormat.SpaceBefore = 0
    para.Range.ParagraphFormat.SpaceAfter = 0
    para.Range.ParagraphFormat.LineSpacingRule = WD_LINE_SPACE_EXACTLY
    para.Range.ParagraphFormat.LineSpacing = 12
    para.Range.ParagraphFormat.TabStops.ClearAll()
    printable_width = section.PageSetup.PageWidth - section.PageSetup.LeftMargin - section.PageSetup.RightMargin
    para.Range.ParagraphFormat.TabStops.Add(
        Position=printable_width,
        Alignment=WD_TAB_ALIGN_RIGHT,
        Leader=WD_TAB_LEADER_SPACES,
    )
    try:
        border = para.Borders(constants.wdBorderBottom)
        border.LineStyle = constants.wdLineStyleSingle
        border.LineWidth = constants.wdLineWidth050pt
    except Exception:
        try:
            border = para.Borders(WD_BORDER_BOTTOM)
            border.LineStyle = WD_LINE_STYLE_SINGLE
        except Exception:
            pass


def set_section_footer(section, number_style: int, restart: bool, start_number: int = 1) -> None:
    footer = section.Footers(WD_HEADER_FOOTER_PRIMARY)
    footer.Range.Text = ""
    while footer.PageNumbers.Count:
        footer.PageNumbers(1).Delete()
    footer.PageNumbers.RestartNumberingAtSection = True if restart else False
    if restart:
        footer.PageNumbers.StartingNumber = start_number
    footer.PageNumbers.NumberStyle = number_style
    footer.PageNumbers.Add(WD_ALIGN_CENTER)
    footer.Range.Font.NameFarEast = "宋体"
    footer.Range.Font.Name = "Times New Roman"
    footer.Range.Font.Size = 9
    footer.Range.ParagraphFormat.Alignment = WD_ALIGN_CENTER


def is_body_section_title(title: str) -> bool:
    return bool(re.match(r"^\d+\s+", title)) or title in {"参考文献", "致谢"}


def configure_sections(doc) -> None:
    titles = {index: first_nonempty_paragraph_text(doc.Sections(index)) for index in range(1, doc.Sections.Count + 1)}
    front_start = next((idx for idx, title in titles.items() if title == "摘  要"), None)
    body_start = next((idx for idx, title in titles.items() if is_body_section_title(title)), None)

    for section in doc.Sections:
        section.PageSetup.TopMargin = 2.5 * POINTS_PER_CM
        section.PageSetup.BottomMargin = 2.5 * POINTS_PER_CM
        section.PageSetup.LeftMargin = 3.0 * POINTS_PER_CM
        section.PageSetup.RightMargin = 2.5 * POINTS_PER_CM
        clear_section_header_footer(section)

    if front_start is None or body_start is None:
        return

    for index in range(1, doc.Sections.Count + 1):
        section = doc.Sections(index)
        title = titles.get(index, "")
        if index < front_start:
            continue
        if index == front_start:
            set_section_footer(section, WD_PAGE_NUMBER_ARABIC, restart=True, start_number=1)
        else:
            section.Footers(WD_HEADER_FOOTER_PRIMARY).LinkToPrevious = True
        if index >= body_start:
            set_section_header(section, title)


def delete_blank_page_before_marker(doc, marker: str) -> bool:
    marker_para = find_paragraph(doc, marker)
    marker_page = marker_para.Range.Information(WD_INFO_PAGE_NUMBER)
    if marker_page <= 1:
        return False
    previous_page = page_range(doc, marker_page - 1)
    if clean_word_text(str(previous_page.Text)):
        return False
    previous_page.Delete()
    return True


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE_PATH, TEMP_OUTPUT_PATH)

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = word.Documents.Open(str(TEMP_OUTPUT_PATH))
    try:
        replace_cover(doc)
        rebuild_after_statement(doc)
        for toc in doc.TablesOfContents:
            toc.Update()
        if delete_blank_page_before_marker(doc, "目  录"):
            for toc in doc.TablesOfContents:
                toc.Update()
        doc.Save()
    finally:
        doc.Close(True)
        word.Quit()

    shutil.copyfile(TEMP_OUTPUT_PATH, OUTPUT_PATH)
    try:
        TEMP_OUTPUT_PATH.unlink()
    except FileNotFoundError:
        pass

    print(f"built: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
