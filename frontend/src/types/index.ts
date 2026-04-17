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

export interface RetrievalStepItem {
  key: string
  label: string
  summary?: string
  details?: Record<string, any>
}

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
  presentation_mode?: PresentationMode
  execution_mode?: ExecutionMode
  use_rag?: boolean
  retrieval_steps?: RetrievalStepItem[]
  retrieval_params?: Record<string, any> | null
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
  chunk_index: number
  content: string
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
