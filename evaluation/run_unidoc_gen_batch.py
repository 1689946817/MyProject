"""
生成器评估 — UniDoc-Bench-subset 数据集（阿里百炼 Batch API 批量推理版）。

================================================================================
脚本用途
================================================================================
本脚本使用阿里百炼（DashScope）的 Batch API 进行批量推理，适合大规模评测场景。
相比 run_unidoc_gen.py 的逐条实时调用，Batch API 提供更高的吞吐量和更低的成本。

================================================================================
三阶段流水线架构
================================================================================
整个流程分为三个阶段，可独立执行（通过 --phase 参数控制）：

  Phase 1 — 构造 JSONL 请求文件
    - 为每条查询样本构造 OpenAI Chat Completions 格式的请求体
    - 将图片编码为 base64 并嵌入请求体中
    - 按 480MB/批次切分为多个 input_*.jsonl 文件
    - 同时生成 input_meta.jsonl 记录每条请求的元数据（query, domain, reference_answer 等）
    - 单行请求体超过 6MB 时自动降级图片质量（1024px / JPEG quality=75）

  Phase 2 — 提交 Batch 任务并轮询结果
    - 将每个 input_*.jsonl 上传到百炼平台，创建 Batch 任务
    - 每 30 秒轮询 Batch 状态，直到 completed/failed/expired
    - 支持断点续传：batch_id 保存到 batch_id_*.txt，重启后自动恢复
    - 使用多线程并行提交多个批次

  Phase 3 — 解析并合并结果
    - 读取所有 result_*.jsonl 响应文件
    - 按 custom_id 关联 input_meta.jsonl 中的元数据
    - 处理异常情况：content 为 null 但有 reasoning_content 时标记为错误
    - 输出最终的 JSON 评测文件

================================================================================
支持的检索方法
================================================================================
  proposed        本系统方法：MLLM 语义描述 → 文本 Embedding 检索 → 传图片给 MLLM
  baseline_clip   基线方法：qwen3-vl-embedding 多模态检索 → 传图片给 MLLM
  baseline_ocr    基线方法：OCR 文字检索 → 传纯文本给 LLM（不传图片）
  no_rag          对照组：不检索，直接问 LLM

================================================================================
query_id 生成规则
================================================================================
所有脚本统一使用 md5("query||domain")[:16] 作为 query_id / custom_id，
确保 run_unidoc_gen.py、run_unidoc_gen_batch.py、run_unidoc_score.py 之间的结果可关联。

================================================================================
关键限制
================================================================================
  - 单行请求体（JSONL 中的一行）最大 6MB（阿里百炼限制）
  - 单个 JSONL 文件最大 480MB（阿里百炼限制）
  - 超限时脚本自动降级图片压缩或分批处理

================================================================================
使用示例（从项目根目录）
================================================================================
  # 完整执行全部三个阶段
  python -m evaluation.run_unidoc_gen_batch \\
    --method proposed \\
    --top-k 5 \\
    --output-dir data/rag_outputs/unidoc_gen_batch

  # 仅执行 Phase 1（构造请求文件）
  python -m evaluation.run_unidoc_gen_batch --method proposed --phase 1

  # 仅执行 Phase 2（提交并等待结果）
  python -m evaluation.run_unidoc_gen_batch --method proposed --phase 2

  # 仅执行 Phase 3（解析已有结果）
  python -m evaluation.run_unidoc_gen_batch --method proposed --phase 3
"""
from __future__ import annotations
import argparse, base64, hashlib, io, json, os, sys, time, threading  # noqa: E402
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# 环境变量加载
# ============================================================================
# 脚本独立运行，需手动加载 backend/.env 中的模型配置
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# ============================================================================
# 核心依赖导入
# ============================================================================
from evaluation.datasets.unidoc_subset import DOMAINS, UniDocQuerySample, load_unidoc_domain  # noqa
from evaluation.methods import unidoc_clip, unidoc_ocr, unidoc_proposed  # noqa

# ============================================================================
# 全局常量
# ============================================================================
CROSSDOMAIN_KEY = "crossdomain"                                        # 跨领域候选池标识
BATCH_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 百炼 Batch API 兼容 OpenAI 的端点
API_KEY = os.environ.get("MLLM_API_KEY", "sk-1fce3abb190e45a29a15aadb4a67390e")  # API 密钥（优先从环境变量读取）
MODEL = os.environ.get("MLLM_MODEL_NAME", "qwen3.5-plus")            # 模型名称

