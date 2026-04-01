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
import type { SearchResultItem } from "./search";

/**
 * 聊天响应接口
 *
 * 表示 RAG 聊天的响应结果，包括生成的回答和检索到的相关图像。
 */
export interface ChatResponse {
  answer: string; // 生成的回答
  results: SearchResultItem[]; // 检索到的相关图像列表
}

/**
 * 聊天会话接口
 */
export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

/**
 * 聊天消息接口（对齐后端 ChatMessageOut）
 */
export interface ChatMessage {
  id: number;
  session_id: string;
  role: string;
  content: string;
  has_image: boolean;
  sources: ChatSourceItem[];
  retrieval_params: Record<string, any> | null;
  created_at: string;
}

/**
 * 来源项接口（对齐后端 ChatSourceItem）
 */
export interface ChatSourceItem {
  source_type: string;
  source_id: string;
  title?: string;
  file_path?: string;
  content?: string;
  score?: number;
  metadata: Record<string, any>;
}

/**
 * RAG 聊天
 *
 * 基于用户查询（文本或图像）检索相关图像，然后生成回答。
 *
 * @param query 用户问题
 * @param topK 返回的检索结果数量，默认为 5
 * @param image 可选的上传图像，用于图像检索
 * @param sessionId 会话 ID
 * @returns 聊天结果，包含生成的回答和检索到的相关图像列表
 */
export async function ragChat(query: string, topK = 5, image?: File, sessionId?: string): Promise<ChatResponse> {
  const form = new FormData();
  form.append('query', query);
  form.append('top_k', String(topK));
  if (image) {
    form.append('image', image);
  }
  if (sessionId) {
    form.append('session_id', sessionId);
  }

  const { data } = await http.post<ChatResponse>('/api/rag/chat', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return data;
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
  const { data } = await http.get<ChatMessage[]>(`/api/chat/sessions/${id}`);
  return data;
}
