/**
 * 前端共享类型定义模块
 *
 * 包含图像记录、搜索结果、聊天消息、文档记录、配置、任务队列等核心业务类型的接口定义，
 * 供前端所有 API 模块和视图组件统一引用。
 */

/**
 * 图像记录
 *
 * 对应后端 ImageRecord ORM 模型，表示知识库中的一张图片及其元数据。
 * 图片经过 MLLM 处理后会生成文本描述，用于后续的向量检索。
 */
export interface ImageRecord {
  /** 图像唯一标识（UUID 字符串） */
  id: string
  /** 图片在后端存储中的文件路径 */
  file_path: string
  /** 上传时间（ISO 8601 格式） */
  upload_time: string
  /** MLLM 自动生成的图像文本描述，未处理时为 null */
  generated_description?: string | null
  /** 处理状态：Processing=处理中, Completed=已完成, Failed=失败 */
  status: 'Processing' | 'Completed' | 'Failed'
  /** 来源数据集名称（如 COCO 等评测集） */
  source_dataset?: string | null
  /** 用户自定义标题 */
  title?: string | null
  /** 标签列表，用于分类和筛选 */
  tags?: string[]
  /** 用户备注 */
  notes?: string | null
  /** 是否启用（可用于临时禁用某条记录而不删除） */
  enabled?: boolean
  /** 自定义元数据键值对，用于扩展属性 */
  custom_metadata?: Record<string, any>
  /** 资源类型（如 image、table、chart 等） */
  asset_type?: string | null
  /** 所在页码（适用于从文档中提取的图片） */
  page_number?: number | null
  /** 同页中的表格索引（适用于表格资源） */
  table_index_on_page?: number | null
  /** 跨页表格组标识（用于合并被分页截断的表格） */
  table_group_id?: string | null
  /** 是否从上一页延续而来（跨页内容标记） */
  continued_from_previous_page?: boolean
  /** 是否延续到下一页（跨页内容标记） */
  continued_to_next_page?: boolean
  /** 降级处理原因（当主流程失败时的回退说明） */
  fallback_reason?: string | null
  /** 父文档 ID（该图像所属的源文档） */
  parent_doc_id?: string | null
  /** 内容哈希值，用于去重判断 */
  content_hash?: string | null
  /** 逻辑资源 ID，同一物理资源的不同版本共享此 ID */
  logical_asset_id?: string | null
  /** 版本号（用于文档版本管理） */
  version_number?: number
  /** 是否为最新版本 */
  is_latest?: boolean
  /** 是否已去重 */
  deduplicated?: boolean
  /** 去重时指向的原始记录 ID */
  duplicate_of?: string | null
}

/**
 * 搜索结果项
 *
 * 表示一次检索返回的单条匹配结果，包含相似度分数和来源信息。
 */
export interface SearchResultItem {
  /** 匹配记录的唯一标识 */
  id: string
  /** 匹配资源的文件路径 */
  file_path?: string
  /** 匹配资源的文本描述（如 MLLM 生成的图像描述） */
  description?: string
  /** 向量相似度分数（通常 0-1，越大越相似） */
  score: number
  /** 经 rerank 等二次排序后的相关性分数 */
  relevance_score?: number | null
  /** 分数来源标识（如 "vector", "rerank"） */
  score_source?: string | null
  /** 资源类型（如 image、table、chart） */
  asset_type?: string | null
  /** 所在页码 */
  page_number?: number | null
  /** 跨页表格组标识 */
  table_group_id?: string | null
  /** 是否从上一页延续 */
  continued_from_previous_page?: boolean
  /** 是否延续到下一页 */
  continued_to_next_page?: boolean
}

/**
 * 聊天引用来源项
 *
 * RAG 问答中检索到的参考文档或图像，作为回答的依据展示给用户。
 */
