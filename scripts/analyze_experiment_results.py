from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "实验数据"

RETRIEVAL_DIR = DATA_ROOT / "检索器"
GENERATION_DIR = DATA_ROOT / "生成器"
FINETUNE_DIR = DATA_ROOT / "微调"

ANALYSIS_DIRNAME = "analysis"
FIG_EN_DIRNAME = "figures_en"
FIG_ZH_DIRNAME = "figures_zh"
TABLE_DIRNAME = "tables"
REPORT_DIRNAME = "report"


PALETTE = {
    "proposed": "#1f77b4",
    "baseline_clip": "#ff7f0e",
    "baseline_ocr": "#7f7f7f",
    "no_rag": "#4c4c4c",
    "base": "#6a8caf",
    "ckpt75": "#ef8354",
    "ckpt140": "#2d3142",
}

METHOD_LABELS = {
    "proposed": {"en": "Proposed", "zh": "本文方法"},
    "baseline_clip": {"en": "Baseline-CLIP", "zh": "CLIP基线"},
    "baseline_ocr": {"en": "Baseline-OCR", "zh": "OCR基线"},
    "no_rag": {"en": "No-RAG", "zh": "无检索"},
    "base": {"en": "Base", "zh": "原始模型"},
    "ckpt75": {"en": "Ckpt-75", "zh": "检查点75"},
    "ckpt140": {"en": "Ckpt-140", "zh": "检查点140"},
}

DOMAIN_LABELS = {
    "commerce_manufacturing": {"en": "Commerce & Manu.", "zh": "商贸制造"},
    "construction": {"en": "Construction", "zh": "建筑"},
    "crm": {"en": "CRM", "zh": "客户管理"},
    "crossdomain": {"en": "Cross-domain", "zh": "跨领域"},
    "education": {"en": "Education", "zh": "教育"},
    "energy": {"en": "Energy", "zh": "能源"},
    "finance": {"en": "Finance", "zh": "金融"},
    "healthcare": {"en": "Healthcare", "zh": "医疗"},
    "legal": {"en": "Legal", "zh": "法律"},
}

QUESTION_TYPE_LABELS = {
    "causal_reasoning": {"en": "Causal", "zh": "因果推理"},
    "comparison": {"en": "Comparison", "zh": "比较"},
    "factual_retrieval": {"en": "Factual", "zh": "事实检索"},
    "summarization": {"en": "Summarization", "zh": "总结"},
    "temporal_comparison": {"en": "Temporal", "zh": "时间比较"},
}


@dataclass
class OutputDirs:
    root: Path
    fig_en: Path
    fig_zh: Path
    tables: Path
    report: Path


def ensure_output_dirs(base_dir: Path) -> OutputDirs:
    root = base_dir / ANALYSIS_DIRNAME
    fig_en = root / FIG_EN_DIRNAME
    fig_zh = root / FIG_ZH_DIRNAME
    tables = root / TABLE_DIRNAME
    report = root / REPORT_DIRNAME
    for path in (root, fig_en, fig_zh, tables, report):
        path.mkdir(parents=True, exist_ok=True)
    return OutputDirs(root=root, fig_en=fig_en, fig_zh=fig_zh, tables=tables, report=report)


def detect_chinese_font() -> Optional[str]:
    preferred = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Noto Sans SC",
        "Source Han Sans SC",
        "WenQuanYi Zen Hei",
        "PingFang SC",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in preferred:
        if name in available:
            return name
    return None


def set_plot_style(locale: str) -> None:
    sns.set_theme(style="whitegrid", context="paper")
    matplotlib.rcParams["figure.dpi"] = 150
    matplotlib.rcParams["savefig.dpi"] = 300
    matplotlib.rcParams["axes.spines.top"] = False
    matplotlib.rcParams["axes.spines.right"] = False
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["font.family"] = "DejaVu Sans"
    if locale == "zh":
        font_name = detect_chinese_font()
        if font_name:
            matplotlib.rcParams["font.family"] = font_name


def save_figure(fig: plt.Figure, out_dir: Path, basename: str) -> None:
    fig.tight_layout()
    fig.savefig(out_dir / f"{basename}.png", bbox_inches="tight")
    fig.savefig(out_dir / f"{basename}.pdf", bbox_inches="tight")
    plt.close(fig)


def export_table_images(df: pd.DataFrame, out_dir: Path, basename: str, locale: str, rows_per_page: int = 24) -> None:
    if df.empty:
        return
    display_df = df.copy()
    for column in display_df.columns:
        if pd.api.types.is_float_dtype(display_df[column]):
            display_df[column] = display_df[column].map(lambda x: "" if pd.isna(x) else f"{x:.4f}")

    preview_mode = len(display_df) > 60
    if preview_mode:
        display_df = display_df.head(60)

    pages = math.ceil(len(display_df) / rows_per_page)
    for page_idx in range(pages):
        chunk = display_df.iloc[page_idx * rows_per_page:(page_idx + 1) * rows_per_page]
        fig_height = max(2.6, 0.42 * (len(chunk) + 2))
        fig, ax = plt.subplots(figsize=(max(8.5, len(chunk.columns) * 1.45), fig_height))
        ax.axis("off")
        title = basename.replace("_", " ")
        if preview_mode:
            title = f"{title} preview"
        if pages > 1:
            title = f"{title} ({page_idx + 1}/{pages})"
        ax.set_title(title, fontsize=11, weight="bold", pad=10)
        table = ax.table(
            cellText=chunk.values,
            colLabels=chunk.columns,
            cellLoc="center",
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 1.2)
        for (row, col), cell in table.get_celld().items():
            cell.set_edgecolor("#D0D7DE")
            if row == 0:
                cell.set_facecolor("#EAF2F8")
                cell.set_text_props(weight="bold")
            elif row % 2 == 0:
                cell.set_facecolor("#F8FAFC")
        if preview_mode:
            suffix = f"_preview_p{page_idx + 1}" if pages > 1 else "_preview"
        else:
            suffix = f"_p{page_idx + 1}" if pages > 1 else ""
        fig.savefig(out_dir / f"{basename}{suffix}.png", dpi=300, bbox_inches="tight")
        plt.close(fig)


