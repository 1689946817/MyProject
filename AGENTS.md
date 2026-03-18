# Repository Guidelines

## 项目结构与模块组织
本仓库分为三个主要区域：

- `backend/`：FastAPI 后端服务。入口文件是 `backend/main.py`；核心代码位于 `backend/app/`，按 `api/routers/`、`application/`、`core/`、`data/`、`retrieval/` 和 `semantic/` 划分。
- `frontend/`：基于 Vue 3、TypeScript 和 Vite 的前端。主要代码在 `frontend/src/`，其中 `views/` 放页面，`api/` 放 HTTP 封装，`router/` 放路由配置。
- `evaluation/`：离线检索评测脚本、数据集、指标计算和基线/方案实现。

当前运行期产物位于 `backend/app.db`、`backend/chroma_data/` 和 `backend/storage/`。这些目录应视为开发数据，而不是源码。

## 构建、测试与开发命令
- `cd backend && pip install -r requirements.txt`：安装后端依赖。
- `cd backend && python main.py`：启动 API，默认地址为 `http://localhost:9090`。
- `cd frontend && npm install`：安装前端依赖。
- `cd frontend && npm run dev`：启动 Vite 开发服务器，默认地址为 `http://localhost:5173`。
- `cd frontend && npm run build`：构建前端生产包。
- `python test_backend.py`：运行当前后端冒烟脚本，覆盖检索、LLM 和 RAG 流程。
- `python -m evaluation.run_offline_eval --dataset-path data/coco_subset_eval.json --method proposed --top-k 10`：执行离线评测。

## 编码风格与命名约定
Python 使用 4 空格缩进、类型注解，以及 `snake_case` 命名模块、函数和变量。FastAPI 路由文件应保持精简，编排逻辑尽量放入 `application/` 或 `semantic/`。

前端采用 Vue 单文件组件和 `<script setup lang="ts">`，使用 2 空格缩进、分号和双引号。页面组件使用 PascalCase，例如 `Search.vue`；组合式变量、`ref` 和 API 辅助函数使用 camelCase。

仓库当前没有配置统一的 linter 或 formatter。提交前请遵循现有风格，保持 import 分组清晰且尽量精简。

## 测试指南
当前没有强制覆盖率要求。修改代码时应尽量补充贴近变更点的测试；至少运行 `python test_backend.py`，并手动验证相关前端流程。新增 Python 测试文件请使用 `test_*.py` 命名。

## 提交与 Pull Request 规范
当前 Git 历史很少，仅有 `init`，因此暂时没有成熟的提交规范。建议使用简短的祈使句标题，例如 `backend: add health check validation` 或 `frontend: guard empty uploads`。

PR 应包含清晰的变更说明、涉及目录、配置或数据影响，以及验证步骤。UI 变更请附截图；API 变更请附示例请求或响应。

## 配置与安全
后端配置从 `backend/.env` 和 `backend/.env.example` 读取。不要提交真实 API Key。若调整模型端点、数据库路径或 CORS 设置，请在 PR 中明确说明所需的 `.env` 变更。
