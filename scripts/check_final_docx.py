from __future__ import annotations

import re
import shutil
from pathlib import Path

import win32com.client


ROOT = Path(__file__).resolve().parents[1]
DOCX_PATH = ROOT / "docs" / "张琪-本科毕业论文-定稿.docx"
CHECK_COPY_PATH = ROOT / "docs" / "张琪-本科毕业论文-检查副本.docx"
REFERENCE_SOURCE = ROOT / "references.md"
CHAPTER_FILES = sorted(ROOT.glob("chapter_*.md"))
EXPECTED_REFERENCE_COUNT = 40
MARKERS = [
    "基于语义描述桥接的多模态RAG系统设计与实现",
    "摘  要",
    "ABSTRACT",
    "目  录",
    "1 绪论",
    "6 实验设计与结果分析",
    "7 总结与展望",
    "参考文献",
    "致谢",
]
POINTS_PER_CM = 28.3464567
WD_GO_TO_PAGE = 1
WD_GO_TO_ABSOLUTE = 1
WD_INFO_ADJUSTED_PAGE = 1
WD_INFO_SECTION_NUMBER = 2
WD_INFO_PAGE_NUMBER = 3
WD_PAGE_NUMBER_ARABIC = 0
CITATION_RE = re.compile(r"\[(\d+(?:[-,]\d+)*)\]")
REFERENCE_RE = re.compile(r"^\[(\d+)\]\s")


def clean(text: str) -> str:
    return text.replace("\r", " ").replace("\n", " ").replace("\x07", " ").strip()


def iter_citation_numbers(token: str) -> list[int]:
    numbers: list[int] = []
    for part in token.split(","):
        if "-" in part:
            start, end = map(int, part.split("-"))
            numbers.extend(range(start, end + 1))
        else:
            numbers.append(int(part))
    return numbers


def first_nonempty_paragraph_text(section) -> str:
    for para in section.Range.Paragraphs:
        text = clean(str(para.Range.Text))
        if text:
            return text
    return ""


def count_reference_entries(doc) -> int:
    count = 0
    in_reference_section = False
    for para in doc.Paragraphs:
        text = clean(str(para.Range.Text))
        if text == "参考文献":
            in_reference_section = True
            continue
        if text == "致谢":
            break
        if in_reference_section and REFERENCE_RE.match(text):
            count += 1
    return count


def rendered_page_numbers(doc) -> list[tuple[int, int, int]]:
    total_pages = doc.ComputeStatistics(2)
    rows: list[tuple[int, int, int]] = []
    for page in range(1, total_pages + 1):
        rng = doc.GoTo(What=WD_GO_TO_PAGE, Which=WD_GO_TO_ABSOLUTE, Count=page)
        rows.append(
            (
                page,
                rng.Information(WD_INFO_SECTION_NUMBER),
                rng.Information(WD_INFO_ADJUSTED_PAGE),
            )
        )
    return rows


def section_page_number_style(section) -> int | None:
    try:
        if section.Footers(1).PageNumbers.Count:
            return int(section.Footers(1).PageNumbers.NumberStyle)
    except Exception:
        return None
    return None


def citation_summary() -> tuple[int, int, bool]:
    cited: set[int] = set()
    ordered: list[int] = []
    for path in CHAPTER_FILES:
        text = path.read_text(encoding="utf-8")
        for match in CITATION_RE.finditer(text):
            for number in iter_citation_numbers(match.group(1)):
                if number not in cited:
                    cited.add(number)
                    ordered.append(number)

    reference_numbers = []
    for line in REFERENCE_SOURCE.read_text(encoding="utf-8").splitlines():
        match = REFERENCE_RE.match(line)
        if match:
            reference_numbers.append(int(match.group(1)))

    is_sequential = ordered == list(range(1, len(reference_numbers) + 1))
    all_cited = cited == set(reference_numbers)
    return len(cited), len(reference_numbers), is_sequential and all_cited


