"""Utilities for collecting and summarizing timing-audit results."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any, Iterable


ACTIONABLE_STAGE_PREFIX_EXCLUDES = ("adapter_",)
ACTIONABLE_STAGE_EXACT_EXCLUDES = {
    "rag_chat_total",
    "rag_chat_stream_total",
    "text_to_image_total",
    "image_to_image_total",
    "knowledge_base_upload_total",
    "document_upload_total",
    "document_progress_total",
    "document_result_total",
    "process_image_upload",
    "process_image_uploads",
    "text_to_image_search_internal",
    "image_to_image_search_internal",
    "async_search_with_dict_output",
}


def extract_stream_timings(sse_payload: str) -> dict[str, Any] | None:
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


def _percentile(values: list[float], pct: float) -> float:
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


def summarize_audit_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    scenario_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stage_elapsed: dict[str, list[float]] = defaultdict(list)
    stage_share: dict[str, list[float]] = defaultdict(list)

    success_runs = 0
    timeout_runs = 0

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

    scenarios: dict[str, dict[str, Any]] = {}
    for scenario_name, group in scenario_groups.items():
        successful = [run for run in group if run.get("ok")]
        timing_successes = [run for run in successful if run.get("timings")]
        total_runs = len(group)
        success_count = len(successful)
        endpoint = next((str(run.get("endpoint")) for run in group if run.get("endpoint")), "")
        wall_stats = _build_stats(run.get("wall_ms", 0.0) for run in successful)
        total_stats = _build_stats(
            (run.get("timings") or {}).get("total_ms", 0.0)
            for run in timing_successes
        )
        first_token_stats = _build_stats(
            (run.get("timings") or {}).get("first_token_ms")
            for run in timing_successes
            if (run.get("timings") or {}).get("first_token_ms") is not None
        )

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
            "top_stages": top_stages[:5],
        }

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
    overall = summary.get("overall", {})
    scenarios = summary.get("scenarios", {})
    bottlenecks = summary.get("bottlenecks", [])
    actionable_bottlenecks = summary.get("actionable_bottlenecks", [])

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
