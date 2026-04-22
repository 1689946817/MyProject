/**
 * 聊天 API 模块
 *
 * 封装与 RAG 聊天相关的 API 调用，包括：
 * - RAG 聊天接口：基于用户查询（文本或图像）生成回答
 * - 会话管理：创建、获取、重命名、删除会话
 *
 * 提供类型定义和异步函数，方便前端组件调用。
 */
import { http } from "./http";
import type {
  ChatMessage,
  RetrievalStepItem,
  ChatSession,
  ChatSourceItem,
  ExecutionMode,
  PresentationMode,
  SearchResultItem,
  TimingSummary,
} from "@/types";

export type { ChatMessage, ChatSession } from "@/types";

const CHAT_REQUEST_TIMEOUT_MS = 120000;

/**
 * 聊天响应接口
 *
 * 表示 RAG 聊天的响应结果，包括生成的回答和检索到的相关图像。
 */
export interface ChatResponse {
  answer: string; // 生成的回答
  results: SearchResultItem[]; // 检索到的相关图像列表
  sources: ChatSourceItem[];
  session_id: string;
  presentation_mode: PresentationMode;
  execution_mode: ExecutionMode;
  use_rag: boolean;
  has_uploaded_image: boolean;
  retrieval_steps: RetrievalStepItem[];
  timings?: TimingSummary | null;
}

/**
 * 会话详情接口（对齐后端 ChatSessionDetailResponse）
 */
export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}

/**
 * 获取会话列表
 *
 * @returns 会话列表
 */
export async function getSessions(): Promise<ChatSession[]> {
  const { data } = await http.get<ChatSession[]>('/api/chat/sessions');
  return data;
}

/**
 * 创建新会话
 *
 * @param title 可选的会话标题
 * @returns 创建的会话
 */
export async function createSession(title?: string): Promise<ChatSession> {
  const { data } = await http.post<ChatSession>('/api/chat/sessions', { title });
  return data;
}

/**
 * 重命名会话
 *
 * @param id 会话 ID
 * @param title 新标题
 */
export async function renameSession(id: string, title: string): Promise<void> {
  await http.patch(`/api/chat/sessions/${id}`, { title });
}

/**
 * 删除会话
 *
 * @param id 会话 ID
 */
export async function deleteSession(id: string): Promise<void> {
  await http.delete(`/api/chat/sessions/${id}`);
}

/**
 * 获取会话消息
 *
 * @param id 会话 ID
 * @returns 消息列表
 */
export async function getSessionMessages(id: string): Promise<ChatMessage[]> {
  const { data } = await http.get<ChatSessionDetail>(`/api/chat/sessions/${id}`);
  return data.messages;
}

/**
 * 非流式 RAG 聊天
 *
 * @param params 聊天参数
 * @returns 聊天响应
 */
export async function ragChat(params: {
  query: string;
  sessionId?: string;
  topK?: number;
  enableScoreFilter?: boolean;
  minRelevanceScore?: number;
  executionHint?: string;
  sourceScope?: {
    doc_ids?: string[];
    image_ids?: string[];
  } | null;
  image?: File | null;
}): Promise<ChatResponse> {
  const form = new FormData();
  form.append("query", params.query);
  if (params.topK !== undefined) {
    form.append("top_k", String(params.topK));
  }
  if (params.enableScoreFilter !== undefined) {
    form.append("enable_score_filter", String(params.enableScoreFilter));
  }
  if (params.minRelevanceScore !== undefined) {
    form.append("min_relevance_score", String(params.minRelevanceScore));
  }
  if (params.executionHint) {
    form.append("execution_hint", params.executionHint);
  }
  if (params.sourceScope && ((params.sourceScope.doc_ids?.length || 0) > 0 || (params.sourceScope.image_ids?.length || 0) > 0)) {
    form.append("source_scope_json", JSON.stringify(params.sourceScope));
  }
  if (params.sessionId) {
    form.append("session_id", params.sessionId);
  }
  if (params.image) {
    form.append("image", params.image);
  }

  const { data } = await http.post<ChatResponse>("/api/rag/chat", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: CHAT_REQUEST_TIMEOUT_MS,
  });
  return data;
}
