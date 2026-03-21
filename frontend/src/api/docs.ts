/**
 * 文档知识库 API 模块
 */
import { http } from "./http";

export interface DocumentRecord {
  id: string;
  file_name: string;
  file_path: string;
  upload_time: string;
  status: string;
  chunk_count: number;
  image_count: number;
}

export interface UploadDocumentResponse {
  document: DocumentRecord;
  message: string;
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

export interface DocParseResult {
  document: DocumentRecord;
  chunks: DocChunk[];
  images: DocImage[];
}

export async function uploadDocument(file: File): Promise<UploadDocumentResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await http.post<UploadDocumentResponse>("/api/docs/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function listDocuments(skip = 0, limit = 50): Promise<DocumentRecord[]> {
  const { data } = await http.get<DocumentRecord[]>("/api/docs/list", {
    params: { skip, limit },
  });
  return data;
}

export async function getDocResult(docId: string): Promise<DocParseResult> {
  const { data } = await http.get<DocParseResult>(`/api/docs/${docId}/result`);
  return data;
}