export interface ChatSourceItem {
  /** 来源类型（如 "document_chunk", "image", "web"） */
  source_type: string
  /** 来源记录的唯一标识 */
  source_id: string
  /** 来源标题 */
  title?: string
  /** 来源文件路径 */
  file_path?: string
  /** 来源文本内容（如文档片段） */
  content?: string
  /** 初始检索相似度分数 */
  score?: number
  /** 经 rerank 模型重排后的分数 */
  rerank_score?: number
  /** 综合相关性分数 */
  relevance_score?: number | null
  /** 分数来源标识 */
  score_source?: string | null
  /** 附加元数据 */
  metadata?: Record<string, any>
}

/**
 * 引用文档片段引用
 *
 * 将回答中的引用锚点关联到具体的文档分片。
 */
export interface ChatCitationChunkRef {
  /** 所属文档 ID */
  doc_id: string
  /** 分片在文档中的索引号 */
  chunk_index: number
  /** 所在页码 */
  page_number?: number | null
}

/**
 * 聊天引用项
 *
 * 表示回答中某一段落的引用信息，将段落与来源关联。
 */
export interface ChatCitationItem {
  /** 段落唯一键（用于前端 DOM 锚点） */
  paragraph_key: string
  /** 段落序号（从 0 开始） */
  paragraph_index: number
  /** 引用的来源 ID 列表 */
  source_ids: string[]
  /** 引用的文档分片引用列表 */
  doc_chunk_refs?: ChatCitationChunkRef[]
  /** 置信度（0-1，null 表示未计算） */
  confidence?: number | null
}

/**
 * 检索步骤项
 *
 * RAG 处理管线中单个步骤的执行详情，用于向用户展示检索过程。
 */
export interface RetrievalStepItem {
  /** 步骤唯一键（如 "rewrite", "retrieve", "rerank"） */
  key: string
  /** 步骤展示名称 */
  label: string
  /** 步骤摘要描述 */
  summary?: string
  /** 步骤详细信息（如检索参数、返回数量等） */
  details?: Record<string, any>
}

/**
 * 聊天进度阶段
 *
 * RAG 管线的处理阶段枚举，用于实时展示后端处理进度。
 * routing→意图路由, rewrite→查询改写, retrieve→检索, rerank→重排,
 * compress→压缩, agentic→Agent推理, generate→生成回答, complete→完成
 */
export type ChatProgressPhase =
  | "routing"
  | "rewrite"
  | "retrieve"
  | "rerank"
  | "compress"
  | "agentic"
  | "generate"
  | "complete"

/**
 * 聊天进度状态
 *
 * started=已启动, running=运行中, completed=已完成, skipped=已跳过, failed=失败
 */
export type ChatProgressStatus = "started" | "running" | "completed" | "skipped" | "failed"

/**
 * 聊天进度事件
 *
 * 后端通过 SSE 推送的进度通知，前端用于实时更新处理阶段 UI。
 */
export interface ChatProgressEvent {
  /** 事件类型标识（始终为 "progress"） */
  type?: "progress"
  /** 当前所处的处理阶段 */
  phase: ChatProgressPhase
  /** 当前阶段的执行状态 */
  status: ChatProgressStatus
  /** 阶段标题（用于 UI 展示） */
  title: string
  /** 阶段详细说明 */
  detail?: string
  /** 已耗时（毫秒） */
  elapsed_ms?: number
  /** 当前聊天模式 */
  chat_mode?: ChatMode
  /** 当前执行模式 */
  execution_mode?: ExecutionMode
  /** 是否使用了 RAG 检索 */
  use_rag?: boolean
  /** 关联的检索步骤键名 */
  step_key?: string
  /** 扩展元数据 */
  meta?: Record<string, any>
}

/**
 * 计时阶段
 *
 * 后端性能追踪中单个阶段的耗时信息。
 */
export interface TimingStage {
  /** 阶段名称（如 "retrieve", "rerank", "generate"） */
  name: string
  /** 阶段耗时（毫秒） */
  elapsed_ms: number
  /** 阶段状态 */
  status?: string
  /** 阶段附加元数据 */
  meta?: Record<string, any>
}

