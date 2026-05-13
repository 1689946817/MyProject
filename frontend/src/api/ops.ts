/**
 * 运维管理 API 模块
 *
 * 提供任务队列管理、批量导入、健康检查和系统指标等运维相关接口。
 */
import { http } from "./http";
import type { BatchImportResponse, HealthStatus, ImportBatch, JobTask, MetricsSummary } from "@/types";

/**
 * 从 Prometheus 格式文本中解析指定指标的计数值
 * @param metricsText Prometheus 原始指标文本
 * @param metricName 指标名称（如 "codex_job_tasks_total"）
 * @param labels 标签键值对过滤条件
 * @returns 匹配的计数值，未找到时返回 0
 */
function parsePrometheusCounter(metricsText: string, metricName: string, labels: Record<string, string> = {}): number {
  const lines = metricsText.split(/\r?\n/);
  const labelEntries = Object.entries(labels);
  for (const line of lines) {
    if (!line.startsWith(metricName)) continue;
    const matchesAllLabels = labelEntries.every(([key, value]) => line.includes(`${key}="${value}"`));
    if (!matchesAllLabels) continue;
    const rawValue = line.trim().split(/\s+/).pop();
    const parsed = Number(rawValue);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }
  return 0;
}

/**
 * 从 Prometheus 指标中解析最近一次 Worker 心跳时间
 * @param metricsText Prometheus 原始指标文本
 * @returns ISO 8601 时间字符串，无心跳数据时返回 null
 */
function parseLatestWorkerHeartbeat(metricsText: string): string | null {
  const lines = metricsText.split(/\r?\n/);
  const target = lines.find((line) => line.startsWith("codex_worker_heartbeat_timestamp_seconds"));
  if (!target) return null;
  const rawValue = Number(target.trim().split(/\s+/).pop());
  if (Number.isNaN(rawValue) || rawValue <= 0) return null;
  return new Date(rawValue * 1000).toISOString();
}

/**
 * 查询任务列表
 * @param params 筛选参数：status=状态过滤, job_type=类型过滤, limit=数量限制, offset=偏移量
 * @returns 任务列表
 */
export async function listJobs(params: {
  status?: string;
  job_type?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<JobTask[]> {
  const { data } = await http.get<JobTask[]>("/api/jobs", {
    params: {
      status: params.status,
      job_type: params.job_type,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    },
  });
  return data;
}

/**
 * 获取单个任务详情
 * @param jobId 任务 ID
 * @returns 任务详情
 */
export async function getJob(jobId: string): Promise<JobTask> {
  const { data } = await http.get<JobTask>(`/api/jobs/${jobId}`);
  return data;
}

/**
 * 重试失败的任务
 * @param jobId 任务 ID
 * @returns 重试后的任务详情
 */
export async function retryJob(jobId: string): Promise<JobTask> {
  const { data } = await http.post<JobTask>(`/api/jobs/${jobId}/retry`);
  return data;
}

/**
 * 批量导入文档
 * @param files 待上传的文件列表
 * @returns 批量导入响应（包含批次信息、任务列表和文档记录）
 */
export async function batchImportDocuments(files: File[]): Promise<BatchImportResponse> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("source_type", "document");
  const { data } = await http.post<BatchImportResponse>("/api/imports/batch", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });
  return data;
}

/**
 * 获取批量导入批次详情
 * @param batchId 批次 ID
 * @returns 批次详情
 */
export async function getImportBatch(batchId: string): Promise<ImportBatch> {
  const { data } = await http.get<ImportBatch>(`/api/imports/${batchId}`);
  return data;
}

/**
 * 获取存活检查（liveness probe）
 * @returns 健康状态
 */
export async function getLiveHealth(): Promise<HealthStatus> {
  const { data } = await http.get<HealthStatus>("/api/health/live");
  return data;
}

/**
 * 获取依赖项健康检查
 * @returns 各依赖项（数据库、向量库等）的健康状态
 */
export async function getDependencyHealth(): Promise<HealthStatus> {
  const { data } = await http.get<HealthStatus>("/api/health/deps");
  return data;
}

/**
 * 获取就绪检查（readiness probe）
 * @returns 服务是否可接受请求的健康状态
 */
export async function getReadyHealth(): Promise<HealthStatus> {
  const { data } = await http.get<HealthStatus>("/api/health/ready");
  return data;
}

/**
 * 获取系统指标汇总
 *
 * 拉取 Prometheus 格式指标并解析为前端可用的结构化数据。
 * @returns 包含任务统计和 Worker 状态的指标汇总
 */
export async function getMetricsSummary(): Promise<MetricsSummary> {
  const { data } = await http.get<string>("/api/metrics", {
    responseType: "text",
  });
  return {
    raw: data,
    totalJobs:
      parsePrometheusCounter(data, "codex_job_tasks_total", { status: "queued" }) +
      parsePrometheusCounter(data, "codex_job_tasks_total", { status: "running" }) +
      parsePrometheusCounter(data, "codex_job_tasks_total", { status: "failed" }) +
      parsePrometheusCounter(data, "codex_job_tasks_total", { status: "completed" }),
    queuedJobs: parsePrometheusCounter(data, "codex_job_tasks_total", { status: "queued" }),
    runningJobs: parsePrometheusCounter(data, "codex_job_tasks_total", { status: "running" }),
    failedJobs: parsePrometheusCounter(data, "codex_job_tasks_total", { status: "failed" }),
    completedJobs: parsePrometheusCounter(data, "codex_job_tasks_total", { status: "completed" }),
    activeWorkers: 0,
    latestWorkerHeartbeat: parseLatestWorkerHeartbeat(data),
  };
}
