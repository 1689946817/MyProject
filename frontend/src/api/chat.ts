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
import type { ChatMessage, ChatSession } from "@/types";

export type { ChatMessage, ChatSession } from "@/types";

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
