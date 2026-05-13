from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "实验数据" / "检索器"
ANALYSIS_DIR = DATA_ROOT / "analysis_2"
FIG_ZH_DIR = ANALYSIS_DIR / "figures_zh"
FIG_EN_DIR = ANALYSIS_DIR / "figures_en"
TABLE_DIR = ANALYSIS_DIR / "tables"
REPORT_DIR = ANALYSIS_DIR / "report"

PERSIST_DIR = ROOT / "backend" / "chroma_data"
RETRIEVAL_SUMMARY_CSV = ANALYSIS_DIR / "tables" / "retrieval_summary_v2.csv"

PALETTE = {
    "ocr": "#7f7f7f",
    "proposed": "#1f77b4",
}

METHOD_LABELS = {
    "ocr": {"zh": "OCR基线", "en": "Baseline-OCR"},
    "proposed": {"zh": "本文方法", "en": "Proposed"},
}

DOMAIN_LABELS = {
    "commerce_manufacturing": {"en": "Commerce & Manu.", "zh": "商贸制造"},
    "construction": {"en": "Construction", "zh": "建筑"},
    "crm": {"en": "CRM", "zh": "客户管理"},
    "education": {"en": "Education", "zh": "教育"},
    "energy": {"en": "Energy", "zh": "能源"},
    "finance": {"en": "Finance", "zh": "金融"},
    "healthcare": {"en": "Healthcare", "zh": "医疗"},
    "legal": {"en": "Legal", "zh": "法律"},
}


@dataclass
class OutputDirs:
    fig_zh: Path
    fig_en: Path
    tables: Path
    report: Path


def ensure_output_dirs() -> OutputDirs:
    for path in (FIG_ZH_DIR, FIG_EN_DIR, TABLE_DIR, REPORT_DIR):
        path.mkdir(parents=True, exist_ok=True)
    return OutputDirs(fig_zh=FIG_ZH_DIR, fig_en=FIG_EN_DIR, tables=TABLE_DIR, report=REPORT_DIR)


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


def label_for_method(method: str, locale: str) -> str:
    return METHOD_LABELS.get(method, {"zh": method, "en": method})[locale]


def label_for_domain(domain: str, locale: str) -> str:
    return DOMAIN_LABELS.get(domain, {"zh": domain, "en": domain})[locale]


def parse_domain(image_id: str) -> str:
    parts = image_id.replace("\\", "/").split("/")
    return parts[1] if len(parts) > 1 else "unknown"


def load_collection_documents(client: chromadb.Client, collection_name: str) -> pd.DataFrame:
    collection = client.get_collection(collection_name)
    total = collection.count()
    batch_size = 200
    rows = []
    for offset in range(0, total, batch_size):
        chunk = collection.get(limit=batch_size, offset=offset, include=["documents"])
        ids = chunk.get("ids") or []
        documents = chunk.get("documents") or []
        for image_id, document in zip(ids, documents):
            text = document or ""
            rows.append(
                {
                    "image_id": image_id,
                    "domain": parse_domain(str(image_id)),
                    "text": text,
                    "chars": len(text),
                    "utf8_bytes": len(text.encode("utf-8")),
                    "words": len(text.split()),
                }
            )
    return pd.DataFrame(rows)


def load_retrieval_metrics() -> pd.DataFrame:
    summary_df = pd.read_csv(RETRIEVAL_SUMMARY_CSV, encoding="utf-8-sig")
    summary_df = summary_df[(summary_df["scope"] == "crossdomain") & (summary_df["method"].isin(["baseline_ocr", "proposed"]))].copy()
    summary_df["method_key"] = summary_df["method"].map({"baseline_ocr": "ocr", "proposed": "proposed"})
    summary_df["recall_at_10"] = summary_df["recall_at_10"].astype(float)
    summary_df["mrr"] = summary_df["mrr"].astype(float)
    return summary_df[["method_key", "recall_at_10", "mrr"]]


