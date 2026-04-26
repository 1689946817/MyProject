/**
 * 知识库 API 模块
 * 
 * 封装与知识库相关的 API 调用，包括：
 * - 获取图片记录列表
 * - 上传图片并生成描述
 * 
 * 提供类型定义和异步函数，方便前端组件调用。
 */
import { http } from "./http";
import type { ImageRecord } from "@/types";

export type { ImageRecord } from "@/types";

export interface ImageListParams {
  skip?: number;
  limit?: number;
  keyword?: string;
  status?: string;
  enabled?: boolean;
  source_dataset?: string;
  tag?: string;
}

export interface ImageRecordUpdatePayload {
  title?: string | null;
  tags?: string[];
  notes?: string | null;
  enabled?: boolean;
  source_dataset?: string | null;
  custom_metadata?: Record<string, any>;
}

/**
 * 上传图像响应接口
 * 
 * 表示批量上传图像的响应结果。
 */
export interface UploadImagesResponse {
  images: ImageRecord[]; // 上传的图像记录列表
  deduplicated_count?: number;
}

/**
 * 获取图片记录列表
 * 
 * 按上传时间倒序获取图片记录，支持分页。
 * 
 * @param skip 跳过的记录数，默认为 0
 * @param limit 返回的最大记录数，默认为 100
 * @returns 图片记录列表
 */
export async function listImages(params: ImageListParams = {}): Promise<ImageRecord[]> {
  const { data } = await http.get<ImageRecord[]>('/api/knowledge-base/list', {
    params: {
      skip: params.skip ?? 0,
      limit: params.limit ?? 100,
      keyword: params.keyword,
      status: params.status,
      enabled: params.enabled,
      source_dataset: params.source_dataset,
      tag: params.tag,
    }
  });
  return data;
}

export async function getImageDetail(id: string): Promise<ImageRecord> {
  const { data } = await http.get<ImageRecord>(`/api/knowledge-base/${id}`);
  return data;
}

export async function updateImage(id: string, payload: ImageRecordUpdatePayload): Promise<ImageRecord> {
  const { data } = await http.patch<ImageRecord>(`/api/knowledge-base/${id}`, payload);
  return data;
}

export async function deleteImage(id: string): Promise<void> {
  await http.delete(`/api/knowledge-base/${id}`, { params: { confirm: true } });
}

export async function reprocessImage(id: string): Promise<void> {
  await http.post(`/api/knowledge-base/${id}/reprocess`);
}

/**
 * 上传图片并生成描述
 * 
 * 批量上传图片，生成结构化描述，并将描述写入向量库。
 * 
 * @param files 要上传的文件列表
 * @returns 上传结果，包含处理后的图片记录列表
 */
export async function uploadImages(files: File[]): Promise<UploadImagesResponse> {
  const form = new FormData();
  // 添加文件到表单
  files.forEach((file) => form.append('files', file));
  // 设置数据集分割类型为 custom
  form.append('split', 'custom');

  const { data } = await http.post<UploadImagesResponse>('/api/knowledge-base/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return data;
}

export async function listImageVersions(id: string): Promise<ImageRecord[]> {
  const { data } = await http.get<ImageRecord[]>(`/api/knowledge-base/${id}/versions`);
  return data;
}

export async function uploadImageVersion(id: string, file: File): Promise<UploadImagesResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await http.post<UploadImagesResponse>(`/api/knowledge-base/${id}/versions`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
