from __future__ import annotations
import argparse, base64, hashlib, io, json, os, sys, time, threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_env_path = Path(__file__).parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from evaluation.datasets.unidoc_subset import DOMAINS, UniDocQuerySample, load_unidoc_domain  # noqa
from evaluation.methods import unidoc_clip, unidoc_ocr, unidoc_proposed  # noqa

CROSSDOMAIN_KEY = "crossdomain"
BATCH_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
API_KEY = os.environ.get("MLLM_API_KEY", "sk-1fce3abb190e45a29a15aadb4a67390e")
MODEL = os.environ.get("MLLM_MODEL_NAME", "qwen3.5-plus")

_PROMPT = (
    "你是一个多模态知识库问答助手。你将看到若干张检索到的相关图像，"
    "以及用户提出的问题。请仔细观察这些图像的内容，基于图像中的视觉信息回答用户的问题。\n\n"
    "用户问题：{query}\n\n"
    "请基于图像内容进行回答。如果图像信息不足以回答某些部分，请明确说明不确定。"
)

MAX_LONG_SIDE = 1600
JPEG_QUALITY = 85
MAX_LONG_SIDE_FALLBACK = 1024
JPEG_QUALITY_FALLBACK = 75
MAX_LINE_BYTES = 6 * 1024 * 1024   # 单行 6MB 硬限
MAX_BATCH_BYTES = 480 * 1024 * 1024  # 单批次 480MB


def _utf8_stdio():
    for s in ("stdout", "stderr"):
        obj = getattr(sys, s, None)
        fn = getattr(obj, "reconfigure", None)
        if callable(fn):
            fn(encoding="utf-8", errors="replace")


_utf8_stdio()


