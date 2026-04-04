/**
 * 搜索 API 模块
 * 
 * 封装与搜索相关的 API 调用，包括：
 * - 文本到图像搜索
 * - 图像到图像搜索
 * 
 * 提供类型定义和异步函数，方便前端组件调用。
 */
import { http } from "./http";
import type { SearchResultItem } from "@/types";

export type { SearchResultItem } from "@/types";

/**
 * 文本搜索响应接口
 * 
 * 表示文本搜索的响应结果。
 */
export interface TextSearchResponse {
  query: string; // 搜索查询文本
  results: SearchResultItem[]; // 搜索结果列表
}

/**
 * 图像搜索响应接口
 * 
 * 表示图像搜索的响应结果，包括生成的查询描述。
 */
export interface ImageSearchResponse {
  query_description: string; // 基于输入图像生成的查询描述
  results: SearchResultItem[]; // 搜索结果列表
}

/**
 * 文本到图像搜索
 * 
 * 根据文本查询检索相关图像。
 * 
 * @param query 搜索查询文本
 * @param topK 返回的结果数量，默认为 10
 * @returns 搜索结果，包含查询文本和相关图像列表
 */
export async function textToImageSearch(query: string, topK = 10): Promise<TextSearchResponse> {
  const { data } = await http.post<TextSearchResponse>('/api/search/text-to-image', {
    query,
    top_k: topK
  });
  return data;
}

/**
 * 图像到图像搜索
 * 
 * 根据输入图像检索相似图像。
 * 
 * @param file 上传的图像文件
 * @param topK 返回的结果数量，默认为 10
 * @returns 搜索结果，包含生成的查询描述和相似图像列表
 */
export async function imageToImageSearch(file: File, topK = 10): Promise<ImageSearchResponse> {
  const form = new FormData();
  // 添加文件到表单
  form.append('file', file);
  // 设置返回结果数量
  form.append('top_k', String(topK));
  
  const { data } = await http.post<ImageSearchResponse>('/api/search/image-to-image', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return data;
}