/**
 * 计时摘要
 *
 * 一次请求的完整性能追踪数据，包含各阶段耗时和首 token 延迟。
 */
export interface TimingSummary {
  /** 追踪唯一标识 */
  trace_id: string
  /** 请求路径（如 "/api/rag/chat"） */
  request_path: string
  /** 请求类型（如 "chat", "search"） */
  request_kind: string
  /** 总耗时（毫秒） */
  total_ms: number
  /** 首 token 延迟（毫秒，流式响应时有效） */
  first_token_ms?: number | null
  /** 请求元数据 */
  metadata?: Record<string, any>
  /** 各阶段耗时列表 */
  stages: TimingStage[]
}

/**
 * QA 流程步骤视图模型
 *
 * 前端 UI 展示用的检索步骤模型，包含状态、耗时和详情列表。
 */
export interface QaProcessStepViewModel {
  /** 步骤唯一键 */
  key: string
  /** 步骤展示名称 */
  label: string
  /** 步骤摘要 */
  summary?: string
  /** 步骤执行状态 */
  status?: ChatProgressStatus
  /** 是否为当前活跃步骤 */
  isActive?: boolean
  /** 步骤耗时（毫秒） */
  durationMs?: number | null
  /** 步骤详情列表（键值对形式，便于 UI 渲染） */
  details: Array<{
    key: string
    label: string
    value: string
  }>
}

/**
 * QA 流程汇总视图模型
 *
 * 前端 UI 展示用的整次问答流程汇总，包含模式、耗时和重试信息。
 */
export interface QaProcessSummaryViewModel {
  /** 聊天模式 */
  chatMode?: ChatMode
  /** 执行模式名称 */
  executionMode: string
  /** 展示模式名称 */
  presentationMode: string
  /** 是否使用 RAG */
  useRag: boolean
  /** 是否为实时处理中 */
  isLive?: boolean
  /** 当前活跃阶段的状态 */
  activeStatus?: ChatProgressStatus | null
  /** 当前活跃阶段的标题 */
  activeTitle?: string | null
  /** 总耗时（毫秒） */
  totalMs?: number | null
  /** 是否使用了重试 */
  retryUsed: boolean
}

/**
 * 聊天模式
 *
 * fast=快速模式（直接 LLM，无检索）, default=标准模式（RAG 检索+生成）,
 * expert=专家模式（多路检索+rerank+高级推理）
 */
export type ChatMode = "fast" | "default" | "expert"

/**
 * 展示模式
 *
 * 控制前端如何呈现回答：纯文本、带来源、仅图片、图片+文本。
 */
export type PresentationMode = "direct_answer" | "rag_answer" | "image_only" | "image_plus_answer"

/**
 * 执行模式
 *
 * 后端实际采用的推理策略：
 * - direct_llm：直接调用 LLM 回答
 * - multimodal_rag：多模态 RAG 检索后生成
 * - image_similarity：图像相似度检索
 * - image_grounded_answer：基于图像内容生成回答
 * - uploaded_image_qa：用户上传图片问答
 * - save_uploaded_image：保存用户上传的图片
 */
export type ExecutionMode =
  | "direct_llm"
  | "multimodal_rag"
  | "image_similarity"
  | "image_grounded_answer"
  | "uploaded_image_qa"
  | "save_uploaded_image"

/**
 * 聊天会话
 *
 * 表示一次完整的对话会话，包含会话元数据。
 */
export interface ChatSession {
  /** 会话唯一标识 */
  id: string
  /** 会话标题（通常取首条消息摘要） */
  title: string
  /** 创建时间（ISO 8601） */
  created_at: string
  /** 最后更新时间（ISO 8601） */
  updated_at: string
}

/**
 * 聊天消息
 *
 * 表示对话中的一条消息，支持用户和助手两种角色，
 * 包含消息内容、检索来源、引用信息和处理进度等丰富数据。
 */