# 多模态问答 Prompt 模板（用于 proposed / baseline_clip 方法）
_PROMPT = (
    "你是一个多模态知识库问答助手。你将看到若干张检索到的相关图像，"
    "以及用户提出的问题。请仔细观察这些图像的内容，基于图像中的视觉信息回答用户的问题。\n\n"
    "用户问题：{query}\n\n"
    "请基于图像内容进行回答。如果图像信息不足以回答某些部分，请明确说明不确定。"
)

# ============================================================================
# 图片压缩参数（两档压缩策略）
# ============================================================================
# 正常压缩档位
MAX_LONG_SIDE = 1600                # 图片长边最大像素数
JPEG_QUALITY = 85                   # JPEG 压缩质量（0-100）
# 降级压缩档位（单行超 6MB 时使用）
MAX_LONG_SIDE_FALLBACK = 1024       # 降级后的长边像素数
JPEG_QUALITY_FALLBACK = 75          # 降级后的 JPEG 质量

# ============================================================================
# Batch API 文件大小限制
# ============================================================================
MAX_LINE_BYTES = 6 * 1024 * 1024    # 单行请求体 6MB 硬限（百炼限制）
MAX_BATCH_BYTES = 480 * 1024 * 1024 # 单个 JSONL 文件 480MB（百炼限制）


def _utf8_stdio():
    """将 stdout/stderr 重新配置为 UTF-8 编码，避免 Windows 下中文乱码。"""
    for s in ("stdout", "stderr"):
        obj = getattr(sys, s, None)
        fn = getattr(obj, "reconfigure", None)
        if callable(fn):
            fn(encoding="utf-8", errors="replace")


_utf8_stdio()


def _img_to_b64(path: str, fallback: bool = False) -> Optional[str]:
    """
    将图片文件读取、压缩并编码为 base64 字符串。

    两档压缩策略：
      - 正常模式（fallback=False）：1600px 长边，JPEG quality=85
      - 降级模式（fallback=True）：1024px 长边，JPEG quality=75（单行超 6MB 时使用）

    Args:
        path: 图片文件路径
        fallback: 是否使用降级压缩

    Returns:
        base64 编码的图片字符串，失败返回 None
    """
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
    """
    将检索返回的图片 ID 列表解析为本地文件路径。

    查询策略：
      1. 从 ChromaDB 的 crossdomain proposed/clip/ocr 集合查询 metadata.file_path
      2. 回退到 data/UniDoc-Bench-subset/ 目录直接按文件名查找

    Args:
        ids: 图片 ID 列表

    Returns:
        文件路径列表（与 ids 同序），未找到的返回空字符串
    """
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
    """
    从 ChromaDB 的 OCR 集合中查询每张图片的 OCR 文字。

    仅用于 baseline_ocr 方法：将 OCR 片段拼接后作为纯文本输入给 LLM，
    不传图片。

    Args:
        ids: 图片 ID 列表

    Returns:
        OCR 文字列表（与 ids 同序），未找到的返回空字符串
    """
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
    """
    构造多模态 Chat Completions 请求体（OpenAI 格式）。

    消息内容由文本 Prompt + 多张 base64 图片交替组成，每张图片前标注 [图像 N]。

    Args:
        query: 用户问题
        b64s: base64 编码的图片列表

    Returns:
        符合 OpenAI Chat Completions API 格式的请求体字典
    """
    # 消息内容列表：先放系统 Prompt，后面交替放图片和标注文字
    content: List[Dict[str, Any]] = [{"type": "text", "text": _PROMPT.format(query=query)}]
    for idx, b64 in enumerate(b64s, 1):
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        content.append({"type": "text", "text": f"\n[图像 {idx}]"})
    return {"model": MODEL, "messages": [{"role": "user", "content": content}], "extra_body": {"enable_thinking": False}}