def export_dataframe_bundle(df: pd.DataFrame, csv_path: Path, output_dirs: OutputDirs, locale: str = "en") -> None:
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    export_table_images(df, output_dirs.tables, csv_path.stem, locale=locale)


def label_for_method(method: str, locale: str) -> str:
    return METHOD_LABELS.get(method, {"en": method, "zh": method})[locale]


def label_for_domain(domain: str, locale: str) -> str:
    return DOMAIN_LABELS.get(domain, {"en": domain, "zh": domain})[locale]


def label_for_question_type(question_type: str, locale: str) -> str:
    return QUESTION_TYPE_LABELS.get(question_type, {"en": question_type, "zh": question_type})[locale]


def latest_file(files: Iterable[Path]) -> Optional[Path]:
    items = sorted(files, key=lambda p: p.name)
    return items[-1] if items else None


def percent_formatter(value: float) -> str:
    if math.isnan(value):
        return "N/A"
    return f"{value * 100:.1f}%"


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_retrieval_filename(path: Path) -> Optional[Tuple[str, str]]:
    name = path.stem
    if name.startswith("unidoc_"):
        match = re.match(r"^unidoc_(.+)_(proposed|baseline_clip|baseline_ocr)_\d{8}_\d{6}$", name)
        if match:
            return match.group(1), match.group(2)
    else:
        match = re.match(r"^(proposed|baseline_clip|baseline_ocr)_\d{8}_\d{6}$", name)
        if match:
            return "coco", match.group(1)
    return None


def build_retrieval_frames() -> Tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: List[dict] = []
    query_rows: List[dict] = []
    grouped: Dict[Tuple[str, str], List[Path]] = {}

    for path in RETRIEVAL_DIR.glob("*.json"):
        parsed = parse_retrieval_filename(path)
        if parsed:
            grouped.setdefault(parsed, []).append(path)

    for (scope, method), paths in sorted(grouped.items()):
        path = latest_file(paths)
        if path is None:
            continue
        payload = load_json(path)
        summary = payload["summary"]
        summary_rows.append(
            {
                "scope": scope,
                "method": method,
                "path": str(path),
                "top_k": summary.get("top_k"),
                "num_queries": summary.get("num_queries"),
                "recall_at_1": summary["recall_at_1"]["mean"],
                "recall_at_5": summary["recall_at_5"]["mean"],
                "recall_at_10": summary["recall_at_10"]["mean"],
                "mrr": summary["mrr"]["mean"],
                "map_at_10": summary["map_at_10"]["mean"],
                "latency_mean_ms": summary["latency_ms"]["mean"],
                "latency_std_ms": summary["latency_ms"]["std"],
                "latency_median_ms": summary["latency_ms_median"],
            }
        )

        for item in payload.get("per_query", []):
            rank = item.get("first_hit_rank")
            if rank == 1:
                rank_bucket = "1"
            elif rank is not None and rank <= 5:
                rank_bucket = "2-5"
            elif rank is not None and rank <= 10:
                rank_bucket = "6-10"
            else:
                rank_bucket = ">10"
            query_rows.append(
                {
                    "scope": scope,
                    "method": method,
                    "query_index": item.get("query_index"),
                    "query": item.get("query"),
                    "first_hit_rank": rank,
                    "rank_bucket": rank_bucket,
                    "recall_at_1": item.get("recall_at_1"),
                    "recall_at_5": item.get("recall_at_5"),
                    "recall_at_10": item.get("recall_at_10"),
                    "reciprocal_rank": item.get("reciprocal_rank"),
                    "ap_at_10": item.get("ap_at_10"),
                    "latency_ms": item.get("latency_ms"),
                }
            )

    summary_df = pd.DataFrame(summary_rows)
    query_df = pd.DataFrame(query_rows)
    return summary_df, query_df


def draw_grouped_metric_chart(
    df: pd.DataFrame,
    methods: Sequence[str],
    metric_order: Sequence[str],
    locale: str,
    title: str,
    ylabel: str,
    output_dir: Path,
    basename: str,
) -> None:
    plot_df = df[df["method"].isin(methods)].copy()
    melted = plot_df.melt(
        id_vars=["method"],
        value_vars=list(metric_order),
        var_name="metric",
        value_name="value",
    )
    metric_labels = {
        "recall_at_1": "Recall@1",
        "recall_at_5": "Recall@5",
        "recall_at_10": "Recall@10",
        "mrr": "MRR",
        "map_at_10": "mAP@10",
        "latency_mean_ms": "Mean",
        "latency_median_ms": "Median",
        "answer_correctness": "Answer\nCorrectness",
        "answer_relevancy": "Answer\nRelevancy",
        "image_context_relevancy": "Image Context\nRelevancy",
        "image_faithfulness": "Image\nFaithfulness",
    }
    melted["metric_label"] = melted["metric"].map(metric_labels).fillna(melted["metric"])
    melted["method_label"] = melted["method"].map(lambda x: label_for_method(x, locale))

    fig, ax = plt.subplots(figsize=(9.4, 4.8))
    sns.barplot(
        data=melted,
        x="metric_label",
        y="value",
        hue="method_label",
        palette=[PALETTE[m] for m in methods],
        ax=ax,
    )
    ax.set_title(title, fontsize=12, weight="bold")
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    upper = melted["value"].max()
    ax.set_ylim(0, max(1.05 if upper <= 1.0 else upper * 1.1, upper * 1.08))
    ax.legend(title="", loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=min(len(methods), 4), frameon=True)
    for container in ax.containers:
        labels = []
        for bar in container:
            height = bar.get_height()
            labels.append(f"{height:.3f}" if height < 1.5 else f"{height:.1f}")
        ax.bar_label(container, labels=labels, padding=3, fontsize=8)
    save_figure(fig, output_dir, basename)


