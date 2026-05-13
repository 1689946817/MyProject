"""Generate v3 charts that exclude OCR from image-related metric comparisons.

OCR baseline does not provide image context to the answer model, so its
image_context_relevancy and image_faithfulness scores (only 3/100 samples
evaluated) are meaningless. This script re-draws affected charts with OCR
image metrics set to NaN, using _v3 suffix to avoid overwriting existing files.

Affected charts:
  - generation_overall_metrics_with_ocr  (OCR image bars disappear)
  - generation_relevancy_faithfulness_with_ocr (OCR excluded from image panels)
  - generation_improvement_with_ocr (OCR image delta bars disappear)

Charts NOT affected (answer_correctness only, no image metrics):
  - generation_domain_correctness_*
  - generation_qtype_correctness_*
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import matplotlib.font_manager as fm
from matplotlib.patches import Patch
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

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


def detect_chinese_font() -> str | None:
    preferred = [
        "Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
        "Noto Sans SC", "Source Han Sans SC", "WenQuanYi Zen Hei", "PingFang SC",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in preferred:
        if name in available:
            return name
    return None


def set_plot_style(locale: str) -> None:
    sns.set_theme(style="whitegrid", context="paper")
    matplotlib.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.unicode_minus": False,
        "font.family": "DejaVu Sans",
    })
    if locale == "zh":
        font_name = detect_chinese_font()
        if font_name:
            matplotlib.rcParams["font.family"] = font_name


def save_figure(fig: plt.Figure, out_dir: Path, basename: str) -> None:
    fig.tight_layout()
    fig.savefig(out_dir / f"{basename}.png", bbox_inches="tight")
    fig.savefig(out_dir / f"{basename}.pdf", bbox_inches="tight")
    plt.close(fig)


def label_for_method(method: str, locale: str) -> str:
    return METHOD_LABELS.get(method, {}).get(locale, method)


def build_legend_handles(methods: list[str], locale: str) -> list[Patch]:
    return [
        Patch(facecolor=PALETTE[m], edgecolor=PALETTE[m], label=label_for_method(m, locale))
        for m in methods
    ]


def resolve_analysis_dirname(suffix: str | None = None) -> str:
    if suffix is None:
        return "analysis"
    cleaned = suffix.strip().strip("_")
    if not cleaned:
        return "analysis"
    return f"analysis_{cleaned}"


def load_summaries() -> pd.DataFrame:
    rows = []
    for path in sorted(GENERATION_DIR.glob("*_scored.summary.json")):
        method = path.name.replace("_results_subset100_scored.summary.json", "")
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        rows.append({
            "method": method,
            "answer_correctness": payload["answer_correctness"]["avg_score"],
            "answer_relevancy": payload["answer_relevancy"]["pass_rate"],
            "image_context_relevancy": payload.get("image_context_relevancy", {}).get("pass_rate"),
            "image_faithfulness": payload.get("image_faithfulness", {}).get("pass_rate"),
        })
    df = pd.DataFrame(rows)
    # Set OCR image metrics to NaN -- they are invalid (only 3/100 evaluated)
    ocr_mask = df["method"] == "baseline_ocr"
    df.loc[ocr_mask, "image_context_relevancy"] = np.nan
    df.loc[ocr_mask, "image_faithfulness"] = np.nan
    # No-RAG also has no image metrics
    norag_mask = df["method"] == "no_rag"
    df.loc[norag_mask, "image_context_relevancy"] = np.nan
    df.loc[norag_mask, "image_faithfulness"] = np.nan
    return df


# ─── Chart 1: Overall metrics (grouped bar) ───────────────────────────────

def draw_overall_metrics(df: pd.DataFrame, methods: list[str], locale: str,
                         out_dir: Path, basename: str) -> None:
    metrics = ["answer_correctness", "answer_relevancy", "image_context_relevancy", "image_faithfulness"]
    metric_labels = {
        "answer_correctness": "Answer\nCorrectness" if locale == "en" else "答案\n正确性",
        "answer_relevancy": "Answer\nRelevancy" if locale == "en" else "答案\n相关性",
        "image_context_relevancy": "Image Context\nRelevancy" if locale == "en" else "图像上下文\n相关性",
        "image_faithfulness": "Image\nFaithfulness" if locale == "en" else "图像\n忠实度",
    }

    plot_df = df[df["method"].isin(methods)].copy()
    melted = plot_df.melt(
        id_vars=["method"], value_vars=metrics,
        var_name="metric", value_name="value",
    )
    melted["metric_label"] = melted["metric"].map(metric_labels)
    melted["method_label"] = melted["method"].map(lambda x: label_for_method(x, locale))
    # Drop NaN rows (OCR/No-RAG image metrics)
    melted = melted.dropna(subset=["value"])

    fig, ax = plt.subplots(figsize=(9.4, 4.8))
    present_methods = [m for m in methods if m in melted["method"].unique()]
    sns.barplot(
        data=melted, x="metric_label", y="value",
        hue="method_label", palette=[PALETTE[m] for m in present_methods],
        ax=ax,
    )
    title = "Generator Evaluation Overview" if locale == "en" else "生成器评测总览"
    ax.set_title(title, fontsize=12, weight="bold")
    ax.set_xlabel("")
    ylabel = "Score / Pass Rate" if locale == "en" else "得分 / 通过率"
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 1.05)
    ax.legend(
        handles=build_legend_handles(methods, locale),
        title="",
        loc="upper center",
        bbox_to_anchor=(0.5, 1.18),
        ncol=min(len(methods), 4),
        frameon=True,
    )
    for container in ax.containers:
        labels = []
        for bar in container:
            height = bar.get_height()
            labels.append(f"{height:.3f}" if height < 1.5 else f"{height:.1f}")
        ax.bar_label(container, labels=labels, padding=3, fontsize=8)
    save_figure(fig, out_dir, basename)


# ─── Chart 2: Relevancy & Faithfulness (two-panel) ────────────────────────

def draw_relevancy_faithfulness(df: pd.DataFrame, methods: list[str], locale: str,
                                out_dir: Path, basename: str) -> None:
    plot_df = df[df["method"].isin(methods)].copy()
    plot_df["method_label"] = plot_df["method"].map(lambda x: label_for_method(x, locale))

    label_map = {
        "answer_relevancy": {"en": "Answer Relevancy", "zh": "答案相关性"},
        "image_context_relevancy": {"en": "Image Context Relevancy", "zh": "图像上下文相关性"},
        "image_faithfulness": {"en": "Image Faithfulness", "zh": "图像忠实度"},
    }

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6), sharey=True)

    # Left panel: relevancy (answer + image context)
    left_melted = plot_df.melt(
        id_vars=["method", "method_label"],
        value_vars=["answer_relevancy", "image_context_relevancy"],
        var_name="metric", value_name="value",
    ).dropna(subset=["value"])
    left_melted["metric_label"] = left_melted["metric"].map(lambda x: label_map[x][locale])

    # Right panel: faithfulness (image only)
    right_melted = plot_df.melt(
        id_vars=["method", "method_label"],
        value_vars=["image_faithfulness"],
        var_name="metric", value_name="value",
    ).dropna(subset=["value"])
    right_melted["metric_label"] = right_melted["metric"].map(lambda x: label_map[x][locale])

    for ax, melted, title in zip(
        axes,
        [left_melted, right_melted],
        ["Relevancy" if locale == "en" else "相关性",
         "Faithfulness" if locale == "en" else "忠实度"],
    ):
        if melted.empty:
            ax.text(0.5, 0.5, "No valid data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12)
            ax.set_title(title, fontsize=11, weight="bold")
            continue
        present_methods = [m for m in methods if m in melted["method"].unique()]
        sns.barplot(
            data=melted, x="metric_label", y="value",
            hue="method_label", palette=[PALETTE[m] for m in present_methods],
            ax=ax,
        )
        ax.set_title(title, fontsize=11, weight="bold")
        ax.set_xlabel("")
        ax.set_ylabel("Pass Rate" if locale == "en" else "通过率")
        ax.set_ylim(0, 1.05)
        leg = ax.get_legend()
        if leg is not None:
            leg.remove()

    suptitle = "Relevancy and Faithfulness Comparison" if locale == "en" else "相关性与忠实度对比"
    fig.suptitle(suptitle, fontsize=13, weight="bold", y=1.02)
    fig.legend(
        handles=build_legend_handles(methods, locale),
        title="",
        loc="upper center",
        bbox_to_anchor=(0.5, 1.00),
        ncol=min(len(methods), 4),
        frameon=True,
    )
    save_figure(fig, out_dir, basename)


# ─── Chart 3: Proposed gains over baselines ────────────────────────────────

def draw_improvement_chart(df: pd.DataFrame, methods: list[str], locale: str,
                           out_dir: Path, basename: str) -> None:
    proposed_row = df[df["method"] == "proposed"].iloc[0]
    compare_methods = [m for m in methods if m != "proposed"]
    metrics = ["answer_correctness", "answer_relevancy", "image_context_relevancy", "image_faithfulness"]
    label_map = {
        "answer_correctness": "Answer Correctness" if locale == "en" else "答案正确性",
        "answer_relevancy": "Answer Relevancy" if locale == "en" else "答案相关性",
        "image_context_relevancy": "Image Context Relevancy" if locale == "en" else "图像上下文相关性",
        "image_faithfulness": "Image Faithfulness" if locale == "en" else "图像忠实度",
    }

    rows = []
    for method in compare_methods:
        row = df[df["method"] == method].iloc[0]
        for metric in metrics:
            proposed_val = proposed_row[metric]
            baseline_val = row[metric]
            if pd.isna(proposed_val) or pd.isna(baseline_val):
                delta = np.nan
            else:
                delta = proposed_val - baseline_val
            rows.append({"method": method, "metric": metric, "delta": delta})

    plot_df = pd.DataFrame(rows).dropna(subset=["delta"])
    if plot_df.empty:
        return
    plot_df["metric_label"] = plot_df["metric"].map(label_map)
    plot_df["method_label"] = plot_df["method"].map(lambda x: label_for_method(x, locale))

    present_methods = [m for m in compare_methods if m in plot_df["method"].unique()]
    fig, ax = plt.subplots(figsize=(9.8, 4.8))
    sns.barplot(
        data=plot_df, x="metric_label", y="delta",
        hue="method_label", palette=[PALETTE[m] for m in present_methods],
        ax=ax,
    )
    ax.axhline(0, color="#222222", linewidth=0.8)
    title = "Proposed Method Gains over Baselines" if locale == "en" else "本文方法相对基线的提升"
    ax.set_title(title, fontsize=12, weight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Absolute Gain" if locale == "en" else "绝对提升")
    ax.legend(
        handles=build_legend_handles(compare_methods, locale),
        title="",
        loc="upper center",
        bbox_to_anchor=(0.5, 1.18),
        ncol=min(len(compare_methods), 4),
        frameon=True,
    )
    for container in ax.containers:
        ax.bar_label(container, fmt="%.3f", padding=3, fontsize=8)
    save_figure(fig, out_dir, basename)


# ─── Main ──────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Redraw generation charts with OCR image metrics excluded."
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


def main() -> None:
    args = parse_args()
    df = load_summaries()
    variants = {
        "with_ocr": ["proposed", "baseline_clip", "baseline_ocr", "no_rag"],
        "without_ocr": ["proposed", "baseline_clip", "no_rag"],
    }
    analysis_dirname = resolve_analysis_dirname(args.analysis_dir_suffix)

    for locale in ("en", "zh"):
        fig_dir = GENERATION_DIR / analysis_dirname / f"figures_{locale}"
        fig_dir.mkdir(parents=True, exist_ok=True)
        set_plot_style(locale)

        for suffix, methods in variants.items():
            draw_overall_metrics(df, methods, locale, fig_dir,
                                 f"generation_overall_metrics_{suffix}_{args.version_suffix}")
            draw_relevancy_faithfulness(df, methods, locale, fig_dir,
                                        f"generation_relevancy_faithfulness_{suffix}_{args.version_suffix}")
            draw_improvement_chart(df, methods, locale, fig_dir,
                                   f"generation_improvement_{suffix}_{args.version_suffix}")

    print(f"{args.version_suffix} charts generated successfully in {analysis_dirname}.")
    for locale in ("en", "zh"):
        fig_dir = GENERATION_DIR / analysis_dirname / f"figures_{locale}"
        for f in sorted(fig_dir.glob(f"*_{args.version_suffix}.*")):
            print(f"  {f.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
