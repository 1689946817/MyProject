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

/**
 * 上传图像响应接口
 * 
 * 表示批量上传图像的响应结果。
 */
export interface UploadImagesResponse {
  images: ImageRecord[]; // 上传的图像记录列表
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
export async function listImages(skip: number = 0, limit: number = 100): Promise<ImageRecord[]> {
  const { data } = await http.get<ImageRecord[]>('/api/knowledge-base/list', {
    params: { skip, limit }
  });
  return data;
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
