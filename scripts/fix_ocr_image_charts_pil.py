"""Redraw OCR-affected generation charts without matplotlib.

This fallback script exists because some local Python environments in the
workspace cannot import matplotlib reliably. It uses Pillow only and writes
new PNG/PDF files without overwriting existing charts.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
GENERATION_DIR = ROOT / "实验数据" / "生成器"

PALETTE = {
    "proposed": "#1f77b4",
    "baseline_clip": "#ff7f0e",
    "baseline_ocr": "#7f7f7f",
    "no_rag": "#4c4c4c",
}

METHOD_LABELS = {
    "proposed": {"en": "Proposed", "zh": "本文方法"},
    "baseline_clip": {"en": "Baseline-CLIP", "zh": "CLIP基线"},
    "baseline_ocr": {"en": "Baseline-OCR", "zh": "OCR基线"},
    "no_rag": {"en": "No-RAG", "zh": "无检索"},
}

METRIC_LABELS = {
    "answer_correctness": {"en": "Answer\nCorrectness", "zh": "答案\n正确性"},
    "answer_relevancy": {"en": "Answer\nRelevancy", "zh": "答案\n相关性"},
    "image_context_relevancy": {"en": "Image Context\nRelevancy", "zh": "图像上下文\n相关性"},
    "image_faithfulness": {"en": "Image\nFaithfulness", "zh": "图像\n忠实度"},
}

TITLE_LABELS = {
    "overall": {"en": "Generator Evaluation Overview", "zh": "生成器评测总览"},
    "relfaith": {"en": "Relevancy and Faithfulness Comparison", "zh": "相关性与忠实度对比"},
    "improve": {"en": "Proposed Method Gains over Baselines", "zh": "本文方法相对基线的提升"},
}

PANEL_LABELS = {
    "relevancy": {"en": "Relevancy", "zh": "相关性"},
    "faithfulness": {"en": "Faithfulness", "zh": "忠实度"},
}

AXIS_LABELS = {
    "score": {"en": "Score / Pass Rate", "zh": "得分 / 通过率"},
    "pass_rate": {"en": "Pass Rate", "zh": "通过率"},
    "gain": {"en": "Absolute Gain", "zh": "绝对提升"},
}

GRID_COLOR = "#D9E2EC"
AXIS_COLOR = "#374151"
TEXT_COLOR = "#111827"
BG_COLOR = "white"


def resolve_analysis_dirname(suffix: str | None = None) -> str:
    if suffix is None:
        return "analysis"
    cleaned = suffix.strip().strip("_")
    if not cleaned:
        return "analysis"
    return f"analysis_{cleaned}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Redraw OCR-affected generation charts with Pillow only."
    )
    parser.add_argument(
        "--analysis-dir-suffix",
        default=None,
        help="Optional suffix for the analysis output directory, e.g. '2' -> analysis_2.",
    )
    parser.add_argument(
        "--version-suffix",
        default="v3",
        help="Suffix appended to generated chart basenames. Defaults to 'v3'.",
    )
    return parser.parse_args()


def load_summaries() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(GENERATION_DIR.glob("*_scored.summary.json")):
        method = path.name.replace("_results_subset100_scored.summary.json", "")
        payload = json.loads(path.read_text(encoding="utf-8"))
        row = {
            "method": method,
            "answer_correctness": payload["answer_correctness"]["avg_score"],
            "answer_relevancy": payload["answer_relevancy"]["pass_rate"],
            "image_context_relevancy": payload.get("image_context_relevancy", {}).get("pass_rate"),
            "image_faithfulness": payload.get("image_faithfulness", {}).get("pass_rate"),
        }
        if method in {"baseline_ocr", "no_rag"}:
            row["image_context_relevancy"] = None
            row["image_faithfulness"] = None
        rows.append(row)
    return rows


class Fonts:
    def __init__(self, locale: str) -> None:
        candidates = [
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/msyhbd.ttc"),
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]
        font_path = next((path for path in candidates if path.exists()), None)
        if font_path is None:
            self.title = ImageFont.load_default()
            self.subtitle = ImageFont.load_default()
            self.label = ImageFont.load_default()
            self.tick = ImageFont.load_default()
            self.small = ImageFont.load_default()
            return
        title_name = str(font_path)
        self.title = ImageFont.truetype(title_name, 30 if locale == "en" else 28)
        self.subtitle = ImageFont.truetype(title_name, 22 if locale == "en" else 20)
        self.label = ImageFont.truetype(title_name, 18 if locale == "en" else 17)
        self.tick = ImageFont.truetype(title_name, 16 if locale == "en" else 15)
        self.small = ImageFont.truetype(title_name, 14 if locale == "en" else 13)


def label_for_method(method: str, locale: str) -> str:
    return METHOD_LABELS[method][locale]


def metric_label(metric: str, locale: str) -> str:
    return METRIC_LABELS[metric][locale]


def save_image(img: Image.Image, output_dir: Path, basename: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / f"{basename}.png"
    pdf_path = output_dir / f"{basename}.pdf"
    img.save(png_path)
    img.convert("RGB").save(pdf_path, "PDF", resolution=300.0)


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: str = TEXT_COLOR,
    spacing: int = 4,
) -> None:
    draw.multiline_text(xy, text, font=font, fill=fill, anchor="mm", align="center", spacing=spacing)


def draw_left_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: str = TEXT_COLOR,
    spacing: int = 4,
) -> None:
    draw.multiline_text(xy, text, font=font, fill=fill, anchor="lm", align="left", spacing=spacing)


def value_to_y(value: float, top: int, bottom: int, min_value: float, max_value: float) -> float:
    usable_height = bottom - top
    if max_value == min_value:
        return float(bottom)
    ratio = (value - min_value) / (max_value - min_value)
    return bottom - ratio * usable_height


def draw_legend(
    draw: ImageDraw.ImageDraw,
    methods: Iterable[str],
    locale: str,
    fonts: Fonts,
    x_start: int,
    y: int,
    item_gap: int = 26,
) -> None:
    x = x_start
    for method in methods:
        draw.rounded_rectangle((x, y - 8, x + 18, y + 10), radius=3, fill=PALETTE[method])
        x += 28
        label = label_for_method(method, locale)
        draw_left_text(draw, (x, y + 1), label, fonts.small)
        bbox = draw.textbbox((0, 0), label, font=fonts.small)
        x += (bbox[2] - bbox[0]) + item_gap


def draw_numeric_grid(
    draw: ImageDraw.ImageDraw,
    left: int,
    right: int,
    top: int,
    bottom: int,
    min_value: float,
    max_value: float,
    fonts: Fonts,
    step: float,
) -> None:
    tick = min_value
    while tick <= max_value + 1e-9:
        y = value_to_y(tick, top, bottom, min_value, max_value)
        draw.line((left, y, right, y), fill=GRID_COLOR, width=1)
        draw.text((left - 12, y), f"{tick:.1f}", font=fonts.small, fill=AXIS_COLOR, anchor="rm")
        tick = round(tick + step, 10)
    draw.line((left, top, left, bottom), fill=AXIS_COLOR, width=2)
    draw.line((left, bottom, right, bottom), fill=AXIS_COLOR, width=2)


def draw_grouped_bars_panel(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    title: str,
    ylabel: str,
    categories: list[str],
    category_labels: list[str],
    methods: list[str],
    values_by_category: list[dict[str, float | None]],
    locale: str,
    fonts: Fonts,
    min_value: float = 0.0,
    max_value: float = 1.0,
    step: float = 0.2,
) -> None:
    left, top, right, bottom = bounds
    plot_top = top + 54
    plot_bottom = bottom - 92
    plot_left = left + 72
    plot_right = right - 28

    draw_centered_text(draw, ((left + right) / 2, top + 16), title, fonts.subtitle)
    draw_numeric_grid(draw, plot_left, plot_right, plot_top, plot_bottom, min_value, max_value, fonts, step)
    draw_centered_text(
        draw,
        (left + 18, (plot_top + plot_bottom) / 2),
        ylabel,
        fonts.small,
    )

    num_categories = len(categories)
    category_width = (plot_right - plot_left) / max(num_categories, 1)
    for idx, category in enumerate(categories):
        cat_center = plot_left + category_width * (idx + 0.5)
        present_methods = [m for m in methods if values_by_category[idx].get(m) is not None]
        if present_methods:
            group_width = min(160.0, category_width * 0.78)
            bar_width = group_width / max(len(present_methods), 1) * 0.72
            gap = group_width / max(len(present_methods), 1) * 0.28
            x = cat_center - group_width / 2
            for method in present_methods:
                value = values_by_category[idx][method]
                if value is None:
                    continue
                bar_left = x + gap / 2
                bar_right = bar_left + bar_width
                y_top = value_to_y(float(value), plot_top, plot_bottom, min_value, max_value)
                draw.rounded_rectangle((bar_left, y_top, bar_right, plot_bottom), radius=4, fill=PALETTE[method])
                draw_centered_text(draw, ((bar_left + bar_right) / 2, y_top - 14), f"{value:.2f}", fonts.small)
                x += group_width / max(len(present_methods), 1)
        draw_centered_text(draw, (cat_center, plot_bottom + 36), category_labels[idx], fonts.tick)


def draw_improvement_panel(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    title: str,
    ylabel: str,
    categories: list[str],
    category_labels: list[str],
    methods: list[str],
    values_by_category: list[dict[str, float | None]],
    locale: str,
    fonts: Fonts,
) -> None:
    left, top, right, bottom = bounds
    plot_top = top + 54
    plot_bottom = bottom - 92
    plot_left = left + 72
    plot_right = right - 28

    numeric_values = [float(v) for row in values_by_category for v in row.values() if v is not None]
    min_value = min(numeric_values + [0.0])
    max_value = max(numeric_values + [0.0])
    extent = max(abs(min_value), abs(max_value), 0.05)
    min_value = -extent * 1.15
    max_value = extent * 1.15
    step = 0.2 if extent > 0.4 else 0.1 if extent > 0.2 else 0.05

    draw_centered_text(draw, ((left + right) / 2, top + 16), title, fonts.subtitle)
    draw_numeric_grid(draw, plot_left, plot_right, plot_top, plot_bottom, min_value, max_value, fonts, step)
    zero_y = value_to_y(0.0, plot_top, plot_bottom, min_value, max_value)
    draw.line((plot_left, zero_y, plot_right, zero_y), fill=AXIS_COLOR, width=2)
    draw_centered_text(draw, (left + 18, (plot_top + plot_bottom) / 2), ylabel, fonts.small)

    num_categories = len(categories)
    category_width = (plot_right - plot_left) / max(num_categories, 1)
    for idx, _category in enumerate(categories):
        cat_center = plot_left + category_width * (idx + 0.5)
        present_methods = [m for m in methods if values_by_category[idx].get(m) is not None]
        if present_methods:
            group_width = min(170.0, category_width * 0.82)
            slot_width = group_width / max(len(present_methods), 1)
            bar_width = slot_width * 0.72
            x = cat_center - group_width / 2
            for method in present_methods:
                value = float(values_by_category[idx][method])
                y_value = value_to_y(value, plot_top, plot_bottom, min_value, max_value)
                bar_left = x + slot_width * 0.14
                bar_right = bar_left + bar_width
                top_y = min(zero_y, y_value)
                bottom_y = max(zero_y, y_value)
                draw.rounded_rectangle((bar_left, top_y, bar_right, bottom_y), radius=4, fill=PALETTE[method])
                label_y = top_y - 14 if value >= 0 else bottom_y + 14
                draw_centered_text(draw, ((bar_left + bar_right) / 2, label_y), f"{value:.3f}", fonts.small)
                x += slot_width
        draw_centered_text(draw, (cat_center, plot_bottom + 36), category_labels[idx], fonts.tick)


def render_overall_chart(rows: list[dict], methods: list[str], locale: str, output_dir: Path, basename: str) -> None:
    img = Image.new("RGB", (1440, 760), BG_COLOR)
    draw = ImageDraw.Draw(img)
    fonts = Fonts(locale)
    draw_centered_text(draw, (720, 42), TITLE_LABELS["overall"][locale], fonts.title)
    draw_legend(draw, methods, locale, fonts, 430, 88)

    metrics = [
        "answer_correctness",
        "answer_relevancy",
        "image_context_relevancy",
        "image_faithfulness",
    ]
    row_map = {row["method"]: row for row in rows}
    values_by_category = []
    for metric in metrics:
        values_by_category.append({method: row_map[method].get(metric) for method in methods if method in row_map})
    draw_grouped_bars_panel(
        draw,
        (40, 120, 1400, 720),
        "",
        AXIS_LABELS["score"][locale],
        metrics,
        [metric_label(metric, locale) for metric in metrics],
        methods,
        values_by_category,
        locale,
        fonts,
    )
    save_image(img, output_dir, basename)


def render_relevancy_faithfulness_chart(rows: list[dict], methods: list[str], locale: str, output_dir: Path, basename: str) -> None:
    img = Image.new("RGB", (1680, 760), BG_COLOR)
    draw = ImageDraw.Draw(img)
    fonts = Fonts(locale)
    draw_centered_text(draw, (840, 42), TITLE_LABELS["relfaith"][locale], fonts.title)
    draw_legend(draw, methods, locale, fonts, 520, 88)
    row_map = {row["method"]: row for row in rows}

    left_metrics = ["answer_relevancy", "image_context_relevancy"]
    left_values = [{method: row_map[method].get(metric) for method in methods if method in row_map} for metric in left_metrics]
    draw_grouped_bars_panel(
        draw,
        (30, 120, 825, 720),
        PANEL_LABELS["relevancy"][locale],
        AXIS_LABELS["pass_rate"][locale],
        left_metrics,
        [metric_label(metric, locale) for metric in left_metrics],
        methods,
        left_values,
        locale,
        fonts,
    )

    right_metrics = ["image_faithfulness"]
    right_values = [{method: row_map[method].get("image_faithfulness") for method in methods if method in row_map}]
    draw_grouped_bars_panel(
        draw,
        (855, 120, 1650, 720),
        PANEL_LABELS["faithfulness"][locale],
        AXIS_LABELS["pass_rate"][locale],
        right_metrics,
        [metric_label("image_faithfulness", locale)],
        methods,
        right_values,
        locale,
        fonts,
    )
    save_image(img, output_dir, basename)


def render_improvement_chart(rows: list[dict], methods: list[str], locale: str, output_dir: Path, basename: str) -> None:
    img = Image.new("RGB", (1500, 760), BG_COLOR)
    draw = ImageDraw.Draw(img)
    fonts = Fonts(locale)
    compare_methods = [method for method in methods if method != "proposed"]
    draw_centered_text(draw, (750, 42), TITLE_LABELS["improve"][locale], fonts.title)
    draw_legend(draw, compare_methods, locale, fonts, 520, 88)

    row_map = {row["method"]: row for row in rows}
    proposed = row_map["proposed"]
    metrics = [
        "answer_correctness",
        "answer_relevancy",
        "image_context_relevancy",
        "image_faithfulness",
    ]
    values_by_category = []
    for metric in metrics:
        category_values: dict[str, float | None] = {}
        for method in compare_methods:
            lhs = proposed.get(metric)
            rhs = row_map[method].get(metric)
            if lhs is None or rhs is None:
                category_values[method] = None
            else:
                category_values[method] = float(lhs) - float(rhs)
        values_by_category.append(category_values)

    draw_improvement_panel(
        draw,
        (40, 120, 1460, 720),
        "",
        AXIS_LABELS["gain"][locale],
        metrics,
        [metric_label(metric, locale).replace("\n", " ") for metric in metrics],
        compare_methods,
        values_by_category,
        locale,
        fonts,
    )
    save_image(img, output_dir, basename)


def main() -> None:
    args = parse_args()
    rows = load_summaries()
    analysis_dirname = resolve_analysis_dirname(args.analysis_dir_suffix)
    variants = {
        "with_ocr": ["proposed", "baseline_clip", "baseline_ocr", "no_rag"],
        "without_ocr": ["proposed", "baseline_clip", "no_rag"],
    }

    generated: list[Path] = []
    for locale in ("en", "zh"):
        output_dir = GENERATION_DIR / analysis_dirname / f"figures_{locale}"
        for suffix, methods in variants.items():
            basename = f"generation_overall_metrics_{suffix}_{args.version_suffix}"
            render_overall_chart(rows, methods, locale, output_dir, basename)
            generated.append(output_dir / f"{basename}.png")
            generated.append(output_dir / f"{basename}.pdf")

            basename = f"generation_relevancy_faithfulness_{suffix}_{args.version_suffix}"
            render_relevancy_faithfulness_chart(rows, methods, locale, output_dir, basename)
            generated.append(output_dir / f"{basename}.png")
            generated.append(output_dir / f"{basename}.pdf")

            basename = f"generation_improvement_{suffix}_{args.version_suffix}"
            render_improvement_chart(rows, methods, locale, output_dir, basename)
            generated.append(output_dir / f"{basename}.png")
            generated.append(output_dir / f"{basename}.pdf")

    print(f"Generated {len(generated)} files under {analysis_dirname}.")
    for path in generated:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