export interface ChatMessage {
  /** 消息唯一标识（本地消息为 number，持久化后为 string） */
  id: string | number
  /** 所属会话 ID */
  session_id: string
  /** 消息角色：user=用户消息, assistant=助手回复 */
  role: 'user' | 'assistant'
  /** 消息文本内容 */
  content: string
  /** 是否包含用户上传的图片 */
  has_image?: boolean
  /** 用户上传图片的本地预览 URL */
  local_image_url?: string
  /** 后端持久化的上传图片预览路径 */
  uploaded_image_path?: string | null
  /** 用户上传图片的原始文件名 */
  uploaded_image_name?: string | null
  /** RAG 检索到的引用来源列表 */
  sources?: ChatSourceItem[]
  /** 回答中的引用锚点列表 */
  citations?: ChatCitationItem[]
  /** 本次使用的聊天模式 */
  chat_mode?: ChatMode
  /** 本次使用的展示模式 */
  presentation_mode?: PresentationMode
  /** 本次使用的执行模式 */
  execution_mode?: ExecutionMode
  /** 是否启用了 RAG 检索 */
  use_rag?: boolean
  /** 检索管线各步骤的执行详情 */
  retrieval_steps?: RetrievalStepItem[]
  /** 检索参数快照（用于调试和复现） */
  retrieval_params?: Record<string, any> | null
  /** 用户对该回答的反馈 */
  feedback?: AnswerFeedbackResponse | null
  /** 性能计时数据 */
  timings?: TimingSummary | null
  /** 最新的实时进度事件 */
  live_progress?: ChatProgressEvent | null
  /** 完整的实时进度事件历史 */
  live_progress_steps?: ChatProgressEvent[]
  /** 进度推送开始时间（ISO 8601） */
  live_progress_started_at?: string | null
  /** 当前活跃的进度阶段 */
  live_progress_active_phase?: ChatProgressPhase | null
  /** 进度推送是否已完成 */
  live_progress_done?: boolean
  /** 消息创建时间（ISO 8601） */
  created_at: string
}

/**
 * 回答反馈请求
 *
 * 用户对助手回答的评价提交数据。
 */
export interface AnswerFeedbackRequest {
  /** 评价方向：up=好评, down=差评 */
  rating: "up" | "down"
  /** 问题类型列表（差评时选填，如 "incorrect", "incomplete", "irrelevant"） */
  issue_types?: string[]
  /** 用户补充评论 */
  comment?: string | null
}

/**
 * 回答反馈响应
 *
 * 已保存的用户反馈记录。
 */
export interface AnswerFeedbackResponse {
  /** 反馈记录 ID */
  id: number
  /** 所属会话 ID */
  session_id?: string | null
  /** 被评价的助手消息 ID */
  assistant_message_id: number
  /** 评价方向 */
  rating: "up" | "down"
  /** 问题类型列表 */
  issue_types: string[]
  /** 用户评论 */
  comment?: string | null
  /** 原始查询文本（快照） */
  query?: string | null
  /** 检索结果快照（用于问题分析） */
  retrieval_snapshot?: Record<string, any>
  /** 反馈创建时间（ISO 8601） */
  created_at: string
}

/**
 * 文档记录
 *
 * 表示知识库中的一份文档，支持多种格式（PDF、Word、Markdown 等）。
 * 文档上传后会经过解析、分片、向量化等处理流程。
 */
