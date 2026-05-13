"""性能审计工具：收集、汇总并渲染 API 端点的计时审计结果。

架构角色：应用层性能分析工具，用于从 SSE 流式响应中提取各阶段耗时数据，
按场景（scenario）聚合统计指标，识别性能瓶颈，生成 Markdown 报告。

核心导出：
- extract_stream_timings: 从 SSE 流中解析计时数据
- summarize_audit_runs: 汇总多次运行结果为结构化统计
- render_audit_markdown: 将汇总结果渲染为 Markdown 报告
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any, Iterable


# ---- 瓶颈过滤规则 ----
# 以下阶段在 "可操作瓶颈" 列表中被排除，因为它们是聚合/总耗时阶段，不具备独立优化意义。

ACTIONABLE_STAGE_PREFIX_EXCLUDES = ("adapter_",)  # 排除 adapter_ 前缀的阶段（门面层）
ACTIONABLE_STAGE_EXACT_EXCLUDES = {
    "rag_chat_total",                  # RAG 聊天总耗时
    "rag_chat_stream_total",           # RAG 流式聊天总耗时
    "text_to_image_total",             # 文本检索图片总耗时
    "image_to_image_total",            # 图片检索图片总耗时
    "knowledge_base_upload_total",     # 知识库上传总耗时
    "document_upload_total",           # 文档上传总耗时
    "document_progress_total",         # 文档进度查询总耗时
    "document_result_total",           # 文档结果查询总耗时
    "process_image_upload",            # 图片上传处理（聚合步骤）
    "process_image_uploads",           # 批量图片上传处理
    "text_to_image_search_internal",   # 文本检索内部调用
    "image_to_image_search_internal",  # 图片检索内部调用
    "async_search_with_dict_output",   # 异步搜索字典输出
}


# ---- SSE 流式响应解析 ----

def extract_stream_timings(sse_payload: str) -> dict[str, Any] | None:
    """从 SSE 流式响应中提取 "results" 事件的 timings 字段。

    遍历 SSE payload 的每一行，解析 JSON 格式的 data 字段，
    查找 type 为 "results" 且包含 timings 字典的事件。

    Args:
        sse_payload: 完整的 SSE 流式响应文本

    Returns:
        timings 字典（含 total_ms、stages 等），未找到时返回 None
    """
    """Extract timings from the final SSE results event."""
    for raw_line in sse_payload.splitlines():
        line = raw_line.strip()
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "results" and isinstance(event.get("timings"), dict):
            return event["timings"]
    return None


# ---- 统计计算工具 ----

def _percentile(values: list[float], pct: float) -> float:
    """计算给定百分位数，使用线性插值法（与 NumPy 默认一致）。

    Args:
        values: 数值列表（非空）
        pct: 百分位数，0.0-1.0 范围（如 0.95 表示 P95）

    Returns:
        保留 3 位小数的百分位数值
    """
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 3)
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    interpolated = ordered[lower] + (ordered[upper] - ordered[lower]) * weight
    return round(interpolated, 3)


def _build_stats(values: Iterable[float]) -> dict[str, float | int] | None:
    """构建基础统计摘要：count、min、max、avg、p50、p90、p95。

    输入为空时返回 None。
    """
    numeric = [float(v) for v in values]
    if not numeric:
        return None
    return {
        "count": len(numeric),
        "min": round(min(numeric), 3),
        "max": round(max(numeric), 3),
        "avg": round(sum(numeric) / len(numeric), 3),
        "p50": _percentile(numeric, 0.5),
        "p90": _percentile(numeric, 0.9),
        "p95": _percentile(numeric, 0.95),
    }


# ---- 审计结果汇总 ----

def summarize_audit_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """将多次审计运行结果汇总为结构化统计。

    处理流程：
    1. 按 scenario_name 分组所有运行结果
    2. 对每个场景计算：成功率、wall_ms / total_ms / first_token_ms 统计、
       各阶段耗时及占比
    3. 跨场景汇总全局瓶颈排名（按平均占比降序）
    4. 过滤出"可操作"瓶颈（排除聚合阶段和 adapter 层）

    Args:
        runs: 运行结果列表，每个元素包含 scenario_name, endpoint, ok, error,
              wall_ms, timings 等字段

    Returns:
        汇总字典，结构为:
        {
            "overall": {总运行数、成功数、失败数、超时数、场景数},
            "scenarios": {场景名 -> 场景统计},
            "bottlenecks": [全局瓶颈 Top 10],
            "actionable_bottlenecks": [可操作瓶颈 Top 10]
        }
    """
    scenario_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)  # 场景名 -> 运行列表
    stage_elapsed: dict[str, list[float]] = defaultdict(list)  # 阶段名 -> 耗时列表（全局）
    stage_share: dict[str, list[float]] = defaultdict(list)    # 阶段名 -> 占比列表（全局）

    success_runs = 0  # 成功运行计数
    timeout_runs = 0  # 超时运行计数

    # ---- 第一轮遍历：分组 + 全局阶段统计 ----
    for run in runs:
        scenario_name = str(run.get("scenario_name", "unknown"))
        scenario_groups[scenario_name].append(run)
        if run.get("ok"):
            success_runs += 1
        if "timeout" in str(run.get("error", "")).lower():
            timeout_runs += 1

        timings = run.get("timings") or {}
        total_ms = float(timings.get("total_ms", 0.0) or 0.0)
        if total_ms <= 0:
            continue
        for stage in timings.get("stages") or []:
            name = str(stage.get("name", "unknown"))
            elapsed_ms = float(stage.get("elapsed_ms", 0.0) or 0.0)
            stage_elapsed[name].append(elapsed_ms)
            stage_share[name].append(elapsed_ms / total_ms if total_ms else 0.0)

    # ---- 第二轮遍历：按场景聚合统计 ----
    scenarios: dict[str, dict[str, Any]] = {}
    for scenario_name, group in scenario_groups.items():
        successful = [run for run in group if run.get("ok")]  # 成功的运行
        timing_successes = [run for run in successful if run.get("timings")]  # 含计时数据的运行
        total_runs = len(group)
        success_count = len(successful)
        endpoint = next((str(run.get("endpoint")) for run in group if run.get("endpoint")), "")
        wall_stats = _build_stats(run.get("wall_ms", 0.0) for run in successful)        # 墙钟时间统计
        total_stats = _build_stats(
            (run.get("timings") or {}).get("total_ms", 0.0)
            for run in timing_successes
        )  # 服务端总耗时统计
        first_token_stats = _build_stats(
            (run.get("timings") or {}).get("first_token_ms")
            for run in timing_successes
            if (run.get("timings") or {}).get("first_token_ms") is not None
        )  # 首 token 延迟统计（仅流式场景有值）

        # 场景级阶段统计（仅统计当前场景的运行）
        local_stage_elapsed: dict[str, list[float]] = defaultdict(list)
        local_stage_share: dict[str, list[float]] = defaultdict(list)
        for run in timing_successes:
            timings = run.get("timings") or {}
            total_ms = float(timings.get("total_ms", 0.0) or 0.0)
            if total_ms <= 0:
                continue
            for stage in timings.get("stages") or []:
                stage_name = str(stage.get("name", "unknown"))
                elapsed_ms = float(stage.get("elapsed_ms", 0.0) or 0.0)
                local_stage_elapsed[stage_name].append(elapsed_ms)
                local_stage_share[stage_name].append(elapsed_ms / total_ms if total_ms else 0.0)

        top_stages = []
        for stage_name, elapsed_values in local_stage_elapsed.items():
            avg_share = sum(local_stage_share[stage_name]) / len(local_stage_share[stage_name])
            top_stages.append(
                {
                    "name": stage_name,
                    "avg_elapsed_ms": round(sum(elapsed_values) / len(elapsed_values), 3),
                    "avg_share": round(avg_share, 4),
                    "run_count": len(elapsed_values),
                }
            )
        # 按平均占比降序、平均耗时降序、名称升序排列
        top_stages.sort(key=lambda item: (-item["avg_share"], -item["avg_elapsed_ms"], item["name"]))

        scenarios[scenario_name] = {
            "scenario_name": scenario_name,
            "endpoint": endpoint,
            "run_count": total_runs,
            "success_count": success_count,
            "success_rate": round(success_count / total_runs, 4) if total_runs else 0.0,
            "wall_ms": wall_stats,
            "timing_total_ms": total_stats,
            "first_token_ms": first_token_stats,
            "top_stages": top_stages[:5],  # 每个场景只保留 Top 5 阶段
        }

    # ---- 全局瓶颈分析：跨场景汇总各阶段耗时 ----
    bottlenecks = []
    for stage_name, elapsed_values in stage_elapsed.items():
        avg_share = sum(stage_share[stage_name]) / len(stage_share[stage_name])
        bottlenecks.append(
            {
                "name": stage_name,
                "avg_elapsed_ms": round(sum(elapsed_values) / len(elapsed_values), 3),
                "avg_share": round(avg_share, 4),
                "run_count": len(elapsed_values),
            }
        )
    bottlenecks.sort(key=lambda item: (-item["avg_share"], -item["avg_elapsed_ms"], item["name"]))

    # 过滤可操作瓶颈：排除聚合阶段（如 *_total）和 adapter 门面层
    actionable_bottlenecks = [
        item
        for item in bottlenecks
        if item["name"] not in ACTIONABLE_STAGE_EXACT_EXCLUDES
        and not item["name"].startswith(ACTIONABLE_STAGE_PREFIX_EXCLUDES)
    ]

    return {
        "overall": {
            "run_count": len(runs),
            "success_count": success_runs,
            "failure_count": len(runs) - success_runs,
            "timeout_count": timeout_runs,
            "scenario_count": len(scenarios),
        },
        "scenarios": scenarios,
        "bottlenecks": bottlenecks[:10],
        "actionable_bottlenecks": actionable_bottlenecks[:10],
    }


def render_audit_markdown(summary: dict[str, Any]) -> str:
    """将审计汇总结果渲染为 Markdown 格式报告。

    报告包含以下章节：
    - Overview：总运行数、成功/失败/超时数
    - Scenario Summary：各场景的成功率、P50/P95 总耗时、首 token 延迟
    - Top Bottlenecks：全局 Top 10 瓶颈阶段
    - Actionable Bottlenecks：可操作的 Top 10 瓶颈（排除聚合阶段）
    - Scenario Details：每个场景的详细统计和 Top 5 阶段

    参数:
        summary: summarize_audit_runs 返回的汇总字典。

    返回:
        Markdown 格式的报告文本。
    """
    overall = summary.get("overall", {})
    scenarios = summary.get("scenarios", {})
    bottlenecks = summary.get("bottlenecks", [])
    actionable_bottlenecks = summary.get("actionable_bottlenecks", [])

    # ---- Overview 章节：总运行统计 ----
    lines = [
        "# Performance Audit Report",
        "",
        "## Overview",
        "",
        f"- Runs: {overall.get('run_count', 0)}",
        f"- Successes: {overall.get('success_count', 0)}",
        f"- Failures: {overall.get('failure_count', 0)}",
        f"- Timeouts: {overall.get('timeout_count', 0)}",
        "",
        "## Scenario Summary",
        "",
        "| Scenario | Endpoint | Success Rate | P50 Total (ms) | P95 Total (ms) | P50 First Token (ms) |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]

    # ---- Scenario Summary 章节：各场景关键指标表格 ----
    for scenario_name, scenario in scenarios.items():
        total_stats = scenario.get("timing_total_ms") or {}
        first_token_stats = scenario.get("first_token_ms") or {}
        lines.append(
            "| {scenario} | {endpoint} | {success_rate:.1%} | {p50_total} | {p95_total} | {p50_first_token} |".format(
                scenario=scenario_name,
                endpoint=scenario.get("endpoint", ""),
                success_rate=scenario.get("success_rate", 0.0),
                p50_total=total_stats.get("p50", "-"),
                p95_total=total_stats.get("p95", "-"),
                p50_first_token=first_token_stats.get("p50", "-"),
            )
        )

    # ---- Top Bottlenecks 章节：全局瓶颈排行 ----
    lines.extend(
        [
            "",
            "## Top Bottlenecks",
            "",
            "| Stage | Avg Elapsed (ms) | Avg Share | Runs |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for item in bottlenecks:
        lines.append(
            "| {name} | {avg_elapsed_ms} | {avg_share:.1%} | {run_count} |".format(
                name=item["name"],
                avg_elapsed_ms=item["avg_elapsed_ms"],
                avg_share=item["avg_share"],
                run_count=item["run_count"],
            )
        )

    # ---- Actionable Bottlenecks 章节：可操作瓶颈（排除聚合阶段） ----
    lines.extend(
        [
            "",
            "## Actionable Bottlenecks",
            "",
            "| Stage | Avg Elapsed (ms) | Avg Share | Runs |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for item in actionable_bottlenecks:
        lines.append(
            "| {name} | {avg_elapsed_ms} | {avg_share:.1%} | {run_count} |".format(
                name=item["name"],
                avg_elapsed_ms=item["avg_elapsed_ms"],
                avg_share=item["avg_share"],
                run_count=item["run_count"],
            )
        )

    # ---- Scenario Details 章节：每个场景的详细统计 ----
    lines.extend(["", "## Scenario Details", ""])
    for scenario_name, scenario in scenarios.items():
        lines.append(f"### {scenario_name}")
        lines.append("")
        lines.append(f"- Endpoint: `{scenario.get('endpoint', '')}`")
        lines.append(f"- Runs: {scenario.get('run_count', 0)}")
        lines.append(f"- Success Rate: {scenario.get('success_rate', 0.0):.1%}")
        total_stats = scenario.get("timing_total_ms")
        if total_stats:
            lines.append(
                "- Total Timing (ms): avg={avg}, p50={p50}, p95={p95}, max={max}".format(
                    avg=total_stats["avg"],
                    p50=total_stats["p50"],
                    p95=total_stats["p95"],
                    max=total_stats["max"],
                )
            )
        first_token_stats = scenario.get("first_token_ms")
        if first_token_stats:
            lines.append(
                "- First Token (ms): avg={avg}, p50={p50}, p95={p95}, max={max}".format(
                    avg=first_token_stats["avg"],
                    p50=first_token_stats["p50"],
                    p95=first_token_stats["p95"],
                    max=first_token_stats["max"],
                )
            )
        top_stages = scenario.get("top_stages") or []
        if top_stages:
            lines.append("- Top Stages:")
            for item in top_stages:
                lines.append(
                    "  - {name}: avg_elapsed={avg_elapsed_ms}ms, avg_share={avg_share:.1%}, runs={run_count}".format(
                        name=item["name"],
                        avg_elapsed_ms=item["avg_elapsed_ms"],
                        avg_share=item["avg_share"],
                        run_count=item["run_count"],
                    )
                )
        lines.append("")

    return "\n".join(lines).strip() + "\n"
