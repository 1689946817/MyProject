import { http } from "./http";

export interface SearchResultItem {
  id: string;
  file_path?: string;
  description?: string;
  score: number;
}

export interface TextSearchResponse {
  query: string;
  results: SearchResultItem[];
}

export interface ImageSearchResponse {
  query_description: string;
  results: SearchResultItem[];
}

export async function textToImageSearch(query: string, topK = 10): Promise<TextSearchResponse> {
  const { data } = await http.post<TextSearchResponse>("/api/search/text-to-image", {
    query,
    top_k: topK
  });
  return data;
}

export async function imageToImageSearch(file: File, topK = 10): Promise<ImageSearchResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("top_k", String(topK));
  const { data } = await http.post<ImageSearchResponse>("/api/search/image-to-image", form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
}

