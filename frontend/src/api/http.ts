/**
 * HTTP 客户端配置
 *
 * 配置 Axios 实例，设置基础 URL 和超时时间，用于与后端 API 通信。
 * 所有 API 调用都通过此实例发起，确保一致的配置和错误处理。
 */
import axios from "axios";

/**
 * Axios 实例，配置了基础 URL 和超时时间
 * - baseURL: 后端 API 基础地址
 * - timeout: 请求超时时间（毫秒）
 */
export const http = axios.create({
  baseURL: "", // 浏览器端统一走 /api，由 Vite 代理到后端
  timeout: 60000 // 60秒超时
});
