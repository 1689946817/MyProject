<!-- 运维管理页面：支持图片/文档批量导入、后台任务队列监控、系统健康状态查看 -->
<template>
  <div class="ops-page">
    <div class="page-intro">
      <div class="page-intro-main">
        <h1 class="page-title">{{ t("ops.title") }}</h1>
        <p class="page-subtitle">{{ t("ops.subtitle") }}</p>
      </div>
      <div class="page-intro-actions">
        <el-button @click="refreshAll">
          <i class="i-ep-refresh mr-1"></i>
          {{ t("ops.refreshAll") }}
        </el-button>
      </div>
    </div>

    <el-tabs v-model="importTab" class="ops-tabs">
      <el-tab-pane :label="t('ops.imageImportTitle')" name="images">
        <el-card class="glass-card upload-entry-card">
          <div class="upload-entry-row">
            <UploadZone
              v-model:files="imageImportFiles"
              :text="t('ops.imageImportArea')"
              :hint="t('ops.imageImportDesc')"
              :accept="'image/*'"
              :multiple="true"
              compact
            />
            <el-button
              type="primary"
              class="upload-btn"
              :loading="imageImporting"
              :disabled="imageImportFiles.length === 0"
              @click="submitImageImport"
            >
              <i class="i-ep-upload mr-2"></i>
              {{ t("ops.startImport") }}
            </el-button>
          </div>
          <el-alert
            v-if="imageImportSummary"
            :title="imageImportSummary"
            type="success"
            show-icon
            :closable="false"
            class="result-alert"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane :label="t('ops.docImportTitle')" name="documents">
        <el-card class="glass-card upload-entry-card">
          <div class="upload-entry-row">
            <UploadZone
              v-model:files="documentImportFiles"
              :text="t('ops.docImportArea')"
              :hint="t('ops.docImportDesc')"
              :accept="'.pdf'"
              :multiple="true"
              compact
            />
            <el-button
              type="primary"
              class="upload-btn"
              :loading="documentImporting"
              :disabled="documentImportFiles.length === 0"
              @click="submitDocumentImport"
            >
              <i class="i-ep-upload mr-2"></i>
              {{ t("ops.startImport") }}
            </el-button>
          </div>
          <el-alert
            v-if="documentImportMessage"
            :title="documentImportMessage"
            type="success"
            show-icon
            :closable="false"
            class="result-alert"
          />
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <div class="ops-grid">
      <el-card class="glass-card">
        <template #header>
          <div class="card-header">
            <span>{{ t("ops.jobsTitle") }}</span>
            <div class="header-actions">
              <el-select v-model="jobStatusFilter" clearable size="small" class="job-filter" @change="loadJobs">
                <el-option :label="t('ops.filterQueued')" value="queued" />
                <el-option :label="t('ops.filterRunning')" value="running" />
                <el-option :label="t('ops.filterCompleted')" value="completed" />
                <el-option :label="t('ops.filterFailed')" value="failed" />
              </el-select>
              <el-button size="small" @click="loadJobs">{{ t("docs.refresh") }}</el-button>
            </div>
          </div>
        </template>

        <div v-if="activeBatchId" class="batch-banner">
          <span>{{ t("ops.activeBatch", { id: activeBatchId }) }}</span>
          <el-button text @click="clearBatchFilter">{{ t("ops.clearBatch") }}</el-button>
        </div>

        <el-table v-loading="jobsLoading" :data="filteredJobs" stripe class="dark-table">
          <el-table-column prop="job_type" :label="t('ops.jobType')" min-width="120" />
          <el-table-column prop="status" :label="t('docs.status')" width="120">
            <template #default="{ row }">
              <el-tag :type="jobStatusType(row.status)">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('ops.relatedTarget')" min-width="150">
            <template #default="{ row }">
              {{ row.related_doc_id || row.related_batch_id || "-" }}
            </template>
          </el-table-column>
          <el-table-column :label="t('ops.retryCount')" width="100" align="center">
            <template #default="{ row }">{{ row.retry_count }} / {{ row.max_retries }}</template>
          </el-table-column>
          <el-table-column :label="t('docs.uploadTime')" width="180">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column :label="t('docs.action')" width="120" align="center">
            <template #default="{ row }">
              <el-button
                size="small"
                :disabled="!canRetryJob(row)"
                @click="handleRetryJob(row.id)"
              >
                {{ t("ops.retryJob") }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card class="glass-card">
        <template #header>
          <div class="card-header">
            <span>{{ t("ops.healthTitle") }}</span>
            <el-button size="small" @click="loadHealth">{{ t("docs.refresh") }}</el-button>
          </div>
        </template>

        <div class="health-grid">
          <div class="metric-card">
            <span class="metric-label">{{ t("ops.totalJobs") }}</span>
            <strong>{{ metrics.totalJobs }}</strong>
          </div>
          <div class="metric-card">
            <span class="metric-label">{{ t("ops.queuedJobs") }}</span>
            <strong>{{ metrics.queuedJobs }}</strong>
          </div>
          <div class="metric-card">
            <span class="metric-label">{{ t("ops.runningJobs") }}</span>
            <strong>{{ metrics.runningJobs }}</strong>
          </div>
          <div class="metric-card">
            <span class="metric-label">{{ t("ops.failedJobs") }}</span>
            <strong>{{ metrics.failedJobs }}</strong>
          </div>
          <div class="metric-card">
            <span class="metric-label">{{ t("ops.activeWorkers") }}</span>
            <strong>{{ workerCount }}</strong>
          </div>
          <div class="metric-card">
            <span class="metric-label">{{ t("ops.lastHeartbeat") }}</span>
            <strong>{{ latestHeartbeatLabel }}</strong>
          </div>
        </div>

        <div class="health-status-list">
          <div class="health-row">
            <span>{{ t("ops.liveCheck") }}</span>
            <el-tag :type="healthTagType(liveHealth?.status)">{{ liveHealth?.status || "-" }}</el-tag>
          </div>
          <div class="health-row">
            <span>{{ t("ops.depsCheck") }}</span>
            <el-tag :type="healthTagType(depsHealth?.status)">{{ depsHealth?.status || "-" }}</el-tag>
          </div>
          <div class="health-row">
            <span>{{ t("ops.readyCheck") }}</span>
            <el-tag :type="healthTagType(readyHealth?.status)">{{ readyHealth?.status || "-" }}</el-tag>
          </div>
        </div>

        <el-collapse class="metrics-collapse">
          <el-collapse-item :title="t('ops.rawMetrics')" name="raw-metrics">
            <pre class="metrics-raw">{{ metrics.raw || t("ops.noMetrics") }}</pre>
          </el-collapse-item>
        </el-collapse>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
// ---- 导入 ----
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import UploadZone from "@/components/UploadZone.vue";
import { uploadImages } from "@/api/kb";
import {
  batchImportDocuments,
  getDependencyHealth,
  getLiveHealth,
  getMetricsSummary,
  getReadyHealth,
  listJobs,
  retryJob,
} from "@/api/ops";
import type { HealthStatus, JobTask, MetricsSummary } from "@/types";

const { t } = useI18n();

// ---- 批量导入状态 ----
const importTab = ref<"images" | "documents">("documents");
const imageImportFiles = ref<File[]>([]);
const documentImportFiles = ref<File[]>([]);
const imageImporting = ref(false);
const documentImporting = ref(false);
const imageImportSummary = ref("");
const documentImportMessage = ref("");
const activeBatchId = ref("");

// ---- 后台任务队列状态 ----
const jobsLoading = ref(false);
const jobs = ref<JobTask[]>([]);
const jobStatusFilter = ref<string>("");

// ---- 系统健康状态 ----
const liveHealth = ref<HealthStatus | null>(null);
const depsHealth = ref<HealthStatus | null>(null);
const readyHealth = ref<HealthStatus | null>(null);
const metrics = ref<MetricsSummary>({
  raw: "",
  totalJobs: 0,
  queuedJobs: 0,
  runningJobs: 0,
  failedJobs: 0,
  completedJobs: 0,
  activeWorkers: 0,
  latestWorkerHeartbeat: null,
});

// ---- 计算属性 ----

/** 根据当前活跃批次 ID 过滤任务列表 */
const filteredJobs = computed(() => {
  let list = jobs.value;
  if (activeBatchId.value) {
    list = list.filter((job) => job.related_batch_id === activeBatchId.value);
  }
  return list;
});

/** 活跃 Worker 数量（优先取依赖健康检查数据，回退到指标数据） */
const workerCount = computed(() => {
  const fromDeps = Number(depsHealth.value?.checks?.workers?.active_workers ?? 0);
  return fromDeps || metrics.value.activeWorkers;
});

/** 最近一次 Worker 心跳的时间显示文本 */
const latestHeartbeatLabel = computed(() => {
  if (!metrics.value.latestWorkerHeartbeat) {
    return t("ops.unknownHeartbeat");
  }
  return formatDateTime(metrics.value.latestWorkerHeartbeat);
});

// ---- 工具函数 ----

/** 将日期时间字符串格式化为本地显示格式 */
function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

/** 将健康检查状态映射为 Element Plus Tag 类型 */
function healthTagType(status?: string): "success" | "warning" | "danger" | "info" {
  if (status === "ok") return "success";
  if (status === "degraded") return "warning";
  if (status === "error") return "danger";
  return "info";
}

/** 将任务状态映射为 Element Plus Tag 类型 */
function jobStatusType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "running") return "warning";
  return "info";
}

