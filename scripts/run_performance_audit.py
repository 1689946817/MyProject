"""Run a live timing audit against the backend API."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.application.performance_audit import (  # noqa: E402
    extract_stream_timings,
    render_audit_markdown,
    summarize_audit_runs,
)


DEFAULT_SCENARIOS = {
    "scenarios": [
        {
            "name": "rag_table_non_stream",
            "kind": "rag_chat",
            "query": "告诉我华为NetEngine AR6000系列路由器的技术规格与功能特性对照表",
            "top_k": 5,
            "repeats": 2,
        },
        {
            "name": "rag_table_stream",
            "kind": "rag_chat_stream",
            "query": "告诉我华为NetEngine AR6000系列路由器的技术规格与功能特性对照表",
            "top_k": 5,
            "repeats": 2,
        },
        {
            "name": "text_search_specs",
            "kind": "text_to_image",
            "query": "华为 NetEngine AR6000 技术规格表",
            "top_k": 5,
            "repeats": 2,
        },
        {
            "name": "image_search_sample",
            "kind": "image_to_image",
            "file_path": "C:/path/to/sample-image.png",
            "top_k": 5,
            "repeats": 1,
        },
        {
            "name": "image_upload_sample",
            "kind": "image_upload",
            "file_path": "C:/path/to/sample-image.png",
            "split": "custom",
            "repeats": 1,
        },
        {
            "name": "document_upload_sample",
            "kind": "document_upload",
            "file_path": "C:/path/to/sample-document.pdf",
            "repeats": 1,
            "capture": {
                "latest_doc_id": "document.id",
            },
        },
        {
            "name": "document_progress_once",
            "kind": "document_progress",
            "refs": {
                "doc_id": "latest_doc_id",
            },
            "wait_seconds_before": 2.0,
            "repeats": 1,
        },
        {
            "name": "document_result_once",
            "kind": "document_result",
            "refs": {
                "doc_id": "latest_doc_id",
            },
            "wait_seconds_before": 2.0,
            "repeats": 1,
        },
    ]
}


def _load_scenarios(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        scenarios = payload.get("scenarios", [])
    elif isinstance(payload, list):
        scenarios = payload
    else:
        raise ValueError("Scenario file must be a JSON object or array")
    if not isinstance(scenarios, list):
        raise ValueError("'scenarios' must be a list")
    return [dict(item) for item in scenarios]


def _extract_path(payload: Any, dotted_path: str) -> Any:
    current = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _apply_refs(target: dict[str, Any], refs: dict[str, str], context: dict[str, Any]) -> None:
    for field_name, context_key in refs.items():
        if context_key not in context:
            raise KeyError(f"Missing context key '{context_key}' for field '{field_name}'")
        target[field_name] = context[context_key]


def _build_file_tuple(file_path: str) -> tuple[str, Any, str]:
    mime_type, _ = mimetypes.guess_type(file_path)
    filename = Path(file_path).name
    return filename, open(file_path, "rb"), mime_type or "application/octet-stream"


def _endpoint_for(kind: str, scenario: dict[str, Any], context: dict[str, Any]) -> str:
    if kind == "rag_chat":
        return "/api/rag/chat"
    if kind == "rag_chat_stream":
        return "/api/rag/chat/stream"
    if kind == "text_to_image":
        return "/api/search/text-to-image"
    if kind == "image_to_image":
        return "/api/search/image-to-image"
    if kind == "image_upload":
        return "/api/knowledge-base/upload"
    if kind == "document_upload":
        return "/api/docs/upload"
    if kind == "document_progress":
        doc_id = scenario.get("doc_id") or context.get((scenario.get("refs") or {}).get("doc_id", ""))
        return f"/api/docs/{doc_id}/progress"
    if kind == "document_result":
        doc_id = scenario.get("doc_id") or context.get((scenario.get("refs") or {}).get("doc_id", ""))
        return f"/api/docs/{doc_id}/result"
    raise ValueError(f"Unsupported scenario kind: {kind}")


def _run_one(
    client: httpx.Client,
    base_url: str,
    scenario: dict[str, Any],
    context: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    kind = str(scenario["kind"])
    endpoint = _endpoint_for(kind, scenario, context)
    wait_seconds_before = float(scenario.get("wait_seconds_before", 0.0) or 0.0)
    if wait_seconds_before > 0:
        time.sleep(wait_seconds_before)

    started_at = time.perf_counter()
    response_payload: dict[str, Any] | None = None
    timings: dict[str, Any] | None = None
    error: str | None = None
    status_code: int | None = None

    try:
        if kind == "rag_chat":
            data = {"query": scenario["query"], "top_k": str(scenario.get("top_k", 5))}
            refs = scenario.get("refs") or {}
            _apply_refs(data, refs, context)
            files = None
            file_handle = None
            try:
                if scenario.get("file_path"):
                    file_handle = _build_file_tuple(str(scenario["file_path"]))
                    files = {"image": file_handle}
                response = client.post(f"{base_url}{endpoint}", data=data, files=files, timeout=timeout)
                status_code = response.status_code
                response_payload = response.json()
                timings = response_payload.get("timings")
                response.raise_for_status()
            finally:
                if file_handle is not None:
                    file_handle[1].close()
        elif kind == "rag_chat_stream":
            data = {"query": scenario["query"], "top_k": str(scenario.get("top_k", 5))}
            refs = scenario.get("refs") or {}
            _apply_refs(data, refs, context)
            files = None
            file_handle = None
            raw_sse = ""
            try:
                if scenario.get("file_path"):
                    file_handle = _build_file_tuple(str(scenario["file_path"]))
                    files = {"image": file_handle}
                with client.stream("POST", f"{base_url}{endpoint}", data=data, files=files, timeout=timeout) as response:
                    status_code = response.status_code
                    for chunk in response.iter_text():
                        raw_sse += chunk
                    response.raise_for_status()
                timings = extract_stream_timings(raw_sse)
                response_payload = {"sse_length": len(raw_sse)}
            finally:
                if file_handle is not None:
                    file_handle[1].close()
        elif kind == "text_to_image":
            body = {"query": scenario["query"], "top_k": int(scenario.get("top_k", 5))}
            response = client.post(f"{base_url}{endpoint}", json=body, timeout=timeout)
            status_code = response.status_code
            response_payload = response.json()
            timings = response_payload.get("timings")
            response.raise_for_status()
        elif kind == "image_to_image":
            file_handle = _build_file_tuple(str(scenario["file_path"]))
            try:
                response = client.post(
                    f"{base_url}{endpoint}",
                    params={"top_k": int(scenario.get("top_k", 5))},
                    files={"file": file_handle},
                    timeout=timeout,
                )
                status_code = response.status_code
                response_payload = response.json()
                timings = response_payload.get("timings")
                response.raise_for_status()
            finally:
                file_handle[1].close()
        elif kind == "image_upload":
            file_handle = _build_file_tuple(str(scenario["file_path"]))
            try:
                response = client.post(
                    f"{base_url}{endpoint}",
                    params={"split": scenario.get("split", "custom")},
                    files=[("files", file_handle)],
                    timeout=timeout,
                )
                status_code = response.status_code
                response_payload = response.json()
                timings = response_payload.get("timings")
                response.raise_for_status()
            finally:
                file_handle[1].close()
        elif kind == "document_upload":
            file_handle = _build_file_tuple(str(scenario["file_path"]))
            try:
                response = client.post(
                    f"{base_url}{endpoint}",
                    files={"file": file_handle},
                    timeout=timeout,
                )
                status_code = response.status_code
                response_payload = response.json()
                timings = response_payload.get("timings")
                response.raise_for_status()
            finally:
                file_handle[1].close()
        elif kind in {"document_progress", "document_result"}:
            response = client.get(f"{base_url}{endpoint}", timeout=timeout)
            status_code = response.status_code
            response_payload = response.json()
            timings = response_payload.get("timings")
            response.raise_for_status()
        else:
            raise ValueError(f"Unsupported scenario kind: {kind}")
    except Exception as exc:
        error = str(exc)

    wall_ms = round((time.perf_counter() - started_at) * 1000, 3)
    ok = error is None and status_code is not None and 200 <= status_code < 300

    if ok and response_payload and scenario.get("capture"):
        for context_key, payload_path in dict(scenario["capture"]).items():
            value = _extract_path(response_payload, str(payload_path))
            if value is not None:
                context[context_key] = value

    return {
        "scenario_name": scenario["name"],
        "kind": kind,
        "endpoint": endpoint,
        "ok": ok,
        "http_status": status_code,
        "wall_ms": wall_ms,
        "timings": timings,
        "error": error,
        "response_excerpt": response_payload,
    }


def run_audit(
    *,
    base_url: str,
    scenarios: list[dict[str, Any]],
    timeout: float,
) -> dict[str, Any]:
    context: dict[str, Any] = {}
    runs: list[dict[str, Any]] = []

    with httpx.Client(follow_redirects=True) as client:
        for scenario in scenarios:
            repeats = int(scenario.get("repeats", 1))
            for _ in range(repeats):
                runs.append(
                    _run_one(
                        client=client,
                        base_url=base_url.rstrip("/"),
                        scenario=scenario,
                        context=context,
                        timeout=timeout,
                    )
                )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url.rstrip("/"),
        "context": context,
        "runs": runs,
        "summary": summarize_audit_runs(runs),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a live backend performance audit.")
    parser.add_argument("--base-url", default="http://127.0.0.1:9090")
    parser.add_argument("--scenario-file", type=Path, help="Path to the JSON scenario file.")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "artifacts" / "performance_audit")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--emit-template", type=Path, help="Write a template scenario file and exit.")
    args = parser.parse_args()

    if args.emit_template:
        args.emit_template.write_text(json.dumps(DEFAULT_SCENARIOS, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Template written to {args.emit_template}")
        return

    if not args.scenario_file:
        raise SystemExit("--scenario-file is required unless --emit-template is used")

    scenarios = _load_scenarios(args.scenario_file)
    audit_result = run_audit(
        base_url=args.base_url,
        scenarios=scenarios,
        timeout=args.timeout,
    )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_path = output_dir / "audit_raw.json"
    summary_path = output_dir / "audit_summary.json"
    report_path = output_dir / "audit_report.md"

    raw_path.write_text(json.dumps(audit_result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(audit_result["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_audit_markdown(audit_result["summary"]), encoding="utf-8")

    print(f"Raw data: {raw_path}")
    print(f"Summary: {summary_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