# ============================================================================
# Phase 1 辅助函数：构造单条 JSONL 请求
# ============================================================================
def _make_line(s: UniDocQuerySample, method: str, top_k: int) -> tuple[str, str]:
    """
    为单条查询样本构造 JSONL 的一行请求和一行元数据。

    Args:
        s: UniDoc 查询样本
        method: 检索方法名
        top_k: 检索图片数量

    Returns:
        (input_line, meta_line) 二元组：
          - input_line: Batch API 请求行（含 custom_id, method, url, body）
          - meta_line: 元数据行（含 query, domain, reference_answer 等，用于 Phase 3 关联）

    注意：
      - query_id 使用 md5("query||domain")[:16] 生成，确保跨脚本一致
      - baseline_ocr 方法只传纯文本（OCR 片段），不传图片
      - proposed / baseline_clip 方法传 base64 图片
      - 单行超 6MB 时自动降级图片压缩
    """
    # query_id 生成规则：md5("query||domain") 取前 16 位
    # 与 run_unidoc_gen.py / run_unidoc_score.py 保持一致
    qid = hashlib.md5(f"{s.query}||{s.domain}".encode()).hexdigest()[:16]
    rids: List[str] = []  # 检索到的图片 ID 列表（用于元数据记录）
    if method == "no_rag":
        # no_rag：不检索，直接问 LLM
        body: Dict[str, Any] = {
            "model": MODEL,
            "messages": [{"role": "user", "content": f"请回答问题：{s.query}"}],
            "extra_body": {"enable_thinking": False},
        }
    else:
        # ---- 检索方法分支 ----
        if method == "proposed":
            ids = unidoc_proposed.retrieve(s.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
        elif method == "baseline_clip":
            ids = unidoc_clip.retrieve(s.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
        elif method == "baseline_ocr":
            # baseline_ocr 特殊处理：传纯文本（OCR 片段），不传图片
            ids = unidoc_ocr.retrieve(s.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
            rids = ids
            # 从 ChromaDB 查询检索到的图片对应的 OCR 文字
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
            # proposed / baseline_clip：传 base64 图片给 MLLM
            rids = ids
            paths = _ids_to_paths(ids)
            # 正常压缩（1600px / quality=85）
            b64s = [b for p in paths if (b := _img_to_b64(p, fallback=False))]
            if not b64s:
                body = {
                    "model": MODEL,
                    "messages": [{"role": "user", "content": f"未找到相关图像。问题：{s.query}"}],
                    "extra_body": {"enable_thinking": False},
                }
            else:
                body = _build_body(s.query, b64s)
    # 构造 Batch API 请求行（OpenAI 兼容格式）
    iline = json.dumps(
        {"custom_id": qid, "method": "POST", "url": "/v1/chat/completions", "body": body},
        ensure_ascii=False)
    # ---- 大小检查与降级压缩 ----
    # 单行超过 6MB 时，仅对图像方法降级到 1024px / quality=75
    if len(iline.encode()) > MAX_LINE_BYTES and method in ("proposed", "baseline_clip"):
        paths = _ids_to_paths(rids)
        b64s = [b for p in paths if (b := _img_to_b64(p, fallback=True))]
        body = _build_body(s.query, b64s) if b64s else body
        iline = json.dumps(
            {"custom_id": qid, "method": "POST", "url": "/v1/chat/completions", "body": body},
            ensure_ascii=False)
        print(f"  [FALLBACK] qid={qid} 降级到 {MAX_LONG_SIDE_FALLBACK}px")
    # 构造元数据行（不含请求体，仅记录 query/reference_answer 等，用于 Phase 3 关联）
    mline = json.dumps(
        {"query_id": qid, "query": s.query, "domain": s.domain,
         "question_type": s.question_type, "answer_type": s.answer_type,
         "reference_answer": s.answer, "retrieved_ids": rids, "method": method},
        ensure_ascii=False)
    return iline, mline


# ============================================================================
# Phase 1：构造 JSONL 请求文件
# ============================================================================
def phase1(samples: List[UniDocQuerySample], method: str, top_k: int, work_dir: Path) -> List[Path]:
    """
    Phase 1：为所有查询样本构造 Batch API 请求的 JSONL 文件。

    处理流程：
      1. 遍历所有样本，调用 _make_line() 构造每行请求
      2. 按 MAX_BATCH_BYTES（480MB）限制自动切分为多个批次文件
      3. 超过单行 6MB 限制的样本直接跳过
      4. 生成 input_000.jsonl, input_001.jsonl, ... 批次文件
      5. 生成 input_meta.jsonl 记录所有样本的元数据（用于 Phase 3 关联结果）

    断点续传：如果 input_*.jsonl 和 input_meta.jsonl 已存在，直接跳过。

    Args:
        samples: 查询样本列表
        method: 检索方法名
        top_k: 检索图片数量
        work_dir: 工作目录（存放中间文件）

    Returns:
        所有 input_*.jsonl 文件路径列表
    """
    # 断点续传：检查是否已构造过
    existing = sorted(work_dir.glob("input_*.jsonl"))
    existing = sorted(work_dir.glob("input_*.jsonl"))
    meta = work_dir / "input_meta.jsonl"
    if existing and meta.exists():
        print(f"[Phase1] 已存在 {len(existing)} 个批次文件，跳过")
        return existing
    print(f"[Phase1] 构造 {len(samples)} 条请求（max_long_side={MAX_LONG_SIDE}px, q={JPEG_QUALITY}）...")
    work_dir.mkdir(parents=True, exist_ok=True)
    mlines: List[str] = []          # 所有元数据行（Phase 3 用）
    batches: List[List[str]] = [[]]  # 批次列表，每批次是一个字符串列表
    batch_bytes = [0]                # 每个批次的累计字节数
    empty = 0                        # 因超限被跳过的样本数
    for i, s in enumerate(samples, 1):
        iline, mline = _make_line(s, method, top_k)
        lb = len(iline.encode()) + 1  # +1 换行符的字节数
        # 单行仍超 6MB（降级压缩后），跳过该样本
        if lb > MAX_LINE_BYTES:
            print(f"  [SKIP] qid 行仍超6MB，跳过")
            empty += 1
            continue
        # 当前批次加上此行后超过 480MB，开启新批次
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
        # 写入 input_000.jsonl, input_001.jsonl, ...
        bp = work_dir / f"input_{bi:03d}.jsonl"
        bp.write_text("\n".join(blines), encoding="utf-8")
        mb = bp.stat().st_size / 1024 / 1024
        print(f"[Phase1] 批次{bi}: {len(blines)}条 {mb:.1f}MB -> {bp.name}")
        inp_paths.append(bp)
    meta.write_text("\n".join(mlines), encoding="utf-8")
    total_mb = sum(batch_bytes) / 1024 / 1024
    print(f"[Phase1] 完成 {len(batches)} 批次，总 {total_mb:.1f}MB，空图/跳过={empty}")
    return inp_paths


# ============================================================================
# Phase 2：提交 Batch 任务并轮询结果
# ============================================================================
def phase2(work_dir: Path, inp_paths: List[Path]) -> List[Path]:
    """
    Phase 2：将所有 input_*.jsonl 并行提交到百炼 Batch API，并轮询等待结果。

    处理流程：
      1. 为每个批次文件启动一个守护线程
      2. 每个线程：
         a. 上传 JSONL 文件到百炼（files.create）
         b. 创建 Batch 任务（batches.create），指定 24h 完成窗口
         c. 每 30 秒轮询状态（batches.retrieve），直到 completed/failed/expired
         d. 下载结果文件并保存为 result_XXX.jsonl
      3. 支持断点续传：batch_id 保存到 batch_id_XXX.txt，重启后可恢复

    Args:
        work_dir: 工作目录（存放中间文件）
        inp_paths: Phase 1 生成的 input_*.jsonl 文件路径列表

    Returns:
        所有 result_*.jsonl 文件路径列表

    Raises:
        RuntimeError: 如果有批次任务失败
    """
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY, base_url=BATCH_BASE_URL)
    result_paths: List[Path] = []
    lock = threading.Lock()        # 线程锁，保护 result_paths 和 errors 的并发写入
    errors: List[Exception] = []   # 收集所有线程的异常

    def _worker(inp: Path, idx: int):
        """单个批次的工作线程：上传 → 创建 Batch → 轮询 → 下载结果。"""
        try:
            res = work_dir / f"result_{idx:03d}.jsonl"
            bid_f = work_dir / f"batch_id_{idx:03d}.txt"  # 保存 batch_id 用于断点续传
            tag = f"[Phase2-{idx:03d}]"
            # 断点续传：结果文件已存在则跳过
            if res.exists():
                print(f"{tag} 已存在，跳过")
                with lock:
                    result_paths.append(res)
                return
            # 断点续传：batch_id 文件已存在则恢复轮询
            if bid_f.exists():
                bid = bid_f.read_text(encoding="utf-8").strip()
                print(f"{tag} 断点续传 batch_id={bid}")
            else:
                # 正常流程：上传 JSONL 文件
                print(f"{tag} 上传 {inp.name} ...")
                with open(inp, "rb") as f:
                    up = client.files.create(file=f, purpose="batch")
                fid = up.id
                print(f"{tag} file_id={fid}")
                # 创建 Batch 任务：指定 24h 完成窗口
                batch = client.batches.create(
                    input_file_id=fid,
                    endpoint="/v1/chat/completions",
                    completion_window="24h",
                )
                bid = batch.id
                bid_f.write_text(bid, encoding="utf-8")
                print(f"{tag} batch_id={bid}")
            # 轮询 Batch 状态：每 30 秒检查一次，直到完成或失败
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

    # ---- 启动所有工作线程并等待完成 ----
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


# ============================================================================
# Phase 3：解析并合并 Batch 结果
# ============================================================================
def phase3(work_dir: Path, result_paths: List[Path], out: Path) -> None:
    """
    Phase 3：将所有 Batch 结果文件解析并合并为最终 JSON 输出。

    处理流程：
      1. 读取 input_meta.jsonl，按 query_id 建立元数据映射
      2. 遍历所有 result_*.jsonl，按 custom_id 关联元数据
      3. 解析响应体，提取 generated_answer
      4. 处理异常情况：
         - content 为 null 但有 reasoning_content → 标记为 [ERROR] reasoning_only
         - 响应状态码非 200 → 标记为 [ERROR]
         - choices 为空 → 标记为 [ERROR] empty
      5. 输出最终 JSON 文件

    Args:
        work_dir: 工作目录（存放 input_meta.jsonl）
        result_paths: Phase 2 生成的 result_*.jsonl 文件路径列表
        out: 输出 JSON 文件路径
    """
    # 读取元数据文件，建立 query_id → 元数据的映射
    meta_f = work_dir / "input_meta.jsonl"
    meta_f = work_dir / "input_meta.jsonl"
    print("[Phase3] 解析结果...")
    meta_map: Dict[str, Dict[str, Any]] = {}
    for line in meta_f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            o = json.loads(line)
            meta_map[o["query_id"]] = o  # query_id → 元数据字典
    records = []
    errs = 0  # 错误计数
    for rp in sorted(result_paths):
        # 遍历每个结果文件的每一行
        for line in rp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            qid = o.get("custom_id", "")       # custom_id 即 query_id
            m = meta_map.get(qid, {})           # 关联 Phase 1 的元数据
            resp = o.get("response", {})
            # 判断响应是否成功（状态码 200）
            if resp and resp.get("status_code") == 200:
                choices = resp.get("body", {}).get("choices", [])
                if choices:
                    msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                    if isinstance(msg, dict):
                        ans = msg.get("content")
                        # content 为 null 时检查是否有 reasoning_content（深度思考模式的输出）
                        if ans is None:
                            reasoning = msg.get("reasoning_content", "")
                            # 有 reasoning_content 但无 content，标记为错误并截取前 200 字符
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


# ============================================================================
# 命令行入口
# ============================================================================
def main():
    """解析命令行参数，加载数据集，按阶段运行 Batch 推理流水线。"""
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
    domains = args.domains or DOMAINS  # 默认全部 8 个领域
    out_dir = Path(args.output_dir)
    work_dir = out_dir / "_batch_workdir" / args.method  # 中间文件工作目录
    out_path = out_dir / f"{args.method}_results.json"   # 最终输出文件

    # ---- 加载所有领域的查询样本 ----
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

    # ---- 按阶段执行流水线 ----
    run_all = args.phase is None  # 未指定 --phase 时执行全部三个阶段
    inp_paths: List[Path] = []
    # Phase 1：构造 JSONL 请求文件
    if run_all or args.phase == 1:
        inp_paths = phase1(samples, args.method, args.top_k, work_dir)
    # Phase 2：提交 Batch 并轮询结果
    if run_all or args.phase == 2:
        if not inp_paths:
            inp_paths = sorted(work_dir.glob("input_*.jsonl"))
        if not inp_paths:
            print("[ERROR] 未找到 input_*.jsonl，请先执行 Phase1")
            return
        result_paths = phase2(work_dir, inp_paths)
    # Phase 3：解析并合并结果
    if run_all or args.phase == 3:
        result_paths = sorted(work_dir.glob("result_*.jsonl"))
        if not result_paths:
            print("[ERROR] 未找到 result_*.jsonl，请先执行 Phase2")
            return
        phase3(work_dir, result_paths, out_path)
    print("全部完成。")


if __name__ == "__main__":
    main()