/** 判断任务是否允许重试（仅 failed 和 completed 状态可重试） */
function canRetryJob(job: JobTask): boolean {
  return job.status === "failed" || job.status === "completed";
}

/** 清除批次过滤，显示全部任务 */
function clearBatchFilter() {
  activeBatchId.value = "";
}

// ---- 数据加载方法 ----

/** 加载后台任务列表，支持按状态过滤 */
async function loadJobs() {
  try {
    jobsLoading.value = true;
    jobs.value = await listJobs({
      status: jobStatusFilter.value || undefined,
      limit: 100,
    });
  } catch (error) {
    console.error("加载任务列表失败:", error);
    ElMessage.error(t("ops.loadJobsFailed"));
  } finally {
    jobsLoading.value = false;
  }
}

/** 并行加载系统健康检查（存活/依赖/就绪）和指标摘要 */
async function loadHealth() {
  try {
    const [live, deps, ready, metricsData] = await Promise.all([
      getLiveHealth(),
      getDependencyHealth(),
      getReadyHealth(),
      getMetricsSummary(),
    ]);
    liveHealth.value = live;
    depsHealth.value = deps;
    readyHealth.value = ready;
    metrics.value = metricsData;
  } catch (error) {
    console.error("加载健康状态失败:", error);
    ElMessage.error(t("ops.loadHealthFailed"));
  }
}

