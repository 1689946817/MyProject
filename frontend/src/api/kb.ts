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

/**
 * 图像记录接口
 * 
 * 表示数据库中的图像记录，包含元数据和生成的描述。
 */
export interface ImageRecord {
  id: string; // 图像唯一标识符
  file_path: string; // 图像文件路径
  upload_time: string; // 上传时间
  generated_description?: string | null; // 生成的图像描述
  status: string; // 处理状态（Processing、Completed、Failed）
  source_dataset?: string | null; // 图像来源数据集
}

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

