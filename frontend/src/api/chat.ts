import { http } from "./http";
import type { SearchResultItem } from "./search";

export interface ChatResponse {
  answer: string;
  results: SearchResultItem[];
}

export async function ragChat(query: string, topK = 5, image?: File): Promise<ChatResponse> {
  const form = new FormData();
  form.append("query", query);
  form.append("top_k", String(topK));
  if (image) {
    form.append("image", image);
  }
  const { data } = await http.post<ChatResponse>("/api/rag/chat", form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
}

