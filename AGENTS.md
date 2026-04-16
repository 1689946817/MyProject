# Repository Guidelines

## 项目结构与模块组织
本仓库分为三个主要区域：

- `backend/`：FastAPI 后端服务。入口文件是 `backend/main.py`；核心代码位于 `backend/app/`，按 `api/routers/`、`application/`、`core/`、`data/`、`retrieval/`、`semantic/` 和 `langchain_integration/` 划分。
- `frontend/`：基于 Vue 3、TypeScript 和 Vite 的前端。主要代码在 `frontend/src/`，其中 `views/` 放页面，`api/` 放 HTTP 封装，`router/` 放路由配置，`composables/` 放组合式函数。
- `evaluation/`：离线检索评测脚本、数据集、指标计算和基线/方案实现。

当前运行期产物位于 `backend/app.db`、`backend/chroma_data/` 和 `backend/storage/`。这些目录应视为开发数据，而不是源码。

## 构建、测试与开发命令

### 后端
- `cd backend && pip install -r requirements.txt`：安装后端依赖。
- `cd backend && python main.py`：启动 API，默认地址为 `http://localhost:9090`。
- `python test_backend.py`：运行后端冒烟测试，覆盖检索、LLM 和 RAG 流程。
- `cd backend && python -m pytest tests/ -v`：运行后端单元测试。
- `cd backend && python -m pytest tests/test_file.py -v -k test_name`：运行单个测试文件或测试用例。
- `cd backend && python -m pytest tests/test_file.py::test_function -v`：运行指定测试函数。
- `python -m evaluation.run_offline_eval --dataset-path data/coco_subset_eval.json --method proposed --top-k 10`：执行离线评测。

### 前端
- `cd frontend && npm install`：安装前端依赖。
- `cd frontend && npm run dev`：启动 Vite 开发服务器，默认地址为 `http://localhost:5173`。
- `cd frontend && npm run build`：构建前端生产包。
- `cd frontend && npm run preview`：预览生产构建。
- `cd frontend && npx vue-tsc --noEmit`：TypeScript 类型检查（无输出）。

### 通用
- 仓库当前没有配置统一的 linter 或 formatter（如 ruff、black、eslint、prettier）。提交前请遵循现有风格。

## 编码风格与命名约定

### Python (后端)
- 使用 4 空格缩进。
- 使用类型注解（typing 模块），尤其是函数参数和返回值。
- 模块、函数和变量使用 `snake_case`；类名使用 `PascalCase`。
- 常量使用 `UPPER_SNAKE_CASE`。
- 私有函数/变量使用前导下划线（如 `_internal_helper`）。
- FastAPI 路由文件应保持精简，仅做参数解析和响应封装；业务编排逻辑放入 `application/` 或 `semantic/`。
- 导入分组顺序：标准库 → 第三方库 → 本地模块，组间空一行。
- 使用 Pydantic model 定义请求/响应 schema（见 `application/schemas.py`）。
- 错误处理：使用 `HTTPException` 抛出 HTTP 错误；业务异常定义自定义异常类（如 `ChatSessionNotFoundError`），在路由层捕获并转为 `HTTPException`。
- 数据库操作使用 SQLAlchemy ORM，通过 `get_db` 依赖注入 session。
- 异步函数使用 `async def`，调用外部 API（LLM、检索）时务必 await。
- 主要服务使用模块级全局变量 + getter 函数的单例模式（如 `get_langchain_adapter()`）。

### TypeScript/Vue (前端)
- 使用 2 空格缩进、分号和双引号。
- 采用 Vue 单文件组件和 `<script setup lang="ts">`。
- 页面组件使用 PascalCase（如 `Search.vue`、`Chat.vue`）。
- 组合式变量、`ref`、`computed` 和 API 辅助函数使用 camelCase。
- 组件文件名使用 PascalCase；组合式函数文件使用 camelCase（如 `useTheme.ts`）。
- 类型定义放在 `types/` 目录，使用 interface 或 type 定义。
- API 调用封装在 `api/` 目录，使用 axios 实例（见 `http.ts`）。
- 路由配置在 `router/index.ts`，使用懒加载（`() => import(...)`）。
- 使用 UnoCSS 进行样式编写，避免内联 style。
- 错误处理：使用 try/catch 包裹 API 调用，通过 Element Plus 的 ElMessage 提示用户。
- 路径别名：`@/*` 映射到 `src/*`（见 `tsconfig.json`）。

## 测试指南
- 当前没有强制覆盖率要求。修改代码时应尽量补充贴近变更点的测试。
- Python 测试文件使用 `test_*.py` 命名，放在 `backend/tests/` 或项目根目录。
- 测试函数使用 `test_` 前缀。
- 异步测试使用 `async def test_*`，通过 `pytest-asyncio` 运行。
- 使用 `unittest.mock`（Mock、MagicMock、AsyncMock、patch）进行模拟。
- 前端当前无自动化测试框架；手动验证相关流程。
- 至少运行 `python test_backend.py` 验证后端冒烟测试通过。

## 架构关键模式
- **LangChain Adapter 模式**：`LangChainAdapter` 是 API 路由与 LangChain 组件的唯一接口。路由不应直接调用 Chain 或 Retriever。
- **双路检索**：文本查询直接进入 embedding + ChromaDB；图像查询先通过 MLLM 生成描述，再走文本路径。
- **三存储一致性**：SQLite（元数据）、ChromaDB（向量）和文件存储（图片）必须保持基于 UUID 的 ID 一致。

## 提交与 Pull Request 规范
- 当前 Git 历史很少，仅有 `init`，因此暂时没有成熟的提交规范。
- 建议使用简短的祈使句标题，例如 `backend: add health check validation` 或 `frontend: guard empty uploads`。
- PR 应包含清晰的变更说明、涉及目录、配置或数据影响，以及验证步骤。
- UI 变更请附截图；API 变更请附示例请求或响应。

## 配置与安全
- 后端配置从 `backend/.env` 和 `backend/.env.example` 读取。
- **不要提交真实 API Key**。若调整模型端点、数据库路径或 CORS 设置，请在 PR 中明确说明所需的 `.env` 变更。
- 前端代理配置在 `frontend/vite.config.ts`。
- 敏感配置（如数据库 URL、LLM API Key）应通过环境变量注入，不要硬编码。
- 国际化文件位于 `frontend/src/locales/`，新增文本需同步更新 `zh-CN.ts` 和 `en-US.ts`。


必读路径：docs/、实验数据/、evaluation/
事实优先级：代码/实验数据 > 系统设计/分析报告 > 开题/中期报告
禁止编造实验结果、功能模块、性能指标
先产出 facts_inventory.md / terminology_table.md / compliance_checklist.md / thesis_outline.md
先 /plan 再写正文
最终必须输出基于模板的 docx
语言风格约束：自然、克制、减少“AI味”
术语统一与格式审校要求