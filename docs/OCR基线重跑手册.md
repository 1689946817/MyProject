# OCR 基线重跑手册

本文档用于在修复 OCR 索引构建问题后，按项目原有实验脚本重跑 `baseline_ocr` 检索器评估和生成器评估。

## 1. 环境准备

1. 使用项目实验环境：

```powershell
E:\Pyenvironment\multimodal-rag\python.exe -V
```

2. 检查 `backend/.env` 中至少包含以下配置：

```env
CHROMA_PERSIST_DIR="E:/BiShe/Code2/MyProject/backend/chroma_data"
PADDLEOCR_PYTHON="E:/Pyenvironment/multimodal-rag/python.exe"
```

3. 安装 OCR 依赖：

```powershell
E:\Pyenvironment\multimodal-rag\python.exe -m pip install -r backend\requirements.txt
E:\Pyenvironment\multimodal-rag\python.exe -m pip install rapidocr_onnxruntime
```

说明：
- OCR 子进程会优先尝试 `PaddleOCR`
- 若 `PaddleOCR` 在当前环境中初始化或推理失败，会自动回退到 `RapidOCR`
- 实验入口脚本和方法名保持不变

## 2. OCR 冒烟验证

先确认 OCR 子进程能对真实页面返回非空文本：

```powershell
@'
import os
from pathlib import Path
os.environ.setdefault("PADDLEOCR_PYTHON", r"E:\Pyenvironment\multimodal-rag\python.exe")
from evaluation.methods import unidoc_ocr
sample = str(next(Path(r"data\UniDoc-Bench-subset\images").rglob("*.png")))
result = unidoc_ocr._run_ocr_subprocess([sample])
print(result[sample][:500])
'@ | E:\Pyenvironment\multimodal-rag\python.exe -
```

若输出为空，不要继续跑实验，先检查 OCR 环境。

## 3. 重建 UniDoc OCR 索引

### 3.1 单领域检索索引

按需要对各领域分别重建：

```powershell
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_unidoc_eval --domain finance --method baseline_ocr --top-k 10 --build-index
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_unidoc_eval --domain energy --method baseline_ocr --top-k 10 --build-index
```

### 3.2 跨领域检索索引

生成器评估和跨领域检索都依赖该索引：

```powershell
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_unidoc_full_eval --method baseline_ocr --top-k 10 --build-index
```

建索引完成后，日志中应能看到类似统计：

```text
OCR stats: total=... non_empty=... fallback=... unique=...
```

要求：
- `non_empty` 大于 0
- `unique` 大于 1

## 4. 重跑检索器评估

### 4.1 UniDoc 单领域检索评估

```powershell
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_unidoc_eval --domain finance --method baseline_ocr --top-k 10
```

结果输出到：

```text
data/eval_results/unidoc_finance_baseline_ocr_*.json
```

### 4.2 UniDoc 跨领域检索评估

```powershell
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_unidoc_full_eval --method baseline_ocr --top-k 10
```

结果输出到：

```text
data/eval_results/unidoc_crossdomain_baseline_ocr_*.json
```

### 4.3 COCO 检索评估

`run_offline_eval.py` 仍沿用原评测方式，但要求 `images_ocr_text` 已提前重建完成。若你有原来的 `image_records` 构造脚本，可直接复用并调用：

```python
from evaluation.methods import baseline_ocr_rag
baseline_ocr_rag.build_ocr_index(image_records)
```

重建后执行：

```powershell
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_offline_eval --dataset-path data/coco_subset_eval.json --method baseline_ocr --top-k 10
```

结果输出到：

```text
data/eval_results/baseline_ocr_*.json
```

## 5. 重跑生成器评估

### 5.1 UniDoc 实时生成评估

```powershell
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_unidoc_gen --method baseline_ocr --top-k 5 --output-dir data/rag_outputs/unidoc_gen
```

结果输出到：

```text
data/rag_outputs/unidoc_gen/unidoc_gen_baseline_ocr_top5.json
```

### 5.2 UniDoc Batch 生成评估

继续使用原 batch 脚本：

```powershell
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_unidoc_gen_batch --method baseline_ocr --top-k 5 --output-dir data/rag_outputs/unidoc_gen_batch
```

分阶段执行时：

```powershell
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_unidoc_gen_batch --method baseline_ocr --top-k 5 --phase 1
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_unidoc_gen_batch --method baseline_ocr --top-k 5 --phase 2
E:\Pyenvironment\multimodal-rag\python.exe -m evaluation.run_unidoc_gen_batch --method baseline_ocr --top-k 5 --phase 3
```

结果输出到：

```text
data/rag_outputs/unidoc_gen_batch/baseline_ocr_results.json
```

## 6. 常见问题排查

### 6.1 仍然出现全 `[no text]`

先看建索引日志中的 `OCR stats`：
- 若 `non_empty=0`，说明 OCR 引擎没有真正识别出文本
- 若脚本直接报 `collapsed`，说明本次索引构建被健康检查拦截，索引不会写入 Chroma

### 6.2 评测脚本提示 `missing or unhealthy`

说明当前 Chroma 中的 OCR 集合不存在，或集合内容仍是坏索引。先重新执行对应的 `--build-index` 命令。

### 6.3 PaddleOCR 可导入但推理失败

当前实现会自动回退到 `RapidOCR`。只要最终 `OCR stats` 正常，并且抽样页面能返回非空文本，就可以继续实验。