def main() -> None:
    shutil.copyfile(DOCX_PATH, CHECK_COPY_PATH)
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    doc = word.Documents.Open(str(CHECK_COPY_PATH))
    try:
        full_text = clean(doc.Content.Text)
        print(f"exists: {DOCX_PATH.exists()}")
        print(f"sections: {doc.Sections.Count}")
        print(f"tables_of_contents: {doc.TablesOfContents.Count}")
        print(f"pages: {doc.ComputeStatistics(2)}")
        for marker in MARKERS:
            print(f"{marker}: {'yes' if marker in full_text else 'no'}")
        print(f"old_chapter_heading_present: {'yes' if '第1章 绪论' in full_text else 'no'}")
        print(f"keywords_label_present: {'yes' if 'Keywords:' in full_text else 'no'}")
        print(f"old_key_words_label_present: {'yes' if 'Key Words:' in full_text or 'Key Words：' in full_text else 'no'}")
        print(f"reference_entries_doc: {count_reference_entries(doc)}")
        cited_count, reference_count, citation_ok = citation_summary()
        print(f"reference_entries_source: {reference_count}")
        print(f"reference_entries_expected_40: {'yes' if reference_count == EXPECTED_REFERENCE_COUNT else 'no'}")
        print(f"cited_reference_count: {cited_count}")
        print(f"citations_cover_all_references: {'yes' if citation_ok else 'no'}")
        abstract_section_index = None
        body_start_index = None
        abstract_number_style = None
        abstract_restart = None
        front_sections_without_page_numbers = True
        body_footers_linked = True
        for index in range(1, doc.Sections.Count + 1):
            section = doc.Sections(index)
            title = first_nonempty_paragraph_text(section)
            footer = section.Footers(1)
            if title == "摘  要" and abstract_section_index is None:
                abstract_section_index = index
                abstract_number_style = section_page_number_style(section)
                abstract_restart = bool(footer.PageNumbers.RestartNumberingAtSection)
            if title.startswith("1 绪论"):
                body_start_index = index
            if abstract_section_index is None and section_page_number_style(section) is not None:
                front_sections_without_page_numbers = False
            if body_start_index is not None and index >= body_start_index and not bool(footer.LinkToPrevious):
                body_footers_linked = False
        if abstract_section_index is not None:
            print(f"abstract_section_index: {abstract_section_index}")
            print(f"abstract_page_number_style_is_arabic: {'yes' if abstract_number_style == WD_PAGE_NUMBER_ARABIC else 'no'}")
            print(f"abstract_footer_restarts_at_1: {'yes' if abstract_restart else 'no'}")
        print(f"front_sections_without_page_numbers: {'yes' if front_sections_without_page_numbers else 'no'}")
        if body_start_index is not None:
            print(f"body_start_section_index: {body_start_index}")
            print(f"body_footers_link_to_previous: {'yes' if body_footers_linked else 'no'}")
        for index in range(1, doc.Sections.Count + 1):
            section = doc.Sections(index)
            title = first_nonempty_paragraph_text(section)
            header = clean(section.Headers(1).Range.Text)
            footer = clean(section.Footers(1).Range.Text)
            margins = (
                round(section.PageSetup.TopMargin / POINTS_PER_CM, 2),
                round(section.PageSetup.BottomMargin / POINTS_PER_CM, 2),
                round(section.PageSetup.LeftMargin / POINTS_PER_CM, 2),
                round(section.PageSetup.RightMargin / POINTS_PER_CM, 2),
            )
            print(f"section_{index}_title: {title}")
            print(f"section_{index}_header: {header}")
            print(f"section_{index}_footer: {footer}")
            print(f"section_{index}_page_number_style: {section_page_number_style(section)}")
            print(f"section_{index}_margins_cm: {margins}")
    finally:
        doc.Close(False)
        word.Quit()
        try:
            CHECK_COPY_PATH.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
