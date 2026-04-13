import { http } from "./http";
import type {
  ConfigResponse,
  ConfigUpdatePayload,
} from "@/types";

export type {
  ConfigGroup,
  ConfigItem,
  ConfigOption,
  ConfigResponse,
  ConfigUpdatePayload,
  ConfigValidationError,
} from "@/types";

export async function getSystemConfig(): Promise<ConfigResponse> {
  const { data } = await http.get<ConfigResponse>("/api/admin/config");
  return data;
}

export async function updateSystemConfig(payload: ConfigUpdatePayload): Promise<{
  success: boolean
  message: string
  restart_required: boolean
}> {
  const { data } = await http.put("/api/admin/config", payload);
  return data;
}