def build_summary_frames(ocr_df: pd.DataFrame, proposed_df: pd.DataFrame, retrieval_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    method_frames = []
    for method_key, frame in (("ocr", ocr_df), ("proposed", proposed_df)):
        method_frames.append(
            {
                "method_key": method_key,
                "method": label_for_method(method_key, "en"),
                "count": int(len(frame)),
                "char_total": int(frame["chars"].sum()),
                "char_mean": round(frame["chars"].mean(), 2),
                "char_median": round(frame["chars"].median(), 2),
                "utf8_total": int(frame["utf8_bytes"].sum()),
                "utf8_mean": round(frame["utf8_bytes"].mean(), 2),
                "utf8_median": round(frame["utf8_bytes"].median(), 2),
                "word_total": int(frame["words"].sum()),
                "word_mean": round(frame["words"].mean(), 2),
                "word_median": round(frame["words"].median(), 2),
            }
        )
    summary_df = pd.DataFrame(method_frames).merge(retrieval_df, on="method_key", how="left")

    ocr_named = ocr_df.rename(columns={"chars": "ocr_chars", "utf8_bytes": "ocr_utf8_bytes", "words": "ocr_words"}).drop(columns=["text"])
    proposed_named = proposed_df.rename(columns={"chars": "proposed_chars", "utf8_bytes": "proposed_utf8_bytes", "words": "proposed_words"}).drop(columns=["text"])
    pairwise_df = ocr_named.merge(proposed_named, on=["image_id", "domain"], how="inner")
    pairwise_df["char_delta"] = pairwise_df["proposed_chars"] - pairwise_df["ocr_chars"]
    pairwise_df["utf8_delta"] = pairwise_df["proposed_utf8_bytes"] - pairwise_df["ocr_utf8_bytes"]
    pairwise_df["word_delta"] = pairwise_df["proposed_words"] - pairwise_df["ocr_words"]
    pairwise_df["char_ratio"] = pairwise_df["proposed_chars"] / pairwise_df["ocr_chars"]
    pairwise_df["utf8_ratio"] = pairwise_df["proposed_utf8_bytes"] / pairwise_df["ocr_utf8_bytes"]
    pairwise_df["word_ratio"] = pairwise_df["proposed_words"] / pairwise_df["ocr_words"]

    pairwise_summary_df = pd.DataFrame(
        [
            {
                "metric": "chars",
                "proposed_shorter_count": int((pairwise_df["char_delta"] < 0).sum()),
                "equal_count": int((pairwise_df["char_delta"] == 0).sum()),
                "proposed_longer_count": int((pairwise_df["char_delta"] > 0).sum()),
                "proposed_mean_ratio": round(pairwise_df["char_ratio"].mean(), 4),
                "proposed_median_ratio": round(pairwise_df["char_ratio"].median(), 4),
            },
            {
                "metric": "utf8_bytes",
                "proposed_shorter_count": int((pairwise_df["utf8_delta"] < 0).sum()),
                "equal_count": int((pairwise_df["utf8_delta"] == 0).sum()),
                "proposed_longer_count": int((pairwise_df["utf8_delta"] > 0).sum()),
                "proposed_mean_ratio": round(pairwise_df["utf8_ratio"].mean(), 4),
                "proposed_median_ratio": round(pairwise_df["utf8_ratio"].median(), 4),
            },
            {
                "metric": "words",
                "proposed_shorter_count": int((pairwise_df["word_delta"] < 0).sum()),
                "equal_count": int((pairwise_df["word_delta"] == 0).sum()),
                "proposed_longer_count": int((pairwise_df["word_delta"] > 0).sum()),
                "proposed_mean_ratio": round(pairwise_df["word_ratio"].mean(), 4),
                "proposed_median_ratio": round(pairwise_df["word_ratio"].median(), 4),
            },
        ]
    )

    domain_rows = []
    for method_key, frame in (("ocr", ocr_df), ("proposed", proposed_df)):
        grouped = frame.groupby("domain", as_index=False).agg(
            count=("image_id", "size"),
            char_mean=("chars", "mean"),
            utf8_mean=("utf8_bytes", "mean"),
            word_mean=("words", "mean"),
            char_median=("chars", "median"),
            word_median=("words", "median"),
        )
        grouped["method_key"] = method_key
        domain_rows.append(grouped)
    by_domain_df = pd.concat(domain_rows, ignore_index=True)
    by_domain_df["char_mean"] = by_domain_df["char_mean"].round(2)
    by_domain_df["utf8_mean"] = by_domain_df["utf8_mean"].round(2)
    by_domain_df["word_mean"] = by_domain_df["word_mean"].round(2)
    by_domain_df["char_median"] = by_domain_df["char_median"].round(2)
    by_domain_df["word_median"] = by_domain_df["word_median"].round(2)

    return {
        "summary": summary_df,
        "pairwise": pairwise_df,
        "pairwise_summary": pairwise_summary_df,
        "by_domain": by_domain_df,
    }


def write_csv_bundle(outputs: OutputDirs, summary_df: pd.DataFrame, by_domain_df: pd.DataFrame, pairwise_df: pd.DataFrame, pairwise_summary_df: pd.DataFrame) -> None:
    summary_df.to_csv(outputs.tables / "retrieval_index_capacity_summary.csv", index=False, encoding="utf-8-sig")
    by_domain_df.to_csv(outputs.tables / "retrieval_index_capacity_by_domain.csv", index=False, encoding="utf-8-sig")
    pairwise_df.to_csv(outputs.tables / "retrieval_index_capacity_per_page.csv", index=False, encoding="utf-8-sig")
    pairwise_summary_df.to_csv(outputs.tables / "retrieval_index_capacity_pairwise_summary.csv", index=False, encoding="utf-8-sig")


def draw_overview(summary_df: pd.DataFrame, locale: str, out_dir: Path) -> None:
    order = ["ocr", "proposed"]
    plot_df = summary_df.copy()
    plot_df["method_label"] = plot_df["method_key"].map(lambda x: label_for_method(x, locale))

    size_metrics = [
        ("char_mean", "Chars / Page" if locale == "en" else "每页字符数"),
        ("word_mean", "Words / Page" if locale == "en" else "每页词数"),
        ("utf8_mean", "UTF-8 Bytes / Page" if locale == "en" else "每页UTF-8字节数"),
    ]
    retrieval_metrics = [
        ("recall_at_10", "Recall@10"),
        ("mrr", "MRR"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.2))
    size_melted = plot_df.melt(
        id_vars=["method_key", "method_label"],
        value_vars=[m for m, _ in size_metrics],
        var_name="metric",
        value_name="value",
    )
    size_label_map = {metric: label for metric, label in size_metrics}
    size_melted["metric_label"] = size_melted["metric"].map(size_label_map)
    sns.barplot(
        data=size_melted,
        x="metric_label",
        y="value",
        hue="method_label",
        order=[label for _, label in size_metrics],
        hue_order=[label_for_method(m, locale) for m in order],
        palette=[PALETTE[m] for m in order],
        ax=axes[0],
    )
    axes[0].set_title("Index Text Size" if locale == "en" else "索引文本篇幅")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("Average per page" if locale == "en" else "平均每页")
    axes[0].tick_params(axis="x", rotation=10)
    for container in axes[0].containers:
        axes[0].bar_label(container, fmt="%.0f", fontsize=8, padding=2)

    retrieval_melted = plot_df.melt(
        id_vars=["method_key", "method_label"],
        value_vars=[m for m, _ in retrieval_metrics],
        var_name="metric",
        value_name="value",
    )
    retrieval_label_map = {metric: label for metric, label in retrieval_metrics}
    retrieval_melted["metric_label"] = retrieval_melted["metric"].map(retrieval_label_map)
    sns.barplot(
        data=retrieval_melted,
        x="metric_label",
        y="value",
        hue="method_label",
        order=[label for _, label in retrieval_metrics],
        hue_order=[label_for_method(m, locale) for m in order],
        palette=[PALETTE[m] for m in order],
        ax=axes[1],
    )
    axes[1].set_title("Retrieval Quality" if locale == "en" else "检索效果")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("Score")
    axes[1].set_ylim(0, 1.05)
    for container in axes[1].containers:
        axes[1].bar_label(container, fmt="%.4f", fontsize=8, padding=2)

    handles, labels = axes[1].get_legend_handles_labels()
    axes[0].legend_.remove()
    axes[1].legend(handles, labels, title="", loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2, frameon=True)
    title = "Index Capacity vs Retrieval Quality" if locale == "en" else "索引容量与检索效果对照"
    fig.suptitle(title, fontsize=12, weight="bold", y=1.03)
    save_figure(fig, out_dir, "retrieval_index_capacity_overview_v1")


def draw_reduction_chart(summary_df: pd.DataFrame, locale: str, out_dir: Path) -> None:
    ocr_row = summary_df[summary_df["method_key"] == "ocr"].iloc[0]
    proposed_row = summary_df[summary_df["method_key"] == "proposed"].iloc[0]
    rows = []
    for metric, label in [
        ("char_total", "Total chars" if locale == "en" else "总字符数"),
        ("word_total", "Total words" if locale == "en" else "总词数"),
        ("utf8_total", "Total UTF-8 bytes" if locale == "en" else "总UTF-8字节数"),
        ("char_mean", "Chars / page" if locale == "en" else "每页字符数"),
        ("word_mean", "Words / page" if locale == "en" else "每页词数"),
        ("utf8_mean", "UTF-8 bytes / page" if locale == "en" else "每页UTF-8字节数"),
    ]:
        rows.append(
            {
                "metric_label": label,
                "ratio": proposed_row[metric] / ocr_row[metric],
                "reduction": 1 - proposed_row[metric] / ocr_row[metric],
            }
        )
    plot_df = pd.DataFrame(rows).sort_values("ratio", ascending=True)

    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    sns.barplot(data=plot_df, x="ratio", y="metric_label", color=PALETTE["proposed"], ax=ax)
    ax.axvline(1.0, color="#6c757d", linestyle="--", linewidth=1)
    ax.set_xlim(0, 1.08)
    ax.set_xlabel("Proposed / OCR" if locale == "en" else "本文方法 / OCR基线")
    ax.set_ylabel("")
    ax.set_title("Relative Index Footprint" if locale == "en" else "相对索引容量")
    for patch, (_, row) in zip(ax.patches, plot_df.iterrows()):
        ax.text(
            patch.get_width() + 0.015,
            patch.get_y() + patch.get_height() / 2,
            f"{row['ratio']:.3f} ({row['reduction'] * 100:.1f}%↓)",
            va="center",
            fontsize=8,
        )
    save_figure(fig, out_dir, "retrieval_index_capacity_reduction_v1")


def draw_domain_chart(by_domain_df: pd.DataFrame, locale: str, out_dir: Path) -> None:
    order = ["commerce_manufacturing", "construction", "crm", "education", "energy", "finance", "healthcare", "legal"]
    plot_df = by_domain_df.copy()
    plot_df["domain_label"] = plot_df["domain"].map(lambda x: label_for_domain(x, locale))
    plot_df["method_label"] = plot_df["method_key"].map(lambda x: label_for_method(x, locale))

    fig, axes = plt.subplots(2, 1, figsize=(11.0, 7.2), sharex=True)
    for ax, value_col, title in [
        (axes[0], "char_mean", "Average chars by domain" if locale == "en" else "各领域平均字符数"),
        (axes[1], "word_mean", "Average words by domain" if locale == "en" else "各领域平均词数"),
    ]:
        sns.barplot(
            data=plot_df,
            x="domain_label",
            y=value_col,
            hue="method_label",
            order=[label_for_domain(d, locale) for d in order],
            hue_order=[label_for_method("ocr", locale), label_for_method("proposed", locale)],
            palette=[PALETTE["ocr"], PALETTE["proposed"]],
            ax=ax,
        )
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("")
        ax.set_ylabel("Average per page" if locale == "en" else "平均每页")
        ax.tick_params(axis="x", rotation=15)
    axes[0].legend(title="", loc="upper center", bbox_to_anchor=(0.5, 1.22), ncol=2, frameon=True)
    axes[1].legend_.remove()
    fig.suptitle("Domain-wise Index Length Comparison" if locale == "en" else "分领域索引长度对比", fontsize=12, weight="bold", y=1.02)
    save_figure(fig, out_dir, "retrieval_index_capacity_by_domain_v1")


def draw_distribution_chart(pairwise_df: pd.DataFrame, locale: str, out_dir: Path) -> None:
    long_df = []
    for metric, value_ocr, value_prop, metric_label in [
        ("chars", "ocr_chars", "proposed_chars", "Chars / page" if locale == "en" else "每页字符数"),
        ("words", "ocr_words", "proposed_words", "Words / page" if locale == "en" else "每页词数"),
    ]:
        for method_key, column in [("ocr", value_ocr), ("proposed", value_prop)]:
            temp = pairwise_df[["image_id", column]].copy()
            temp["metric"] = metric_label
            temp["method_label"] = label_for_method(method_key, locale)
            temp["value"] = temp[column]
            long_df.append(temp[["image_id", "metric", "method_label", "value"]])
    plot_df = pd.concat(long_df, ignore_index=True)

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.3))
    for ax, metric_label in zip(axes, plot_df["metric"].drop_duplicates().tolist()):
        subset = plot_df[plot_df["metric"] == metric_label]
        sns.violinplot(
            data=subset,
            x="method_label",
            y="value",
            hue="method_label",
            palette=[PALETTE["ocr"], PALETTE["proposed"]],
            cut=0,
            inner="quartile",
            legend=False,
            ax=ax,
        )
        ax.set_title(metric_label)
        ax.set_xlabel("")
        ax.set_ylabel("Value")
    fig.suptitle("Per-page Length Distribution" if locale == "en" else "逐页长度分布", fontsize=12, weight="bold", y=1.02)
    save_figure(fig, out_dir, "retrieval_index_capacity_distribution_v1")