export interface DocumentRecord {
  /** 文档唯一标识（UUID） */
  id: string
  /** 原始文件名 */
  file_name: string
  /** 用户自定义标题 */
  title?: string | null
  /** 文档在后端存储中的文件路径 */
  file_path?: string
  /** 上传时间（ISO 8601） */
  upload_time: string
  /** 处理状态：Processing=处理中, Completed=已完成, Failed=失败 */
  status: 'Processing' | 'Completed' | 'Failed'
  /** 文档分片数量 */
  chunk_count: number
  /** 文档中提取的图片数量 */
  image_count: number
  /** 文档类型（如 pdf, docx, markdown） */
  document_type?: string
  /** 标签列表 */
  tags?: string[]
  /** 用户备注 */
  notes?: string | null
  /** 是否启用 */
  enabled?: boolean
  /** 自定义元数据 */
  custom_metadata?: Record<string, any>
  /** 解析后端标识（如 "mineru", "marker"） */
  parse_backend?: string
  /** 当前解析阶段 */
  parse_stage?: string
  /** 处理进度百分比（0-100） */
  progress_percent?: number
  /** 处理进度说明消息 */
  progress_message?: string | null
  /** 内容哈希值（用于去重） */
  content_hash?: string | null
  /** 逻辑资源 ID（同资源不同版本共享） */
  logical_asset_id?: string | null
  /** 版本号 */
  version_number?: number
  /** 是否为最新版本 */
  is_latest?: boolean
  /** 是否已去重 */
  deduplicated?: boolean
  /** 去重时指向的原始记录 ID */
  duplicate_of?: string | null
}

/**
 * 文档解析结果
 *
 * 文档完整解析后的结构化输出，包含文档元数据、文本分片和提取的图片。
 */
export interface DocParseResult {
  /** 文档元数据 */
  document: DocumentRecord
  /** 文档分片列表 */
  chunks: DocChunk[]
  /** 从文档中提取的图片列表 */
  images: ImageRecord[]
}

/**
 * 文档文本片段
 *
 * 文档经过分片后的单个文本块，用于向量检索和上下文引用。
 */
export interface DocChunk {
  /** 所属文档 ID */
  doc_id: string
  /** 分片在文档中的索引号（从 0 开始） */
  chunk_index: number
  /** 分片文本内容 */
  content: string
  /** 检索时的相似度分数（可选） */
  score?: number
  /** 所在页码 */
  page_number?: number | null
  /** 来源类型（如 "text", "table", "figure_caption"） */
  source_type?: string | null
}

/**
 * 配置选项
 *
 * 下拉选择框中的单个选项。
 */
export interface ConfigOption {
  /** 选项显示文本 */
  label: string
  /** 选项实际值 */
  value: string
}

/**
 * 配置分组
 *
 * 系统配置项的逻辑分组，用于前端分类展示。
 */
export interface ConfigGroup {
  /** 分组唯一键 */
  key: string
  /** 分组显示名称 */
  label: string
  /** 分组说明 */
  description?: string | null
}

/**
 * 配置项
 *
 * 单个系统配置项的完整定义，包含类型、验证规则和 UI 渲染信息。
 */
export interface ConfigItem {
  /** 配置项唯一键（对应后端环境变量名） */
  key: string
  /** 所属分组键 */
  group: string
  /** 配置项显示名称 */
  label: string
  /** 配置项详细说明 */
  description: string
  /** 前端输入控件类型 */
  inputType: "text" | "textarea" | "password" | "switch" | "number" | "select"
  /** 值解析类型（决定后端如何解析提交的值） */
  parseAs: "string" | "bool" | "int" | "float" | "csv" | "url" | "path"
  /** 当前配置值 */
  value: string | number | boolean
  /** 是否为敏感信息（如 API Key，前端需遮蔽显示） */
  sensitive: boolean
  /** 是否必填 */
  required: boolean
  /** 修改后是否需要重启服务 */
  restartRequired: boolean
  /** 输入框占位文本 */
  placeholder?: string | null
  /** 下拉选项列表（inputType 为 select 时使用） */
  options?: ConfigOption[]
}

/**
 * 配置响应
 *
 * 获取系统配置时的完整返回结构。
 */
export interface ConfigResponse {
  /** 配置分组列表 */
  groups: ConfigGroup[]
  /** 配置项列表 */
  items: ConfigItem[]
  /** 是否有待生效的重启 */
  restart_required: boolean
  /** 响应提示消息 */
  message: string
}