def _img_to_b64(path: str, fallback: bool = False) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    long_side = MAX_LONG_SIDE_FALLBACK if fallback else MAX_LONG_SIDE
    quality = JPEG_QUALITY_FALLBACK if fallback else JPEG_QUALITY
    try:
        from PIL import Image
        with Image.open(path) as img:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            w, h = img.size
            ls = max(w, h)
            if ls > long_side:
                sc = long_side / ls
                img = img.resize((int(w * sc), int(h * sc)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"  [WARN] compress failed {path}: {e}")
        try:
            return base64.b64encode(open(path, "rb").read()).decode()
        except Exception:
            return None


def _ids_to_paths(ids: List[str]) -> List[str]:
    import chromadb
    from chromadb.config import Settings as CS
    from app.core.config import settings as cfg
    client = chromadb.Client(CS(is_persistent=True, persist_directory=cfg.CHROMA_PERSIST_DIR))
    id2p: Dict[str, str] = {}
    for col in [
        f"unidoc_{CROSSDOMAIN_KEY}_proposed",
        f"unidoc_{CROSSDOMAIN_KEY}_clip",
        f"unidoc_{CROSSDOMAIN_KEY}_ocr",
    ]:
        if len(id2p) == len(ids):
            break
        try:
            c = client.get_collection(col)
            rem = [i for i in ids if i not in id2p]
            r = c.get(ids=rem, include=["metadatas"])
            for img_id, meta in zip(r["ids"], r["metadatas"]):
                if img_id not in id2p and meta and meta.get("file_path"):
                    id2p[img_id] = meta["file_path"]
        except Exception:
            continue
    root = Path(__file__).parent.parent / "data" / "UniDoc-Bench-subset"
    for img_id in ids:
        if img_id not in id2p and (root / img_id).exists():
            id2p[img_id] = str(root / img_id)
    return [id2p.get(i, "") for i in ids]


def _ids_to_ocr_texts(ids: List[str]) -> List[str]:
    import chromadb
    from chromadb.config import Settings as CS
    from app.core.config import settings as cfg
    client = chromadb.Client(CS(is_persistent=True, persist_directory=cfg.CHROMA_PERSIST_DIR))
    id2t: Dict[str, str] = {}
    col_name = f"unidoc_{CROSSDOMAIN_KEY}_ocr"
    try:
        c = client.get_collection(col_name)
        r = c.get(ids=ids, include=["metadatas"])
        for img_id, meta in zip(r["ids"], r["metadatas"]):
            if meta and meta.get("ocr_text"):
                id2t[img_id] = meta["ocr_text"]
    except Exception:
        pass
    return [id2t.get(i, "") for i in ids]


def _build_body(query: str, b64s: List[str]) -> Dict[str, Any]:
    content: List[Dict[str, Any]] = [{"type": "text", "text": _PROMPT.format(query=query)}]
    for idx, b64 in enumerate(b64s, 1):
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        content.append({"type": "text", "text": f"\n[图像 {idx}]"})
    return {"model": MODEL, "messages": [{"role": "user", "content": content}], "extra_body": {"enable_thinking": False}}


def _make_line(s: UniDocQuerySample, method: str, top_k: int) -> tuple[str, str]:
    """返回 (input_jsonl_line, meta_jsonl_line)，图片超6MB时自动降级压缩。"""
    qid = hashlib.md5(f"{s.query}||{s.domain}".encode()).hexdigest()[:16]
    rids: List[str] = []
    if method == "no_rag":
        body: Dict[str, Any] = {
            "model": MODEL,
            "messages": [{"role": "user", "content": f"请回答问题：{s.query}"}],
            "extra_body": {"enable_thinking": False},
        }
    else:
        if method == "proposed":
            ids = unidoc_proposed.retrieve(s.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
        elif method == "baseline_clip":
            ids = unidoc_clip.retrieve(s.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
        elif method == "baseline_ocr":
            ids = unidoc_ocr.retrieve(s.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
            rids = ids
            ocr_texts = _ids_to_ocr_texts(ids)
            combined = "\n\n".join(f"[片段{i+1}] {t}" for i, t in enumerate(ocr_texts) if t)
            if combined:
                ocr_prompt = (
                    f"你是一个知识库问答助手。以下是从知识库中检索到的相关文字内容：\n\n"
                    f"{combined}\n\n用户问题：{s.query}\n\n请基于上述内容回答问题。"
                )
            else:
                ocr_prompt = f"未找到相关文字内容。问题：{s.query}"
            body = {
                "model": MODEL,
                "messages": [{"role": "user", "content": ocr_prompt}],
                "extra_body": {"enable_thinking": False},
            }
        else:
            raise ValueError(f"Unknown method: {method}")
        if method in ("proposed", "baseline_clip"):
            rids = ids
            paths = _ids_to_paths(ids)
            b64s = [b for p in paths if (b := _img_to_b64(p, fallback=False))]
            if not b64s:
                body = {
                    "model": MODEL,
                    "messages": [{"role": "user", "content": f"未找到相关图像。问题：{s.query}"}],
                    "extra_body": {"enable_thinking": False},
                }
            else:
                body = _build_body(s.query, b64s)
    iline = json.dumps(
        {"custom_id": qid, "method": "POST", "url": "/v1/chat/completions", "body": body},
        ensure_ascii=False)
    # 单行超 6MB 时降级压缩（仅图像方法）
    if len(iline.encode()) > MAX_LINE_BYTES and method in ("proposed", "baseline_clip"):
        paths = _ids_to_paths(rids)
        b64s = [b for p in paths if (b := _img_to_b64(p, fallback=True))]
        body = _build_body(s.query, b64s) if b64s else body
        iline = json.dumps(
            {"custom_id": qid, "method": "POST", "url": "/v1/chat/completions", "body": body},
            ensure_ascii=False)
        print(f"  [FALLBACK] qid={qid} 降级到 {MAX_LONG_SIDE_FALLBACK}px")
    mline = json.dumps(
        {"query_id": qid, "query": s.query, "domain": s.domain,
         "question_type": s.question_type, "answer_type": s.answer_type,
         "reference_answer": s.answer, "retrieved_ids": rids, "method": method},
        ensure_ascii=False)
    return iline, mline


def phase1(samples: List[UniDocQuerySample], method: str, top_k: int, work_dir: Path) -> List[Path]:
    """构造 JSONL，按 480MB/批切分，返回所有 input_*.jsonl 路径列表。"""
    existing = sorted(work_dir.glob("input_*.jsonl"))
    meta = work_dir / "input_meta.jsonl"
    if existing and meta.exists():
        print(f"[Phase1] 已存在 {len(existing)} 个批次文件，跳过")
        return existing
    print(f"[Phase1] 构造 {len(samples)} 条请求（max_long_side={MAX_LONG_SIDE}px, q={JPEG_QUALITY}）...")
    work_dir.mkdir(parents=True, exist_ok=True)
    mlines: List[str] = []
    batches: List[List[str]] = [[]]
    batch_bytes = [0]
    empty = 0
    for i, s in enumerate(samples, 1):
        iline, mline = _make_line(s, method, top_k)
        lb = len(iline.encode()) + 1  # +1 换行符
        if lb > MAX_LINE_BYTES:
            print(f"  [SKIP] qid 行仍超6MB，跳过")
            empty += 1
            continue
        if batch_bytes[-1] + lb > MAX_BATCH_BYTES:
            batches.append([])
            batch_bytes.append(0)
        batches[-1].append(iline)
        batch_bytes[-1] += lb
        mlines.append(mline)
        if i % 50 == 0:
            total_mb = sum(batch_bytes) / 1024 / 1024
            print(f"  [{i}/{len(samples)}] 已处理，当前累计 {total_mb:.1f}MB，批次数={len(batches)}")
    inp_paths: List[Path] = []
    for bi, blines in enumerate(batches):
        bp = work_dir / f"input_{bi:03d}.jsonl"
        bp.write_text("\n".join(blines), encoding="utf-8")
        mb = bp.stat().st_size / 1024 / 1024
        print(f"[Phase1] 批次{bi}: {len(blines)}条 {mb:.1f}MB -> {bp.name}")
        inp_paths.append(bp)
    meta.write_text("\n".join(mlines), encoding="utf-8")
    total_mb = sum(batch_bytes) / 1024 / 1024
    print(f"[Phase1] 完成 {len(batches)} 批次，总 {total_mb:.1f}MB，空图/跳过={empty}")
    return inp_paths


def phase2(work_dir: Path, inp_paths: List[Path]) -> List[Path]:
    """并行提交所有批次，返回所有 result_*.jsonl 路径。"""
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY, base_url=BATCH_BASE_URL)
    result_paths: List[Path] = []
    lock = threading.Lock()
    errors: List[Exception] = []

    def _worker(inp: Path, idx: int):
        try:
            res = work_dir / f"result_{idx:03d}.jsonl"
            bid_f = work_dir / f"batch_id_{idx:03d}.txt"
            tag = f"[Phase2-{idx:03d}]"
            if res.exists():
                print(f"{tag} 已存在，跳过")
                with lock:
                    result_paths.append(res)
                return
            if bid_f.exists():
                bid = bid_f.read_text(encoding="utf-8").strip()
                print(f"{tag} 断点续传 batch_id={bid}")
            else:
                print(f"{tag} 上传 {inp.name} ...")
                with open(inp, "rb") as f:
                    up = client.files.create(file=f, purpose="batch")
                fid = up.id
                print(f"{tag} file_id={fid}")
                batch = client.batches.create(
                    input_file_id=fid,
                    endpoint="/v1/chat/completions",
                    completion_window="24h",
                )
                bid = batch.id
                bid_f.write_text(bid, encoding="utf-8")
                print(f"{tag} batch_id={bid}")
            print(f"{tag} 轮询中（每30s）...")
            while True:
                batch = client.batches.retrieve(bid)
                st = batch.status
                c = batch.request_counts
                print(f"{tag} {st}  total={c.total} done={c.completed} fail={c.failed}")
                if st == "completed":
                    break
                if st in ("failed", "expired", "cancelled"):
                    raise RuntimeError(f"{tag} Batch失败 status={st}")
                time.sleep(30)
            ofid = batch.output_file_id
            if not ofid:
                raise RuntimeError(f"{tag} output_file_id 为空")
            print(f"{tag} 下载 output_file_id={ofid}")
            res.write_bytes(client.files.content(ofid).read())
            print(f"{tag} 已保存 {res}")
            with lock:
                result_paths.append(res)
        except Exception as e:
            with lock:
                errors.append(e)
            print(f"[ERROR] 批次{idx} 失败: {e}")

    threads = [threading.Thread(target=_worker, args=(inp, i), daemon=True)
               for i, inp in enumerate(inp_paths)]
    print(f"[Phase2] 并行提交 {len(threads)} 个批次...")
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise RuntimeError(f"[Phase2] {len(errors)} 个批次失败: {errors[0]}")
    return sorted(result_paths)


def phase3(work_dir: Path, result_paths: List[Path], out: Path) -> None:
    """合并所有 result_*.jsonl，解析成最终 JSON 输出。"""
    meta_f = work_dir / "input_meta.jsonl"
    print("[Phase3] 解析结果...")
    meta_map: Dict[str, Dict[str, Any]] = {}
    for line in meta_f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            o = json.loads(line)
            meta_map[o["query_id"]] = o
    records = []
    errs = 0
    for rp in sorted(result_paths):
        for line in rp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            qid = o.get("custom_id", "")
            m = meta_map.get(qid, {})
            resp = o.get("response", {})
            if resp and resp.get("status_code") == 200:
                choices = resp.get("body", {}).get("choices", [])
                if choices:
                    msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                    if isinstance(msg, dict):
                        ans = msg.get("content")
                        if ans is None:
                            reasoning = msg.get("reasoning_content", "")
                            ans = f"[ERROR] reasoning_only: {reasoning[:200]}" if reasoning else "[ERROR] empty"
                            errs += 1
                    else:
                        ans = "[ERROR] empty"
                        errs += 1
                else:
                    ans = "[ERROR] empty"
                    errs += 1
            else:
                ans = f"[ERROR] {o.get('error') or resp}"
                errs += 1
            records.append({
                "query_id": qid,
                "query": m.get("query", ""),
                "domain": m.get("domain", ""),
                "question_type": m.get("question_type", ""),
                "answer_type": m.get("answer_type", ""),
                "reference_answer": m.get("reference_answer", ""),
                "generated_answer": ans,
                "retrieved_ids": m.get("retrieved_ids", []),
                "method": m.get("method", ""),
            })
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Phase3] {len(records)}条（来自{len(result_paths)}批次）-> {out}（错误={errs}）")


def main():
    parser = argparse.ArgumentParser(description="批量推理生成器 - UniDoc-Bench-subset")
    parser.add_argument("--method", required=True,
                        choices=["proposed", "baseline_clip", "baseline_ocr", "no_rag"])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", default="data/rag_outputs/unidoc_gen_batch")
    parser.add_argument("--subset-root", default="data/UniDoc-Bench-subset")
    parser.add_argument("--domains", nargs="+", default=None)
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], default=None,
                        help="只执行某一阶段（默认全部执行）")
    args = parser.parse_args()

    subset_root = Path(args.subset_root)
    domains = args.domains or DOMAINS
    out_dir = Path(args.output_dir)
    work_dir = out_dir / "_batch_workdir" / args.method
    out_path = out_dir / f"{args.method}_results.json"

    samples: List[UniDocQuerySample] = []
    for d in domains:
        try:
            ds = load_unidoc_domain(d, subset_root)
            samples.extend(ds)
            print(f"Loaded {len(ds)} from {d}")
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")
    if not samples:
        print("没有加载到任何样本，请检查 --subset-root")
        return
    if args.method == "baseline_ocr" and not unidoc_ocr.check_index(CROSSDOMAIN_KEY):
        print(
            "[ERROR] OCR index for crossdomain is missing or unhealthy. "
            "请先执行 `python -m evaluation.run_unidoc_full_eval --method baseline_ocr --build-index` 重建索引。"
        )
        return
    print(f"共 {len(samples)} 条，method={args.method}, top_k={args.top_k}")

    run_all = args.phase is None
    inp_paths: List[Path] = []
    if run_all or args.phase == 1:
        inp_paths = phase1(samples, args.method, args.top_k, work_dir)
    if run_all or args.phase == 2:
        if not inp_paths:
            inp_paths = sorted(work_dir.glob("input_*.jsonl"))
        if not inp_paths:
            print("[ERROR] 未找到 input_*.jsonl，请先执行 Phase1")
            return
        result_paths = phase2(work_dir, inp_paths)
    if run_all or args.phase == 3:
        result_paths = sorted(work_dir.glob("result_*.jsonl"))
        if not result_paths:
            print("[ERROR] 未找到 result_*.jsonl，请先执行 Phase2")
            return
        phase3(work_dir, result_paths, out_path)
    print("全部完成。")


if __name__ == "__main__":
    main()