/** 刷新所有数据（任务列表 + 健康状态） */
async function refreshAll() {
  await Promise.all([loadJobs(), loadHealth()]);
}

// ---- 批量导入与任务操作 ----

/** 批量导入图片到知识库 */
async function submitImageImport() {
  if (imageImportFiles.value.length === 0) return;
  try {
    imageImporting.value = true;
    const response = await uploadImages(imageImportFiles.value);
    imageImportSummary.value = t("ops.imageImportSummary", {
      count: response.images.length,
      deduplicated: response.deduplicated_count ?? 0,
    });
    imageImportFiles.value = [];
  } catch (error) {
    console.error("批量导入图片失败:", error);
    ElMessage.error(t("ops.importFailed"));
  } finally {
    imageImporting.value = false;
  }
}

/** 批量导入文档到知识库，创建后台任务批次并刷新任务和健康数据 */
async function submitDocumentImport() {
  if (documentImportFiles.value.length === 0) return;
  try {
    documentImporting.value = true;
    const response = await batchImportDocuments(documentImportFiles.value);
    activeBatchId.value = response.batch.id;
    documentImportMessage.value = t("ops.docImportSummary", {
      batchId: response.batch.id,
      count: response.jobs.length,
    });
    documentImportFiles.value = [];
    await loadJobs();
    await loadHealth();
  } catch (error) {
    console.error("批量导入文档失败:", error);
    ElMessage.error(t("ops.importFailed"));
  } finally {
    documentImporting.value = false;
  }
}

/** 重试指定任务，刷新任务列表和健康状态 */
async function handleRetryJob(jobId: string) {
  try {
    await retryJob(jobId);
    ElMessage.success(t("ops.retrySuccess"));
    await loadJobs();
    await loadHealth();
  } catch (error) {
    console.error("重试任务失败:", error);
    ElMessage.error(t("ops.retryFailed"));
  }
}

// ---- 生命周期 ----

onMounted(async () => {
  await refreshAll();
});
</script>

<style scoped>
.ops-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.page-intro-actions,
.card-header,
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: space-between;
}

.ops-tabs :deep(.el-tabs__nav-wrap::after) {
  background: var(--border-color);
}

.upload-entry-card :deep(.el-card__body) {
  padding: 14px 18px;
}

.upload-entry-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
}

.upload-btn {
  min-width: 180px;
  min-height: 38px;
  padding: 0 18px;
  margin-top: 0;
  border-radius: 12px;
}

.result-alert {
  margin-top: 16px;
}

.ops-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 18px;
}

.job-filter {
  width: 130px;
}

.batch-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--border-color);
}

.health-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--border-color);
}

.metric-card strong {
  font-size: 24px;
  color: var(--text-primary);
}

@media (max-width: 960px) {
  .upload-entry-row {
    grid-template-columns: 1fr;
  }

  .upload-btn {
    width: 100%;
  }
}

.metric-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.health-status-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 8px;
}

.health-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.metrics-collapse {
  margin-top: 12px;
}

.metrics-raw {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  padding: 12px;
  border-radius: 14px;
  background: var(--bg-tertiary);
  font-size: 12px;
  line-height: 1.5;
}

.dark-table {
  --el-table-bg-color: var(--bg-secondary);
  --el-table-tr-bg-color: var(--bg-secondary);
  --el-table-header-bg-color: var(--bg-tertiary);
}

@media (max-width: 1100px) {
  .ops-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .health-grid {
    grid-template-columns: 1fr;
  }
}
</style>