def draw_pairwise_chart(pairwise_df: pd.DataFrame, pairwise_summary_df: pd.DataFrame, locale: str, out_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2))

    sns.histplot(pairwise_df["char_delta"], bins=40, color=PALETTE["proposed"], ax=axes[0])
    axes[0].axvline(0, color="#6c757d", linestyle="--", linewidth=1)
    axes[0].set_title("Per-page char delta" if locale == "en" else "逐页字符差值")
    axes[0].set_xlabel("Proposed - OCR" if locale == "en" else "本文方法 - OCR基线")
    axes[0].set_ylabel("Pages" if locale == "en" else "页数")

    stacked_df = pairwise_summary_df[pairwise_summary_df["metric"].isin(["chars", "utf8_bytes", "words"])].copy()
    stacked_df["metric_label"] = stacked_df["metric"].map(
        {
            "chars": "Chars" if locale == "en" else "字符数",
            "utf8_bytes": "UTF-8 bytes" if locale == "en" else "UTF-8字节数",
            "words": "Words" if locale == "en" else "词数",
        }
    )
    shorter = stacked_df["proposed_shorter_count"]
    equal = stacked_df["equal_count"]
    longer = stacked_df["proposed_longer_count"]
    x = range(len(stacked_df))
    axes[1].bar(x, shorter, color=PALETTE["proposed"], label="Proposed shorter" if locale == "en" else "本文方法更短")
    axes[1].bar(x, equal, bottom=shorter, color="#ced4da", label="Equal" if locale == "en" else "相同")
    axes[1].bar(x, longer, bottom=shorter + equal, color=PALETTE["ocr"], label="OCR shorter" if locale == "en" else "OCR更短")
    axes[1].set_xticks(list(x))
    axes[1].set_xticklabels(stacked_df["metric_label"].tolist())
    axes[1].set_title("Pairwise shorter/longer counts" if locale == "en" else "逐页长短胜负统计")
    axes[1].set_ylabel("Pages" if locale == "en" else "页数")
    axes[1].legend(title="", fontsize=8)

    fig.suptitle("Pairwise Compactness Analysis" if locale == "en" else "逐页紧凑性分析", fontsize=12, weight="bold", y=1.03)
    save_figure(fig, out_dir, "retrieval_index_capacity_pairwise_v1")


