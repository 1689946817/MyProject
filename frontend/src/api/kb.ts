import { http } from "./http";

export interface ImageRecord {
  id: string;
  file_path: string;
  upload_time: string;
  generated_description?: string | null;
  status: string;
  source_dataset?: string | null;
}

export interface UploadImagesResponse {
  images: ImageRecord[];
}

export async function uploadImages(files: File[]): Promise<UploadImagesResponse> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("split", "custom");

  const { data } = await http.post<UploadImagesResponse>("/api/knowledge-base/upload", form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
}