def draw_latency_chart(
    df: pd.DataFrame,
    methods: Sequence[str],
    locale: str,
    output_dir: Path,
    basename: str,
) -> None:
    plot_df = df[df["method"].isin(methods)].copy()
    melted = plot_df.melt(
        id_vars=["method"],
        value_vars=["latency_mean_ms", "latency_median_ms"],
        var_name="metric",
        value_name="value",
    )
    labels = {
        "latency_mean_ms": {"en": "Mean Latency", "zh": "平均延迟"},
        "latency_median_ms": {"en": "Median Latency", "zh": "中位延迟"},
    }
    melted["metric_label"] = melted["metric"].map(lambda x: labels[x][locale])
    melted["method_label"] = melted["method"].map(lambda x: label_for_method(x, locale))

    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    sns.barplot(
        data=melted,
        x="metric_label",
        y="value",
        hue="method_label",
        palette=[PALETTE[m] for m in methods],
        ax=ax,
    )
    ax.set_title("Retrieval Latency Comparison" if locale == "en" else "检索延迟对比", fontsize=12, weight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Latency (ms)" if locale == "en" else "延迟（ms）")
    ax.legend(title="", loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=min(len(methods), 4), frameon=True)
    for container in ax.containers:
        ax.bar_label(container, fmt="%.1f", padding=3, fontsize=8)
    save_figure(fig, output_dir, basename)


def draw_domain_metric_chart(
    df: pd.DataFrame,
    methods: Sequence[str],
    locale: str,
    metrics: Sequence[str],
    output_dir: Path,
    basename: str,
) -> None:
    plot_df = df[(df["scope"] != "coco") & (df["method"].isin(methods))].copy()
    if plot_df.empty:
        return

    fig, axes = plt.subplots(1, len(metrics), figsize=(14.2, 4.8), sharey=False)
    if len(metrics) == 1:
        axes = [axes]

    for ax, metric in zip(axes, metrics):
        temp = plot_df.copy()
        temp["domain_label"] = temp["scope"].map(lambda x: label_for_domain(x, locale))
        sns.barplot(
            data=temp,
            x="domain_label",
            y=metric,
            hue=temp["method"].map(lambda x: label_for_method(x, locale)),
            palette=[PALETTE[m] for m in methods],
            ax=ax,
        )
        ax.set_xlabel("")
        ax.set_ylabel(metric.upper())
        ax.set_title({"recall_at_1": "Recall@1", "mrr": "MRR", "recall_at_10": "Recall@10", "map_at_10": "mAP@10"}[metric])
        ax.tick_params(axis="x", rotation=35)
        ax.set_ylim(0, min(1.05, temp[metric].max() * 1.15))
        if ax is axes[-1]:
            ax.legend(title="", loc="upper center", bbox_to_anchor=(0.5, 1.22), ncol=min(len(methods), 4), fontsize=8, frameon=True)
        else:
            ax.get_legend().remove()

    fig.suptitle(
        "UniDoc Domain-wise Retrieval Performance" if locale == "en" else "UniDoc分领域检索性能",
        fontsize=13,
        weight="bold",
        y=1.03,
    )
    save_figure(fig, output_dir, basename)


def draw_heatmap(
    df: pd.DataFrame,
    methods: Sequence[str],
    locale: str,
    output_dir: Path,
    basename: str,
) -> None:
    plot_df = df[(df["scope"] != "coco") & (df["method"].isin(methods))].copy()
    if plot_df.empty:
        return
    metrics = ["recall_at_1", "recall_at_10", "mrr", "map_at_10"]
    fig, axes = plt.subplots(1, len(methods), figsize=(15.2, 5.4), sharey=True)
    if len(methods) == 1:
        axes = [axes]

    for ax, method in zip(axes, methods):
        temp = plot_df[plot_df["method"] == method].copy()
        temp["domain_label"] = temp["scope"].map(lambda x: label_for_domain(x, locale))
        pivot = temp.set_index("domain_label")[metrics]
        pivot.columns = ["Recall@1", "Recall@10", "MRR", "mAP@10"]
        sns.heatmap(
            pivot,
            annot=True,
            fmt=".3f",
            cmap="Blues",
            cbar=ax is axes[-1],
            linewidths=0.5,
            linecolor="white",
            ax=ax,
            vmin=0,
            vmax=max(1.0, float(pivot.max().max())),
        )
        ax.set_title(label_for_method(method, locale), fontsize=11, weight="bold")
        ax.set_xlabel("")
        ax.set_ylabel("")

    fig.suptitle("Domain-level Metric Heatmaps" if locale == "en" else "分领域指标热力图", fontsize=13, weight="bold", y=1.02)
    save_figure(fig, output_dir, basename)


def draw_rank_bucket_chart(
    query_df: pd.DataFrame,
    methods: Sequence[str],
    locale: str,
    output_dir: Path,
    basename: str,
) -> None:
    plot_df = query_df[(query_df["scope"] == "coco") & (query_df["method"].isin(methods))].copy()
    if plot_df.empty:
        return

    rank_df = plot_df.groupby(["method", "rank_bucket"]).size().reset_index(name="count")
    rank_df["ratio"] = rank_df.groupby("method")["count"].transform(lambda s: s / s.sum())
    order = ["1", "2-5", "6-10", ">10"]
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    bottom = np.zeros(len(methods))
    x = np.arange(len(methods))

    for bucket in order:
        subset = rank_df[rank_df["rank_bucket"] == bucket].set_index("method").reindex(methods)
        values = subset["ratio"].fillna(0).to_numpy()
        bars = ax.bar(
            x,
            values,
            bottom=bottom,
            label=bucket,
            color=sns.color_palette("Blues", 5)[order.index(bucket) + 1],
            edgecolor="white",
        )
        for bar, value, btm in zip(bars, values, bottom):
            if value >= 0.08:
                ax.text(bar.get_x() + bar.get_width() / 2, btm + value / 2, f"{value * 100:.1f}%", ha="center", va="center", fontsize=8, color="white", weight="bold")
        bottom += values

    ax.set_xticks(x)
    ax.set_xticklabels([label_for_method(m, locale) for m in methods])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Ratio" if locale == "en" else "占比")
    ax.set_title("First-hit Rank Distribution on COCO" if locale == "en" else "COCO首命中排名分布", fontsize=12, weight="bold")
    ax.legend(title="Rank" if locale == "en" else "排名段", loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=4, frameon=True)
    save_figure(fig, output_dir, basename)


def write_retrieval_report(summary_df: pd.DataFrame, output_dirs: OutputDirs) -> None:
    coco = summary_df[summary_df["scope"] == "coco"].copy()
    domain = summary_df[summary_df["scope"] != "coco"].copy()
    domain_avg = domain.groupby("method")[["recall_at_1", "mrr", "map_at_10"]].mean().sort_values("mrr", ascending=False)
    best_coco = coco.sort_values("mrr", ascending=False).iloc[0]
    worst_coco = coco.sort_values("mrr", ascending=True).iloc[0]
    best_domain = domain_avg.iloc[0]

    text = f"""# 检索器实验分析报告

## 1. 数据范围
- COCO 总体结果：{len(coco)} 个方法
- UniDoc 分领域结果：{len(domain)} 条方法-领域记录

## 2. 总体结论
- COCO 上 MRR 最优方法为 `{best_coco['method']}`，MRR={best_coco['mrr']:.4f}，Recall@1={best_coco['recall_at_1']:.4f}。
- COCO 上最弱方法为 `{worst_coco['method']}`，MRR={worst_coco['mrr']:.4f}。
- UniDoc 分领域平均指标显示 `{domain_avg.index[0]}` 的平均 MRR 最高，为 {best_domain['mrr']:.4f}。

## 3. 结果解读
- COCO 更偏视觉描述对齐，`baseline_clip` 在首位命中和排序指标上通常更强。
- UniDoc 的分领域图更适合论文主文，用于突出方法在专业文档场景下的泛化性。
- OCR 基线建议同时保留完整版本与去 OCR 版本，以兼顾对照充分性和主图可读性。

## 4. 图表清单
- `retrieval_coco_metrics_with_ocr`
- `retrieval_coco_metrics_without_ocr`
- `retrieval_latency_with_ocr`
- `retrieval_latency_without_ocr`
- `retrieval_domain_metrics_with_ocr`
- `retrieval_domain_metrics_without_ocr`
- `retrieval_heatmap_with_ocr`
- `retrieval_heatmap_without_ocr`
- `retrieval_first_hit_distribution_with_ocr`
- `retrieval_first_hit_distribution_without_ocr`
    """
    (output_dirs.report / "retrieval_analysis.md").write_text(text, encoding="utf-8")


def draw_retrieval_single_domain_chart(
    summary_df: pd.DataFrame,
    domain: str,
    methods: Sequence[str],
    locale: str,
    output_dir: Path,
    basename: str,
) -> None:
    plot_df = summary_df[(summary_df["scope"] == domain) & (summary_df["method"].isin(methods))].copy()
    if plot_df.empty:
        return
    metric_order = ["recall_at_1", "recall_at_10", "mrr", "map_at_10"]
    melted = plot_df.melt(id_vars=["method"], value_vars=metric_order, var_name="metric", value_name="value")
    metric_labels = {"recall_at_1": "Recall@1", "recall_at_10": "Recall@10", "mrr": "MRR", "map_at_10": "mAP@10"}
    melted["metric_label"] = melted["metric"].map(metric_labels)
    melted["method_label"] = melted["method"].map(lambda x: label_for_method(x, locale))
    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    sns.barplot(
        data=melted,
        x="metric_label",
        y="value",
        hue="method_label",
        palette=[PALETTE[m] for m in methods],
        ax=ax,
    )
    ax.set_title(
        f"{label_for_domain(domain, locale)} Retrieval Metrics" if locale == "en" else f"{label_for_domain(domain, locale)}检索指标",
        fontsize=12,
        weight="bold",
    )
    ax.set_xlabel("")
    ax.set_ylabel("Score" if locale == "en" else "指标值")
    ax.set_ylim(0, 1.05)
    ax.legend(title="", loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=min(len(methods), 4), frameon=True)
    for container in ax.containers:
        ax.bar_label(container, fmt="%.3f", padding=3, fontsize=8)
    save_figure(fig, output_dir, basename)


def build_generation_frames() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_rows: List[dict] = []
    domain_rows: List[dict] = []
    qtype_rows: List[dict] = []

    for path in GENERATION_DIR.glob("*_scored.summary.json"):
        method = path.name.replace("_results_subset100_scored.summary.json", "")
        payload = load_json(path)
        summary_rows.append(
            {
                "method": method,
                "answer_correctness": payload["answer_correctness"]["avg_score"],
                "answer_relevancy": payload["answer_relevancy"]["pass_rate"],
                "image_context_relevancy": payload["image_context_relevancy"]["pass_rate"],
                "image_faithfulness": payload["image_faithfulness"]["pass_rate"],
            }
        )
        for domain, item in payload.get("answer_correctness_by_domain", {}).items():
            domain_rows.append({"method": method, "domain": domain, "count": item["count"], "answer_correctness": item["avg_score"]})
        for qtype, item in payload.get("answer_correctness_by_question_type", {}).items():
            qtype_rows.append({"method": method, "question_type": qtype, "count": item["count"], "answer_correctness": item["avg_score"]})

    return pd.DataFrame(summary_rows), pd.DataFrame(domain_rows), pd.DataFrame(qtype_rows)


def draw_generation_domain_chart(df: pd.DataFrame, methods: Sequence[str], locale: str, output_dir: Path, basename: str) -> None:
    plot_df = df[df["method"].isin(methods)].copy()
    plot_df["domain_label"] = plot_df["domain"].map(lambda x: label_for_domain(x, locale))
    plot_df["method_label"] = plot_df["method"].map(lambda x: label_for_method(x, locale))
    fig, ax = plt.subplots(figsize=(11.8, 5.1))
    sns.barplot(data=plot_df, x="domain_label", y="answer_correctness", hue="method_label", palette=[PALETTE[m] for m in methods], ax=ax)
    ax.set_title("Domain-wise Answer Correctness" if locale == "en" else "分领域答案正确性", fontsize=12, weight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Avg. Score" if locale == "en" else "平均得分")
    ax.tick_params(axis="x", rotation=30)
    ax.set_ylim(0, 1.05)
    ax.legend(title="", loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=min(len(methods), 4), frameon=True)
    save_figure(fig, output_dir, basename)


def draw_generation_qtype_chart(df: pd.DataFrame, methods: Sequence[str], locale: str, output_dir: Path, basename: str) -> None:
    plot_df = df[df["method"].isin(methods)].copy()
    plot_df["question_label"] = plot_df["question_type"].map(lambda x: label_for_question_type(x, locale))
    plot_df["method_label"] = plot_df["method"].map(lambda x: label_for_method(x, locale))
    fig, ax = plt.subplots(figsize=(10.8, 4.9))
    sns.barplot(data=plot_df, x="question_label", y="answer_correctness", hue="method_label", palette=[PALETTE[m] for m in methods], ax=ax)
    ax.set_title("Question-type Answer Correctness" if locale == "en" else "分题型答案正确性", fontsize=12, weight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Avg. Score" if locale == "en" else "平均得分")
    ax.set_ylim(0, 1.05)
    ax.legend(title="", loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=min(len(methods), 4), frameon=True)
    save_figure(fig, output_dir, basename)


def draw_relevancy_faithfulness_chart(summary_df: pd.DataFrame, methods: Sequence[str], locale: str, output_dir: Path, basename: str) -> None:
    plot_df = summary_df[summary_df["method"].isin(methods)].copy()
    plot_df["method_label"] = plot_df["method"].map(lambda x: label_for_method(x, locale))
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6), sharey=True)

    left_metrics = ["answer_relevancy", "image_context_relevancy"]
    right_metrics = ["image_faithfulness"]
    label_map = {
        "answer_relevancy": {"en": "Answer Relevancy", "zh": "答案相关性"},
        "image_context_relevancy": {"en": "Image Context Relevancy", "zh": "图像上下文相关性"},
        "image_faithfulness": {"en": "Image Faithfulness", "zh": "图像忠实度"},
    }

    for ax, metric_group, title in zip(axes, [left_metrics, right_metrics], ["Relevancy" if locale == "en" else "相关性", "Faithfulness" if locale == "en" else "忠实度"]):
        melted = plot_df.melt(id_vars=["method", "method_label"], value_vars=metric_group, var_name="metric", value_name="value")
        melted["metric_label"] = melted["metric"].map(lambda x: label_map[x][locale])
        sns.barplot(data=melted, x="metric_label", y="value", hue="method_label", palette=[PALETTE[m] for m in methods], ax=ax)
        ax.set_title(title, fontsize=11, weight="bold")
        ax.set_xlabel("")
        ax.set_ylabel("Pass Rate" if locale == "en" else "通过率")
        ax.set_ylim(0, 1.05)
        if ax is axes[1]:
            ax.legend(title="", loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=min(len(methods), 4), frameon=True)
        else:
            ax.get_legend().remove()

    fig.suptitle("Relevancy and Faithfulness Comparison" if locale == "en" else "相关性与忠实度对比", fontsize=13, weight="bold", y=1.02)
    save_figure(fig, output_dir, basename)


def draw_generation_improvement_chart(summary_df: pd.DataFrame, methods: Sequence[str], locale: str, output_dir: Path, basename: str) -> None:
    proposed_row = summary_df[summary_df["method"] == "proposed"].iloc[0]
    compare_methods = [m for m in methods if m != "proposed"]
    metrics = ["answer_correctness", "answer_relevancy", "image_context_relevancy", "image_faithfulness"]
    rows = []
    for method in compare_methods:
        row = summary_df[summary_df["method"] == method].iloc[0]
        for metric in metrics:
            rows.append({"method": method, "metric": metric, "delta": proposed_row[metric] - row[metric]})
    plot_df = pd.DataFrame(rows)
    label_map = {
        "answer_correctness": "Answer Correctness" if locale == "en" else "答案正确性",
        "answer_relevancy": "Answer Relevancy" if locale == "en" else "答案相关性",
        "image_context_relevancy": "Image Context Relevancy" if locale == "en" else "图像上下文相关性",
        "image_faithfulness": "Image Faithfulness" if locale == "en" else "图像忠实度",
    }
    plot_df["metric_label"] = plot_df["metric"].map(label_map)
    plot_df["method_label"] = plot_df["method"].map(lambda x: label_for_method(x, locale))
    fig, ax = plt.subplots(figsize=(9.8, 4.8))
    sns.barplot(data=plot_df, x="metric_label", y="delta", hue="method_label", palette=[PALETTE[m] for m in compare_methods], ax=ax)
    ax.axhline(0, color="#222222", linewidth=0.8)
    ax.set_title("Proposed Method Gains over Baselines" if locale == "en" else "本文方法相对基线的提升", fontsize=12, weight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Absolute Gain" if locale == "en" else "绝对提升")
    ax.legend(title="", loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=min(len(compare_methods), 4), frameon=True)
    for container in ax.containers:
        ax.bar_label(container, fmt="%.3f", padding=3, fontsize=8)
    save_figure(fig, output_dir, basename)


def write_generation_report(summary_df: pd.DataFrame, output_dirs: OutputDirs) -> None:
    ranked = summary_df.sort_values("answer_correctness", ascending=False)
    best = ranked.iloc[0]
    no_rag = summary_df[summary_df["method"] == "no_rag"].iloc[0]
    proposed = summary_df[summary_df["method"] == "proposed"].iloc[0]
    text = f"""# 生成器实验分析报告

## 1. 总体表现
- 答案正确性最高的方法为 `{best['method']}`，平均分为 {best['answer_correctness']:.4f}。
- `proposed` 相比 `no_rag` 的答案正确性提升为 {proposed['answer_correctness'] - no_rag['answer_correctness']:.4f}。
- `proposed` 的答案相关性为 {percent_formatter(proposed['answer_relevancy'])}，图像忠实度为 {percent_formatter(proposed['image_faithfulness'])}。

## 2. 结果解读
- `no_rag` 的相关性不低，但正确性很弱，说明无检索时容易生成表面相关的回答。
- `baseline_ocr` 在当前 UniDoc 实验中整体偏弱，适合作为弱基线。
- 主文建议突出 `proposed` 与 `baseline_clip` 的对比，并在附图保留 OCR 版本。

## 3. 图表清单
- `generation_overall_metrics_with_ocr`
- `generation_overall_metrics_without_ocr`
- `generation_domain_correctness_with_ocr`
- `generation_domain_correctness_without_ocr`
- `generation_qtype_correctness_with_ocr`
- `generation_qtype_correctness_without_ocr`
- `generation_relevancy_faithfulness_with_ocr`
- `generation_relevancy_faithfulness_without_ocr`
- `generation_improvement_with_ocr`
- `generation_improvement_without_ocr`
    """
    (output_dirs.report / "generation_analysis.md").write_text(text, encoding="utf-8")


def parse_training_log(path: Path) -> pd.DataFrame:
    rows: List[dict] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if "global_step/max_steps" not in line:
            continue
        start = line.find("{")
        end = line.rfind("}")
        if start == -1 or end == -1 or end <= start:
            continue
        payload_text = line[start:end + 1]
        try:
            payload = ast.literal_eval(payload_text)
        except Exception:
            continue
        step_text = str(payload.get("global_step/max_steps", ""))
        step_match = re.match(r"(\d+)/(\d+)", step_text)
        rows.append(
            {
                "step": int(step_match.group(1)) if step_match else None,
                "max_steps": int(step_match.group(2)) if step_match else None,
                "epoch": float(payload.get("epoch")) if payload.get("epoch") is not None else None,
                "loss": float(payload["loss"]) if "loss" in payload else np.nan,
                "eval_loss": float(payload["eval_loss"]) if "eval_loss" in payload else np.nan,
                "token_acc": float(payload["token_acc"]) if "token_acc" in payload else np.nan,
                "eval_token_acc": float(payload["eval_token_acc"]) if "eval_token_acc" in payload else np.nan,
                "learning_rate": float(payload["learning_rate"]) if "learning_rate" in payload else np.nan,
            }
        )
    df = pd.DataFrame(rows).drop_duplicates(subset=["step", "loss", "eval_loss"], keep="last")
    if not df.empty:
        df = df.sort_values(["step", "epoch"], na_position="last").reset_index(drop=True)
    return df


def build_finetune_frames() -> Tuple[pd.DataFrame, pd.DataFrame]:
    judge_df = pd.read_csv(FINETUNE_DIR / "evaluation_report_qwen3.5-plus.csv").rename(
        columns={"Base_Avg": "base", "Ckpt75_Avg": "ckpt75", "Ckpt140_Avg": "ckpt140"}
    )
    long_df = judge_df.melt(id_vars=["ID"], value_vars=["base", "ckpt75", "ckpt140"], var_name="model", value_name="score")
    training_df = parse_training_log(FINETUNE_DIR / "train_log.txt")
    return long_df, training_df


def draw_finetune_overall_chart(long_df: pd.DataFrame, locale: str, output_dir: Path, basename: str) -> None:
    stats_df = long_df.groupby("model")["score"].agg(["mean", "std"]).reset_index()
    stats_df["method_label"] = stats_df["model"].map(lambda x: label_for_method(x, locale))
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    bars = ax.bar(stats_df["method_label"], stats_df["mean"], yerr=stats_df["std"].fillna(0), capsize=5, color=[PALETTE[m] for m in stats_df["model"]], edgecolor="white")
    ax.set_title("Fine-tuning Score Comparison" if locale == "en" else "微调模型得分对比", fontsize=12, weight="bold")
    ax.set_ylabel("Judge Score" if locale == "en" else "评测得分")
    ax.set_ylim(0, max(10.5, stats_df["mean"].max() + stats_df["std"].max() + 0.3))
    ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=8)
    save_figure(fig, output_dir, basename)


def draw_finetune_distribution_chart(long_df: pd.DataFrame, locale: str, output_dir: Path, basename: str) -> None:
    plot_df = long_df.copy()
    plot_df["model_label"] = plot_df["model"].map(lambda x: label_for_method(x, locale))
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    sns.violinplot(
        data=plot_df,
        x="model_label",
        y="score",
        hue="model_label",
        palette=[PALETTE["base"], PALETTE["ckpt75"], PALETTE["ckpt140"]],
        inner="quartile",
        legend=False,
        ax=ax,
    )
    ax.set_title("Score Distribution across Samples" if locale == "en" else "样本级得分分布", fontsize=12, weight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Judge Score" if locale == "en" else "评测得分")
    ax.set_ylim(0, 10.5)
    save_figure(fig, output_dir, basename)


def draw_finetune_delta_chart(judge_wide_df: pd.DataFrame, locale: str, output_dir: Path, basename: str) -> None:
    delta_df = pd.DataFrame({"Ckpt75 - Base": judge_wide_df["ckpt75"] - judge_wide_df["base"], "Ckpt140 - Base": judge_wide_df["ckpt140"] - judge_wide_df["base"]}).melt(var_name="comparison", value_name="delta")
    if locale == "zh":
        delta_df["comparison"] = delta_df["comparison"].replace({"Ckpt75 - Base": "检查点75 - 原始模型", "Ckpt140 - Base": "检查点140 - 原始模型"})
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    sns.histplot(data=delta_df, x="delta", hue="comparison", bins=14, kde=True, stat="count", common_norm=False, palette=[PALETTE["ckpt75"], PALETTE["ckpt140"]], ax=ax)
    ax.axvline(0, color="#222222", linewidth=0.9)
    ax.set_title("Sample-level Score Gains" if locale == "en" else "样本级得分增益分布", fontsize=12, weight="bold")
    ax.set_xlabel("Score Gain" if locale == "en" else "得分增益")
    ax.set_ylabel("Sample Count" if locale == "en" else "样本数")
    save_figure(fig, output_dir, basename)


def draw_finetune_wtl_chart(judge_wide_df: pd.DataFrame, locale: str, output_dir: Path, basename: str) -> None:
    rows = []
    for name, left, right in [("Ckpt75 vs Base", "ckpt75", "base"), ("Ckpt140 vs Base", "ckpt140", "base"), ("Ckpt140 vs Ckpt75", "ckpt140", "ckpt75")]:
        delta = judge_wide_df[left] - judge_wide_df[right]
        rows.extend([
            {"comparison": name, "result": "Win", "count": int((delta > 0).sum())},
            {"comparison": name, "result": "Tie", "count": int((delta == 0).sum())},
            {"comparison": name, "result": "Loss", "count": int((delta < 0).sum())},
        ])
    plot_df = pd.DataFrame(rows)
    if locale == "zh":
        plot_df["comparison"] = plot_df["comparison"].replace({"Ckpt75 vs Base": "检查点75 对 原始模型", "Ckpt140 vs Base": "检查点140 对 原始模型", "Ckpt140 vs Ckpt75": "检查点140 对 检查点75"})
        plot_df["result"] = plot_df["result"].replace({"Win": "胜", "Tie": "平", "Loss": "负"})
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    sns.barplot(data=plot_df, x="comparison", y="count", hue="result", palette=["#2a9d8f", "#adb5bd", "#e76f51"], ax=ax)
    ax.set_title("Win / Tie / Loss Comparison" if locale == "en" else "胜平负统计", fontsize=12, weight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Sample Count" if locale == "en" else "样本数")
    ax.legend(title="")
    for container in ax.containers:
        ax.bar_label(container, fmt="%d", padding=2, fontsize=8)
    save_figure(fig, output_dir, basename)


def draw_training_curve(training_df: pd.DataFrame, locale: str, output_dir: Path, basename: str) -> None:
    if training_df.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6))
    train_df = training_df[training_df["loss"].notna()]
    eval_df = training_df[training_df["eval_loss"].notna()]
    sns.lineplot(data=train_df, x="step", y="loss", marker="o", color=PALETTE["ckpt75"], ax=axes[0])
    axes[0].set_title("Training Loss" if locale == "en" else "训练损失", fontsize=11, weight="bold")
    axes[0].set_xlabel("Step" if locale == "en" else "步数")
    axes[0].set_ylabel("Loss")
    if not eval_df.empty:
        sns.lineplot(data=eval_df, x="step", y="eval_loss", marker="o", color=PALETTE["ckpt140"], ax=axes[1])
        axes[1].set_title("Validation Loss" if locale == "en" else "验证损失", fontsize=11, weight="bold")
        axes[1].set_xlabel("Step" if locale == "en" else "步数")
        axes[1].set_ylabel("Eval Loss" if locale == "en" else "验证损失")
    else:
        axes[1].axis("off")
    fig.suptitle("Fine-tuning Learning Curves" if locale == "en" else "微调学习曲线", fontsize=13, weight="bold", y=1.02)
    save_figure(fig, output_dir, basename)


def write_finetune_report(judge_wide_df: pd.DataFrame, training_df: pd.DataFrame, output_dirs: OutputDirs) -> None:
    means = {"base": judge_wide_df["base"].mean(), "ckpt75": judge_wide_df["ckpt75"].mean(), "ckpt140": judge_wide_df["ckpt140"].mean()}
    best_name = max(means, key=means.get)
    delta_75 = (judge_wide_df["ckpt75"] - judge_wide_df["base"]).mean()
    delta_140 = (judge_wide_df["ckpt140"] - judge_wide_df["base"]).mean()
    catastrophic = judge_wide_df[(judge_wide_df["ckpt140"] - judge_wide_df["base"]) < -5]
    text = f"""# 微调实验分析报告

## 1. 总体表现
- 三组模型平均分分别为：Base={means['base']:.3f}，Ckpt75={means['ckpt75']:.3f}，Ckpt140={means['ckpt140']:.3f}。
- 最优检查点为 `{best_name}`。
- 相比 Base，Ckpt75 平均提升 {delta_75:.3f}，Ckpt140 平均提升 {delta_140:.3f}。

## 2. 稳定性判断
- 优先建议使用 `Ckpt75` 作为论文中的最佳 checkpoint。
- `Ckpt140` 整体仍高于 Base，但样本级波动更大。
- 检测到 Ckpt140 对 Base 的显著退化样本数：{len(catastrophic)}。

## 3. 训练过程
- 训练日志共解析出 {len(training_df)} 条有效记录。
- 建议将学习曲线与最佳 checkpoint 结论结合描述。

## 4. 图表清单
- `finetune_overall_scores`
- `finetune_score_distribution`
- `finetune_score_delta_distribution`
- `finetune_wtl`
- `finetune_learning_curves`
"""
    (output_dirs.report / "finetune_analysis.md").write_text(text, encoding="utf-8")


def export_failure_cases(judge_wide_df: pd.DataFrame, output_dirs: OutputDirs) -> None:
    df = judge_wide_df.copy()
    df["delta_75_vs_base"] = df["ckpt75"] - df["base"]
    df["delta_140_vs_base"] = df["ckpt140"] - df["base"]
    worst = df.sort_values("delta_140_vs_base").head(10)
    export_dataframe_bundle(worst, output_dirs.tables / "finetune_failure_cases_v2.csv", output_dirs)


def run_retrieval_analysis() -> None:
    output_dirs = ensure_output_dirs(RETRIEVAL_DIR)
    summary_df, query_df = build_retrieval_frames()
    export_dataframe_bundle(summary_df, output_dirs.tables / "retrieval_summary_v2.csv", output_dirs)
    export_dataframe_bundle(query_df, output_dirs.tables / "retrieval_per_query_v2.csv", output_dirs)

    coco_df = summary_df[summary_df["scope"] == "coco"].copy()
    variants = {
        "with_ocr": ["proposed", "baseline_clip", "baseline_ocr"],
        "without_ocr": ["proposed", "baseline_clip"],
    }
    for locale, fig_dir in [("en", output_dirs.fig_en), ("zh", output_dirs.fig_zh)]:
        set_plot_style(locale)
        for suffix, methods in variants.items():
            draw_grouped_metric_chart(coco_df, methods, ["recall_at_1", "recall_at_5", "recall_at_10", "mrr", "map_at_10"], locale, "COCO Retrieval Performance" if locale == "en" else "COCO检索性能对比", "Score" if locale == "en" else "指标值", fig_dir, f"retrieval_coco_metrics_{suffix}_v2")
            draw_latency_chart(coco_df, methods, locale, fig_dir, f"retrieval_latency_{suffix}_v2")
            draw_domain_metric_chart(summary_df, methods, locale, ["recall_at_1", "mrr"], fig_dir, f"retrieval_domain_metrics_{suffix}_v2")
            draw_heatmap(summary_df, methods, locale, fig_dir, f"retrieval_heatmap_{suffix}_v2")
            draw_rank_bucket_chart(query_df, methods, locale, fig_dir, f"retrieval_first_hit_distribution_{suffix}_v2")
            for domain in sorted(summary_df[summary_df["scope"] != "coco"]["scope"].unique()):
                draw_retrieval_single_domain_chart(summary_df, domain, methods, locale, fig_dir, f"retrieval_{domain}_{suffix}_v2")
    write_retrieval_report(summary_df, output_dirs)


def run_generation_analysis() -> None:
    output_dirs = ensure_output_dirs(GENERATION_DIR)
    summary_df, domain_df, qtype_df = build_generation_frames()
    export_dataframe_bundle(summary_df, output_dirs.tables / "generation_summary_v2.csv", output_dirs)
    export_dataframe_bundle(domain_df, output_dirs.tables / "generation_domain_summary_v2.csv", output_dirs)
    export_dataframe_bundle(qtype_df, output_dirs.tables / "generation_qtype_summary_v2.csv", output_dirs)
    chart_summary_df = summary_df.fillna(0)

    variants = {
        "with_ocr": ["proposed", "baseline_clip", "baseline_ocr", "no_rag"],
        "without_ocr": ["proposed", "baseline_clip", "no_rag"],
    }
    for locale, fig_dir in [("en", output_dirs.fig_en), ("zh", output_dirs.fig_zh)]:
        set_plot_style(locale)
        for suffix, methods in variants.items():
            draw_grouped_metric_chart(chart_summary_df, methods, ["answer_correctness", "answer_relevancy", "image_context_relevancy", "image_faithfulness"], locale, "Generator Evaluation Overview" if locale == "en" else "生成器评测总览", "Score / Pass Rate" if locale == "en" else "得分 / 通过率", fig_dir, f"generation_overall_metrics_{suffix}_v2")
            draw_generation_domain_chart(domain_df, methods, locale, fig_dir, f"generation_domain_correctness_{suffix}_v2")
            draw_generation_qtype_chart(qtype_df, methods, locale, fig_dir, f"generation_qtype_correctness_{suffix}_v2")
            draw_relevancy_faithfulness_chart(chart_summary_df, methods, locale, fig_dir, f"generation_relevancy_faithfulness_{suffix}_v2")
            draw_generation_improvement_chart(chart_summary_df, methods, locale, fig_dir, f"generation_improvement_{suffix}_v2")
    write_generation_report(summary_df, output_dirs)


def run_finetune_analysis() -> None:
    output_dirs = ensure_output_dirs(FINETUNE_DIR)
    long_df, training_df = build_finetune_frames()
    judge_wide_df = long_df.pivot(index="ID", columns="model", values="score").reset_index()
    export_dataframe_bundle(long_df, output_dirs.tables / "finetune_scores_long_v2.csv", output_dirs)
    export_dataframe_bundle(judge_wide_df, output_dirs.tables / "finetune_scores_wide_v2.csv", output_dirs)
    export_dataframe_bundle(training_df, output_dirs.tables / "finetune_training_curve_v3.csv", output_dirs)

    for locale, fig_dir in [("en", output_dirs.fig_en), ("zh", output_dirs.fig_zh)]:
        set_plot_style(locale)
        draw_finetune_overall_chart(long_df, locale, fig_dir, "finetune_overall_scores_v2")
        draw_finetune_distribution_chart(long_df, locale, fig_dir, "finetune_score_distribution_v2")
        draw_finetune_delta_chart(judge_wide_df, locale, fig_dir, "finetune_score_delta_distribution_v2")
        draw_finetune_wtl_chart(judge_wide_df, locale, fig_dir, "finetune_wtl_v2")
        draw_training_curve(training_df, locale, fig_dir, "finetune_learning_curves_v3")

    export_failure_cases(judge_wide_df, output_dirs)
    write_finetune_report(judge_wide_df, training_df, output_dirs)


def main() -> None:
    run_retrieval_analysis()
    run_generation_analysis()
    run_finetune_analysis()
    print("Analysis complete. Outputs saved under each experiment directory's analysis/ folder.")


if __name__ == "__main__":
    main()
