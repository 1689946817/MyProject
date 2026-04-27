/**
 * 共享类型定义
 */

/**
 * 图像记录
 */
export interface ImageRecord {
  id: string
  file_path: string
  upload_time: string
  generated_description?: string | null
  status: 'Processing' | 'Completed' | 'Failed'
  source_dataset?: string | null
  title?: string | null
  tags?: string[]
  notes?: string | null
  enabled?: boolean
  custom_metadata?: Record<string, any>
  asset_type?: string | null
  page_number?: number | null
  table_index_on_page?: number | null
  table_group_id?: string | null
  continued_from_previous_page?: boolean
  continued_to_next_page?: boolean
  fallback_reason?: string | null
  parent_doc_id?: string | null
  content_hash?: string | null
  logical_asset_id?: string | null
  version_number?: number
  is_latest?: boolean
  deduplicated?: boolean
  duplicate_of?: string | null
}

/**
 * 搜索结果项
 */
export interface SearchResultItem {
  id: string
  file_path?: string
  description?: string
  score: number
  relevance_score?: number | null
  score_source?: string | null
  asset_type?: string | null
  page_number?: number | null
  table_group_id?: string | null
  continued_from_previous_page?: boolean
  continued_to_next_page?: boolean
}

export interface ChatSourceItem {
  source_type: string
  source_id: string
  title?: string
  file_path?: string
  content?: string
  score?: number
  rerank_score?: number
  relevance_score?: number | null
  score_source?: string | null
  metadata?: Record<string, any>
}

export interface ChatCitationChunkRef {
  doc_id: string
  chunk_index: number
  page_number?: number | null
}

export interface ChatCitationItem {
  paragraph_key: string
  paragraph_index: number
  source_ids: string[]
  doc_chunk_refs?: ChatCitationChunkRef[]
  confidence?: number | null
}

export interface RetrievalStepItem {
  key: string
  label: string
  summary?: string
  details?: Record<string, any>
}

export type ChatProgressPhase =
  | "routing"
  | "rewrite"
  | "retrieve"
  | "rerank"
  | "compress"
  | "agentic"
  | "generate"
  | "complete"

export type ChatProgressStatus = "started" | "running" | "completed" | "skipped" | "failed"

export interface ChatProgressEvent {
  type?: "progress"
  phase: ChatProgressPhase
  status: ChatProgressStatus
  title: string
  detail?: string
  elapsed_ms?: number
  chat_mode?: ChatMode
  execution_mode?: ExecutionMode
  use_rag?: boolean
  step_key?: string
  meta?: Record<string, any>
}

export interface TimingStage {
  name: string
  elapsed_ms: number
  status?: string
  meta?: Record<string, any>
}

export interface TimingSummary {
  trace_id: string
  request_path: string
  request_kind: string
  total_ms: number
  first_token_ms?: number | null
  metadata?: Record<string, any>
  stages: TimingStage[]
}

export interface QaProcessStepViewModel {
  key: string
  label: string
  summary?: string
  status?: ChatProgressStatus
  isActive?: boolean
  durationMs?: number | null
  details: Array<{
    key: string
    label: string
    value: string
  }>
}

export interface QaProcessSummaryViewModel {
  chatMode?: ChatMode
  executionMode: string
  presentationMode: string
  useRag: boolean
  isLive?: boolean
  activeStatus?: ChatProgressStatus | null
  activeTitle?: string | null
  totalMs?: number | null
  retryUsed: boolean
}

export type ChatMode = "fast" | "default" | "expert"
export type PresentationMode = "direct_answer" | "rag_answer" | "image_only" | "image_plus_answer"
export type ExecutionMode =
  | "direct_llm"
  | "multimodal_rag"
  | "image_similarity"
  | "image_grounded_answer"
  | "uploaded_image_qa"
  | "save_uploaded_image"

/**
 * 聊天会话
 */
export interface ChatSession {
  id: string
  title: string
  created_at: string
  updated_at: string
}

/**
 * 聊天消息
 */
