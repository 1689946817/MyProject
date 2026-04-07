/**
 * 文档知识库 API 模块
 */
import { http } from "./http";
import type { DocumentRecord, DocParseResult } from "@/types";

export type { DocumentRecord, DocParseResult } from "@/types";

export interface DocumentListParams {
  skip?: number;
  limit?: number;
  keyword?: string;
  status?: string;
  enabled?: boolean;
  document_type?: string;
  tag?: string;
}

export interface DocumentRecordUpdatePayload {
  title?: string | null;
  tags?: string[];
  notes?: string | null;
  enabled?: boolean;
  document_type?: string | null;
  custom_metadata?: Record<string, any>;
}

export interface UploadDocumentResponse {
  document: DocumentRecord;
  message: string;
}

export interface DocumentProgressResponse {
  document: DocumentRecord;
  status: string;
  stage: string;
  progress_percent: number;
  message?: string | null;
}

export interface DocChunk {
  doc_id: string;
  chunk_index: number;
  content: string;
  score: number;
}

export interface DocImage {
  id: string;
  file_path: string;
  generated_description?: string | null;
  status: string;
}

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

export async function getDocumentDetail(docId: string): Promise<DocumentRecord> {
  const { data } = await http.get<DocumentRecord>(`/api/docs/${docId}`);
  return data;
}

export async function updateDocument(docId: string, payload: DocumentRecordUpdatePayload): Promise<DocumentRecord> {
  const { data } = await http.patch<DocumentRecord>(`/api/docs/${docId}`, payload);
  return data;
}

export async function deleteDocument(docId: string): Promise<void> {
  await http.delete(`/api/docs/${docId}`, { params: { confirm: true } });
}

export async function reprocessDocument(docId: string): Promise<void> {
  await http.post(`/api/docs/${docId}/reprocess`);
}

export async function getDocumentProgress(docId: string): Promise<DocumentProgressResponse> {
  const { data } = await http.get<DocumentProgressResponse>(`/api/docs/${docId}/progress`);
  return data;
}

export async function getDocResult(docId: string): Promise<DocParseResult> {
  const { data } = await http.get<DocParseResult>(`/api/docs/${docId}/result`);
  return data;
}
