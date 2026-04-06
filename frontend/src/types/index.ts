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
}

/**
 * 搜索结果项
 */
export interface SearchResultItem {
  id: string
  file_path?: string
  description?: string
  score: number
}

export interface ChatSourceItem {
  source_type: string
  source_id: string
  title?: string
  file_path?: string
  content?: string
  score?: number
  metadata?: Record<string, any>
}

export type PresentationMode = "direct_answer" | "rag_answer" | "image_only" | "image_plus_answer"
export type ExecutionMode =
  | "direct_llm"
  | "multimodal_rag"
  | "image_similarity"
  | "image_grounded_answer"
  | "uploaded_image_qa"

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
  sources?: ChatSourceItem[]
  presentation_mode?: PresentationMode
  execution_mode?: ExecutionMode
  use_rag?: boolean
  retrieval_params?: Record<string, any> | null
  created_at: string
}

/**
 * 文档记录
 */
export interface DocumentRecord {
  id: string
  file_name: string
  file_path?: string
  upload_time: string
  status: 'Processing' | 'Completed' | 'Failed'
  chunk_count: number
  image_count: number
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