export interface ChatMessage {
  id: string | number
  session_id: string
  role: 'user' | 'assistant'
  content: string
  has_image?: boolean
  local_image_url?: string
  sources?: ChatSourceItem[]
  citations?: ChatCitationItem[]
  chat_mode?: ChatMode
  presentation_mode?: PresentationMode
  execution_mode?: ExecutionMode
  use_rag?: boolean
  retrieval_steps?: RetrievalStepItem[]
  retrieval_params?: Record<string, any> | null
  feedback?: AnswerFeedbackResponse | null
  timings?: TimingSummary | null
  live_progress?: ChatProgressEvent | null
  live_progress_steps?: ChatProgressEvent[]
  live_progress_started_at?: string | null
  live_progress_active_phase?: ChatProgressPhase | null
  live_progress_done?: boolean
  created_at: string
}

export interface AnswerFeedbackRequest {
  rating: "up" | "down"
  issue_types?: string[]
  comment?: string | null
}

export interface AnswerFeedbackResponse {
  id: number
  session_id?: string | null
  assistant_message_id: number
  rating: "up" | "down"
  issue_types: string[]
  comment?: string | null
  query?: string | null
  retrieval_snapshot?: Record<string, any>
  created_at: string
}

/**
 * 文档记录
 */
export interface DocumentRecord {
  id: string
  file_name: string
  title?: string | null
  file_path?: string
  upload_time: string
  status: 'Processing' | 'Completed' | 'Failed'
  chunk_count: number
  image_count: number
  document_type?: string
  tags?: string[]
  notes?: string | null
  enabled?: boolean
  custom_metadata?: Record<string, any>
  parse_backend?: string
  parse_stage?: string
  progress_percent?: number
  progress_message?: string | null
  content_hash?: string | null
  logical_asset_id?: string | null
  version_number?: number
  is_latest?: boolean
  deduplicated?: boolean
  duplicate_of?: string | null
}

/**
 * 文档解析结果
 */
export interface DocParseResult {
  document: DocumentRecord
  chunks: DocChunk[]
  images: ImageRecord[]
}

/**
 * 文档文本片段
 */
export interface DocChunk {
  doc_id: string
  chunk_index: number
  content: string
  score?: number
  page_number?: number | null
  source_type?: string | null
}

export interface ConfigOption {
  label: string
  value: string
}

export interface ConfigGroup {
  key: string
  label: string
  description?: string | null
}

export interface ConfigItem {
  key: string
  group: string
  label: string
  description: string
  inputType: "text" | "textarea" | "password" | "switch" | "number" | "select"
  parseAs: "string" | "bool" | "int" | "float" | "csv" | "url" | "path"
  value: string | number | boolean
  sensitive: boolean
  required: boolean
  restartRequired: boolean
  placeholder?: string | null
  options?: ConfigOption[]
}

export interface ConfigResponse {
  groups: ConfigGroup[]
  items: ConfigItem[]
  restart_required: boolean
  message: string
}

export interface ConfigUpdatePayload {
  values: Record<string, string | number | boolean>
}

export interface ConfigValidationError {
  field_errors?: Record<string, string>
  message?: string
}

export interface JobTask {
  id: string
  job_type: string
  status: string
  priority: number
  payload: Record<string, any>
  result: Record<string, any>
  error_message?: string | null
  retry_count: number
  max_retries: number
  locked_by?: string | null
  related_doc_id?: string | null
  related_batch_id?: string | null
  created_at: string
  started_at?: string | null
  finished_at?: string | null
}

export interface ImportBatch {
  id: string
  source_type: string
  status: string
  summary: Record<string, any>
  created_at: string
  updated_at: string
}

export interface BatchImportResponse {
  batch: ImportBatch
  jobs: JobTask[]
  documents: DocumentRecord[]
  message: string
  timings?: TimingSummary | null
}

export interface HealthStatus {
  status: string
  checks: Record<string, any>
  generated_at: string
}

export interface MetricsSummary {
  raw: string
  totalJobs: number
  queuedJobs: number
  runningJobs: number
  failedJobs: number
  completedJobs: number
  activeWorkers: number
  latestWorkerHeartbeat?: string | null
}
