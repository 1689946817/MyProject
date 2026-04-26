import { http } from "./http";
import type { BatchImportResponse, HealthStatus, ImportBatch, JobTask, MetricsSummary } from "@/types";

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

function parseLatestWorkerHeartbeat(metricsText: string): string | null {
  const lines = metricsText.split(/\r?\n/);
  const target = lines.find((line) => line.startsWith("codex_worker_heartbeat_timestamp_seconds"));
  if (!target) return null;
  const rawValue = Number(target.trim().split(/\s+/).pop());
  if (Number.isNaN(rawValue) || rawValue <= 0) return null;
  return new Date(rawValue * 1000).toISOString();
}

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

export async function getJob(jobId: string): Promise<JobTask> {
  const { data } = await http.get<JobTask>(`/api/jobs/${jobId}`);
  return data;
}

export async function retryJob(jobId: string): Promise<JobTask> {
  const { data } = await http.post<JobTask>(`/api/jobs/${jobId}/retry`);
  return data;
}

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

export async function getImportBatch(batchId: string): Promise<ImportBatch> {
  const { data } = await http.get<ImportBatch>(`/api/imports/${batchId}`);
  return data;
}

export async function getLiveHealth(): Promise<HealthStatus> {
  const { data } = await http.get<HealthStatus>("/api/health/live");
  return data;
}

export async function getDependencyHealth(): Promise<HealthStatus> {
  const { data } = await http.get<HealthStatus>("/api/health/deps");
  return data;
}

export async function getReadyHealth(): Promise<HealthStatus> {
  const { data } = await http.get<HealthStatus>("/api/health/ready");
  return data;
}

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
