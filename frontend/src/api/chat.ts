/**
 * 聊天 API 模块
 * 
 * 封装与 RAG 聊天相关的 API 调用，包括：
 * - RAG 聊天接口：基于用户查询（文本或图像）生成回答
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
 * RAG 聊天
 * 
 * 基于用户查询（文本或图像）检索相关图像，然后生成回答。
 * 
 * @param query 用户问题
 * @param topK 返回的检索结果数量，默认为 5
 * @param image 可选的上传图像，用于图像检索
 * @returns 聊天结果，包含生成的回答和检索到的相关图像列表
 */
export async function ragChat(query: string, topK = 5, image?: File): Promise<ChatResponse> {
  const form = new FormData();
  // 添加查询文本
  form.append('query', query);
  // 设置返回结果数量
  form.append('top_k', String(topK));
  // 如果提供了图像，添加到表单
  if (image) {
    form.append('image', image);
  }
  
  const { data } = await http.post<ChatResponse>('/api/rag/chat', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return data;
}

