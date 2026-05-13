/**
 * 文档知识库 API 模块
 *
 * 提供文档的上传、查询、更新、删除、版本管理和解析进度查询等接口。
 */
import { http } from "./http";
import type { DocumentRecord, DocParseResult, JobTask } from "@/types";

export type { DocumentRecord, DocParseResult } from "@/types";

/**
 * 文档列表查询参数
 */
export interface DocumentListParams {
  /** 分页偏移量（默认 0） */
  skip?: number;
  /** 分页大小（默认 50） */
  limit?: number;
  /** 关键词搜索（模糊匹配文件名和标题） */
  keyword?: string;
  /** 状态过滤（Processing / Completed / Failed） */
  status?: string;
  /** 是否启用过滤 */
  enabled?: boolean;
  /** 文档类型过滤 */
  document_type?: string;
  /** 标签过滤 */
  tag?: string;
}

/**
 * 文档更新请求体
 *
 * 所有字段均为可选，仅提交需要修改的字段。
 */
export interface DocumentRecordUpdatePayload {
  /** 新标题 */
  title?: string | null;
  /** 新标签列表 */
  tags?: string[];
  /** 新备注 */
  notes?: string | null;
  /** 启用/禁用 */
  enabled?: boolean;
  /** 文档类型 */
  document_type?: string | null;
  /** 自定义元数据 */
  custom_metadata?: Record<string, any>;
}

/**
 * 文档上传响应
 */
export interface UploadDocumentResponse {
  /** 创建的文档记录 */
  document: DocumentRecord;
  /** 后台解析任务（如有） */
  job?: JobTask | null;
  /** 响应提示消息 */
  message: string;
}

/**
 * 文档处理进度响应
 */
export interface DocumentProgressResponse {
  /** 文档记录 */
  document: DocumentRecord;
  /** 当前状态 */
  status: string;
  /** 当前处理阶段 */
  stage: string;
  /** 进度百分比（0-100） */
  progress_percent: number;
  /** 进度说明消息 */
  message?: string | null;
  /** 关联的后台任务 */
  job?: JobTask | null;
}

/**
 * 文档文本片段（API 局部类型，与 types/index.ts 中的 DocChunk 类似）
 */
export interface DocChunk {
  /** 所属文档 ID */
  doc_id: string;
  /** 分片索引 */
  chunk_index: number;
  /** 分片内容 */
  content: string;
  /** 检索相似度分数 */
  score: number;
  /** 所在页码 */
  page_number?: number | null;
  /** 来源类型 */
  source_type?: string | null;
}

/**
 * 文档内嵌图片
 */
export interface DocImage {
  /** 图片记录 ID */
  id: string;
  /** 图片文件路径 */
  file_path: string;
  /** MLLM 生成的图片描述 */
  generated_description?: string | null;
  /** 处理状态 */
  status: string;
}

/**
 * 上传文档文件
 * @param file 待上传的文件对象
 * @param onProgress 上传进度回调（百分比 0-100）
 * @returns 上传响应（包含文档记录和后台任务）
 */
export async function uploadDocument(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<UploadDocumentResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await http.post<UploadDocumentResponse>("/api/docs/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (!onProgress || !event.total) return;
      onProgress(Math.min(100, Math.round((event.loaded * 100) / event.total)));
    },
  });
  return data;
}

/**
 * 查询文档列表
 * @param params 查询参数（分页、关键词、状态、类型、标签等）
 * @returns 文档记录列表
 */
export async function listDocuments(params: DocumentListParams = {}): Promise<DocumentRecord[]> {
  const { data } = await http.get<DocumentRecord[]>("/api/docs/list", {
    params: {
      skip: params.skip ?? 0,
      limit: params.limit ?? 50,
      keyword: params.keyword,
      status: params.status,
      enabled: params.enabled,
      document_type: params.document_type,
      tag: params.tag,
    },
  });
  return data;
}

/**
 * 获取文档详情
 * @param docId 文档 ID
 * @returns 文档记录详情
 */
export async function getDocumentDetail(docId: string): Promise<DocumentRecord> {
  const { data } = await http.get<DocumentRecord>(`/api/docs/${docId}`);
  return data;
}

/**
 * 更新文档元数据
 * @param docId 文档 ID
 * @param payload 更新字段（部分更新）
 * @returns 更新后的文档记录
 */
export async function updateDocument(docId: string, payload: DocumentRecordUpdatePayload): Promise<DocumentRecord> {
  const { data } = await http.patch<DocumentRecord>(`/api/docs/${docId}`, payload);
  return data;
}

/**
 * 删除文档（需确认）
 * @param docId 文档 ID
 */
export async function deleteDocument(docId: string): Promise<void> {
  await http.delete(`/api/docs/${docId}`, { params: { confirm: true } });
}

/**
 * 重新处理文档
 * @param docId 文档 ID
 */
export async function reprocessDocument(docId: string): Promise<void> {
  await http.post(`/api/docs/${docId}/reprocess`);
}

/**
 * 获取文档处理进度
 * @param docId 文档 ID
 * @returns 处理进度详情
 */
export async function getDocumentProgress(docId: string): Promise<DocumentProgressResponse> {
  const { data } = await http.get<DocumentProgressResponse>(`/api/docs/${docId}/progress`);
  return data;
}

/**
 * 获取文档解析结果
 * @param docId 文档 ID
 * @returns 解析结果（包含文档元数据、分片列表和提取的图片）
 */
export async function getDocResult(docId: string): Promise<DocParseResult> {
  const { data } = await http.get<DocParseResult>(`/api/docs/${docId}/result`);
  return data;
}

/**
 * 查询文档版本历史
 * @param docId 文档 ID
 * @returns 该文档的所有版本记录列表
 */
export async function listDocumentVersions(docId: string): Promise<DocumentRecord[]> {
  const { data } = await http.get<DocumentRecord[]>(`/api/docs/${docId}/versions`);
  return data;
}

/**
 * 上传文档新版本
 * @param docId 文档 ID
 * @param file 新版本文件
 * @param onProgress 上传进度回调
 * @returns 上传响应
 */
export async function uploadDocumentVersion(
  docId: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<UploadDocumentResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await http.post<UploadDocumentResponse>(`/api/docs/${docId}/versions`, form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (!onProgress || !event.total) return;
      onProgress(Math.min(100, Math.round((event.loaded * 100) / event.total)));
    },
  });
  return data;
}