def write_report(outputs: OutputDirs, summary_df: pd.DataFrame, pairwise_df: pd.DataFrame, pairwise_summary_df: pd.DataFrame) -> None:
    ocr_row = summary_df[summary_df["method_key"] == "ocr"].iloc[0]
    proposed_row = summary_df[summary_df["method_key"] == "proposed"].iloc[0]
    char_ratio = proposed_row["char_total"] / ocr_row["char_total"]
    word_ratio = proposed_row["word_total"] / ocr_row["word_total"]
    byte_ratio = proposed_row["utf8_total"] / ocr_row["utf8_total"]
    recall_gap = proposed_row["recall_at_10"] - ocr_row["recall_at_10"]
    mrr_gap = proposed_row["mrr"] - ocr_row["mrr"]
    char_shorter = int((pairwise_df["char_delta"] < 0).sum())
    total = len(pairwise_df)

    report = f"""# 索引容量对比分析

## 数据来源
- 向量库目录：`{PERSIST_DIR}`
- OCR 集合：`unidoc_crossdomain_ocr`
- Proposed 集合：`unidoc_crossdomain_proposed`
- 检索指标来源：`{RETRIEVAL_SUMMARY_CSV}`

## 核心结论
- 在 947 个跨领域候选页上，本文方法索引文本总字符数为 OCR 基线的 `{char_ratio:.4f}`，总词数为 `{word_ratio:.4f}`。
- 换言之，本文方法相对 OCR 基线减少了 `{(1 - char_ratio) * 100:.2f}%` 的字符量，以及 `{(1 - word_ratio) * 100:.2f}%` 的词量。
- 如果按 UTF-8 字节统计，本文方法仍减少 `{(1 - byte_ratio) * 100:.2f}%`，但降幅显著小于字符数和词数，说明中文描述带来的多字节编码开销抵消了部分字符压缩收益。
- 在检索效果上，本文方法的 Recall@10 为 `{proposed_row['recall_at_10']:.4f}`，OCR 基线为 `{ocr_row['recall_at_10']:.4f}`，差值为 `{recall_gap:+.4f}`。
- 本文方法的 MRR 为 `{proposed_row['mrr']:.4f}`，OCR 基线为 `{ocr_row['mrr']:.4f}`，差值为 `{mrr_gap:+.4f}`。
- 逐页比较显示，本文方法在 `{char_shorter}/{total}` 页上字符数更短，占比 `{char_shorter / total * 100:.2f}%`。

## 图表建议
- `retrieval_index_capacity_overview_v1`：正文主图，直接展示“更短篇幅 vs 接近效果”。
- `retrieval_index_capacity_reduction_v1`：适合正文或附录，强调各类容量指标的相对缩减。
- `retrieval_index_capacity_by_domain_v1`：用于说明压缩效果在不同领域上具有一致性。
- `retrieval_index_capacity_distribution_v1` 与 `retrieval_index_capacity_pairwise_v1`：适合附录或补充分析。
"""
    (outputs.report / "retrieval_index_capacity_analysis.md").write_text(report, encoding="utf-8")


