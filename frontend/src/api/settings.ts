/**
 * 系统设置 API 模块
 *
 * 提供系统配置的查询和更新接口，用于管理后端运行时参数。
 */
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

/**
 * 获取系统配置
 * @returns 包含分组、配置项列表和重启状态的完整配置数据
 */
export async function getSystemConfig(): Promise<ConfigResponse> {
  const { data } = await http.get<ConfigResponse>("/api/admin/config");
  return data;
}

/**
 * 更新系统配置
 * @param payload 待更新的配置键值对
 * @returns 更新结果：success=是否成功, message=提示消息, restart_required=是否需要重启
 */
export async function updateSystemConfig(payload: ConfigUpdatePayload): Promise<{
  success: boolean
  message: string
  restart_required: boolean
}> {
  const { data } = await http.put("/api/admin/config", payload);
  return data;
}