/**
 * 配置更新请求体
 *
 * 批量更新系统配置时提交的数据。
 */
export interface ConfigUpdatePayload {
  /** 待更新的配置键值对 */
  values: Record<string, string | number | boolean>
}

/**
 * 配置重启响应
 *
 * 后端接收重启请求后的返回结构。
 */
export interface ConfigRestartResponse {
  /** 是否成功接收重启请求 */
  success: boolean
  /** 响应提示消息 */
  message: string
  /** 是否已调度重启 */
  restart_scheduled: boolean
}

/**
 * 配置校验错误
 *
 * 配置更新失败时返回的错误详情。
 */
export interface ConfigValidationError {
  /** 字段级错误信息（键为配置项 key，值为错误描述） */
  field_errors?: Record<string, string>
  /** 整体错误消息 */
  message?: string
}

/**
 * 任务项
 *
 * 后端任务队列中的单个任务，用于异步处理文档解析、批量导入等操作。
 */
export interface JobTask {
  /** 任务唯一标识 */
  id: string
  /** 任务类型（如 "doc_parse", "batch_import"） */
  job_type: string
  /** 任务状态（如 "queued", "running", "completed", "failed"） */
  status: string
  /** 优先级（数值越小优先级越高） */
  priority: number
  /** 任务输入数据 */
  payload: Record<string, any>
  /** 任务执行结果 */
  result: Record<string, any>
  /** 错误消息（失败时） */
  error_message?: string | null
  /** 已重试次数 */
  retry_count: number
  /** 最大重试次数 */
  max_retries: number
  /** 当前锁定执行的 worker 标识 */
  locked_by?: string | null
  /** 关联的文档 ID */
  related_doc_id?: string | null
  /** 关联的批量导入 ID */
  related_batch_id?: string | null
  /** 创建时间（ISO 8601） */
  created_at: string
  /** 开始执行时间（ISO 8601） */
  started_at?: string | null
  /** 完成时间（ISO 8601） */
  finished_at?: string | null
}

/**
 * 批量导入批次
 *
 * 一次批量导入操作的汇总信息。
 */
export interface ImportBatch {
  /** 批次唯一标识 */
  id: string
  /** 来源类型（如 "document"） */
  source_type: string
  /** 批次状态 */
  status: string
  /** 批次汇总数据（如各状态任务数量） */
  summary: Record<string, any>
  /** 创建时间（ISO 8601） */
  created_at: string
  /** 最后更新时间（ISO 8601） */
  updated_at: string
}

/**
 * 批量导入响应
 *
 * 发起批量导入后返回的完整结果。
 */
export interface BatchImportResponse {
  /** 批次信息 */
  batch: ImportBatch
  /** 创建的任务列表 */
  jobs: JobTask[]
  /** 创建的文档记录列表 */
  documents: DocumentRecord[]
  /** 响应提示消息 */
  message: string
  /** 性能计时数据 */
  timings?: TimingSummary | null
}

/**
 * 健康检查状态
 *
 * 后端服务健康检查的返回结果。
 */
export interface HealthStatus {
  /** 整体状态（如 "ok", "degraded"） */
  status: string
  /** 各依赖项的检查结果 */
  checks: Record<string, any>
  /** 检查生成时间（ISO 8601） */
  generated_at: string
}

/**
 * 指标汇总
 *
 * 从 Prometheus 格式指标解析出的任务队列和 Worker 状态汇总。
 */
export interface MetricsSummary {
  /** 原始 Prometheus 指标文本 */
  raw: string
  /** 任务总数 */
  totalJobs: number
  /** 排队中任务数 */
  queuedJobs: number
  /** 执行中任务数 */
  runningJobs: number
  /** 失败任务数 */
  failedJobs: number
  /** 已完成任务数 */
  completedJobs: number
  /** 活跃 Worker 数 */
  activeWorkers: number
  /** 最近一次 Worker 心跳时间（ISO 8601） */
  latestWorkerHeartbeat?: string | null
}