def main() -> None:
    outputs = ensure_output_dirs()
    client = chromadb.Client(
        ChromaSettings(
            is_persistent=True,
            persist_directory=str(PERSIST_DIR),
        )
    )

    ocr_df = load_collection_documents(client, "unidoc_crossdomain_ocr")
    proposed_df = load_collection_documents(client, "unidoc_crossdomain_proposed")
    retrieval_df = load_retrieval_metrics()

    frames = build_summary_frames(ocr_df, proposed_df, retrieval_df)
    write_csv_bundle(outputs, frames["summary"], frames["by_domain"], frames["pairwise"], frames["pairwise_summary"])
    write_report(outputs, frames["summary"], frames["pairwise"], frames["pairwise_summary"])

    for locale, out_dir in (("zh", outputs.fig_zh), ("en", outputs.fig_en)):
        set_plot_style(locale)
        draw_overview(frames["summary"], locale, out_dir)
        draw_reduction_chart(frames["summary"], locale, out_dir)
        draw_domain_chart(frames["by_domain"], locale, out_dir)
        draw_distribution_chart(frames["pairwise"], locale, out_dir)
        draw_pairwise_chart(frames["pairwise"], frames["pairwise_summary"], locale, out_dir)

    payload = {
        "persist_dir": str(PERSIST_DIR),
        "summary_csv": str(outputs.tables / "retrieval_index_capacity_summary.csv"),
        "by_domain_csv": str(outputs.tables / "retrieval_index_capacity_by_domain.csv"),
        "pairwise_csv": str(outputs.tables / "retrieval_index_capacity_per_page.csv"),
        "report": str(outputs.report / "retrieval_index_capacity_analysis.md"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
