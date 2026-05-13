<!-- 文档知识库管理页面：支持 PDF 上传、解析结果查看（文本片段/提取图片）、版本管理和文档编辑 -->
<template>
  <div class="doc-kb">
    <div class="page-intro">
      <div class="page-intro-main">
        <h1 class="page-title">{{ t("docs.title") }}</h1>
        <p class="page-subtitle">{{ t("docs.subtitle") }}</p>
      </div>
    </div>
    <el-card class="glass-card upload-entry-card">
      <div class="upload-entry-row">
        <UploadZone
          v-model:files="selectedFiles"
          :text="t('docs.uploadArea')"
          :hint="t('docs.uploadTip')"
          :accept="'.pdf'"
          :multiple="false"
          compact
        />
        <el-button
          type="primary"
          class="upload-btn"
          :loading="uploading"
          :disabled="!selectedFile"
          @click="doUpload"
        >
          <i class="i-ep-upload mr-2"></i>
          {{ t("docs.uploadBtn") }}
        </el-button>
      </div>
      <div v-if="showProgressPanel" class="upload-progress-panel">
        <div class="progress-header">
          <span>{{ progressTitle }}</span>
          <span>{{ progressPercent }}%</span>
        </div>
        <el-progress :percentage="progressPercent" :status="progressStatus" />
        <p class="progress-message">{{ progressMessage }}</p>
      </div>
      <el-alert
        v-if="uploadMsg"
        :title="uploadMsg"
        :type="uploadSuccess ? 'success' : 'error'"
        show-icon
        style="margin-top: 12px"
        :closable="false"
      />
    </el-card>

    <el-card class="glass-card" style="margin-top: 24px">
      <template #header>
        <div class="card-header">
          <span>{{ t("docs.uploadedDocs") }}</span>
          <el-button size="small" @click="loadDocList">
            <i class="i-ep-refresh mr-1"></i>
            {{ t("docs.refresh") }}
          </el-button>
        </div>
      </template>

      <div class="filter-bar">
        <el-input v-model="filters.keyword" :placeholder="t('docs.searchPlaceholder')" clearable @keyup.enter="loadDocList" />
        <el-select v-model="filters.status" clearable :placeholder="t('docs.status')" @change="loadDocList">
          <el-option label="Processing" value="Processing" />
          <el-option label="Completed" value="Completed" />
          <el-option label="Failed" value="Failed" />
        </el-select>
        <el-select v-model="filters.enabled" clearable :placeholder="t('kb.enabled')" @change="loadDocList">
          <el-option :label="t('kb.enabledOnly')" :value="true" />
          <el-option :label="t('kb.disabledOnly')" :value="false" />
        </el-select>
        <el-input v-model="filters.tag" :placeholder="t('kb.tagPlaceholder')" clearable @keyup.enter="loadDocList" />
      </div>

      <el-table v-loading="loadingList" :data="docList" stripe class="dark-table">
        <el-table-column prop="title" :label="t('docs.titleColumn')" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title || row.file_name }}</template>
        </el-table-column>
        <el-table-column prop="document_type" :label="t('docs.documentType')" width="110" />
        <el-table-column :label="t('docs.uploadTime')" width="180">
          <template #default="{ row }">
            {{ new Date(row.upload_time).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column :label="t('kb.enabled')" width="110">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">
              {{ row.enabled ? t("kb.enabled") : t("kb.disabled") }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('docs.status')" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" :class="'status-' + row.status.toLowerCase()">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('kb.tags')" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ formatTags(row.tags) }}</template>
        </el-table-column>
        <el-table-column :label="t('docs.chunks')" width="90" align="center" prop="chunk_count" />
        <el-table-column :label="t('docs.images')" width="80" align="center" prop="image_count" />
        <el-table-column :label="t('docs.action')" width="280" align="center" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button size="small" @click="openDrawer(row)">
                {{ t("docs.view") }}
              </el-button>
              <el-button size="small" @click="openEdit(row)">{{ t("common.edit") }}</el-button>
              <el-button size="small" @click="handleReprocess(row)">{{ t("kb.reprocess") }}</el-button>
              <el-button size="small" type="danger" @click="handleDelete(row)">{{ t("common.delete") }}</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer
      v-model="drawerVisible"
      :title="activeDoc?.title || activeDoc?.file_name || '解析结果'"
      size="60%"
      direction="rtl"
      class="dark-drawer"
    >
      <div v-if="loadingResult" class="detail-loading">
        <el-icon class="is-loading" style="font-size:32px"><Loading /></el-icon>
        <p>{{ t("common.loading") }}</p>
      </div>
      <template v-else-if="activeDoc">
        <el-descriptions :column="3" border style="margin-bottom: 20px" class="dark-descriptions">
          <el-descriptions-item :label="t('docs.chunks')">{{ activeChunkCount }}</el-descriptions-item>
          <el-descriptions-item :label="t('docs.images')">{{ activeImageCount }}</el-descriptions-item>
          <el-descriptions-item :label="t('docs.status')">
            <el-tag :type="statusType(activeDoc.status)">{{ activeDoc.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('docs.documentType')">{{ activeDoc.document_type }}</el-descriptions-item>
          <el-descriptions-item :label="t('kb.enabled')">
            {{ activeDoc.enabled ? t("kb.enabled") : t("kb.disabled") }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('kb.tags')">{{ formatTags(activeDoc.tags) }}</el-descriptions-item>
        </el-descriptions>

        <el-tabs v-model="resultTab" class="doc-result-tabs">
          <el-tab-pane :label="`${t('docs.chunksTitle')} (${activeChunkCount})`" name="chunks">
            <template v-if="parseResult">
              <div class="chunks-toolbar">
                <span class="chunks-hint">
                  {{ parseResult.chunks.length > 0 ? t("docs.chunkReadableHint") : t("docs.noChunks") }}
                </span>
              </div>
              <div class="chunks-container">
                <el-card
                  v-for="chunk in parseResult.chunks"
                  :key="chunk.chunk_index"
                  :ref="(el: Element | { $el?: Element } | null) => setChunkItemRef(chunk.chunk_index, el)"
                  class="chunk-card glass-card"
                  :class="{ 'chunk-card-active': activeChunkIndex === chunk.chunk_index }"
                  shadow="never"
                >
                  <template #header>
                    <div class="chunk-header">
                      <span>片段 #{{ chunk.chunk_index + 1 }}</span>
                      <span>
                        <template v-if="chunk.page_number">{{ t("docs.pageLabel", { page: chunk.page_number }) }} · </template>
                        {{ chunk.content.length }} 字
                      </span>
                    </div>
                  </template>
                  <pre class="chunk-content">{{ chunk.content }}</pre>
                </el-card>
                <el-alert
                  v-if="parseResult.chunks.length === 0 && parseResult.document.chunk_count > 0"
                  :title="t('docs.chunksLoadMismatch')"
                  type="warning"
                  show-icon
                  :closable="false"
                />
                <el-empty v-else-if="parseResult.chunks.length === 0" :description="t('docs.noChunks')" />
              </div>
            </template>
          </el-tab-pane>

          <el-tab-pane :label="`${t('docs.imagesTitle')} (${activeImageCount})`" name="images">
            <template v-if="parseResult">
              <div class="images-grid">
                <div v-for="img in sortedResultImages" :key="img.id" class="doc-image-item">
                  <div class="doc-image-badges">
                    <el-tag v-if="assetTypeLabel(img)" size="small" type="primary" effect="dark">
                      {{ assetTypeLabel(img) }}
                    </el-tag>
                    <el-tag v-if="img.page_number" size="small" effect="plain">
                      {{ t("docs.pageLabel", { page: img.page_number }) }}
                    </el-tag>
                    <el-tag v-if="isCrossPageAsset(img)" size="small" type="warning" effect="plain">
                      {{ t("docs.crossPageContinued") }}
                    </el-tag>
                  </div>
                  <ImageCard
                    :src="imgSrc(img.file_path)"
                    :title="img.title || img.id"
                    :description="img.generated_description || ''"
                    :status="img.status"
                  />
                  <p v-if="assetDetailText(img)" class="doc-image-meta">
                    {{ assetDetailText(img) }}
                  </p>
                </div>
                <el-empty v-if="parseResult.images.length === 0" :description="t('docs.noImages')" />
              </div>
            </template>
          </el-tab-pane>

          <el-tab-pane :label="t('docs.versionsTitle')" name="versions">
            <div class="version-toolbar">
              <div class="version-hint">{{ t("docs.versionsHint") }}</div>
              <el-upload
                :auto-upload="false"
                :show-file-list="false"
                accept=".pdf"
                :on-change="handleVersionFileChange"
              >
                <el-button type="primary" :loading="versionUploading">
                  <i class="i-ep-upload mr-2"></i>
                  {{ t("docs.versionUploadBtn") }}
                </el-button>
              </el-upload>
            </div>
            <el-table v-loading="versionsLoading" :data="documentVersions" stripe class="dark-table">
              <el-table-column :label="t('docs.versionNumber')" width="100" align="center">
                <template #default="{ row }">v{{ row.version_number || 1 }}</template>
              </el-table-column>
              <el-table-column :label="t('docs.latestVersion')" width="110" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.is_latest" type="success">{{ t("docs.latestVersion") }}</el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('docs.uploadTime')" width="180">
                <template #default="{ row }">{{ formatDateTime(row.upload_time) }}</template>
              </el-table-column>
              <el-table-column prop="file_name" :label="t('docs.fileName')" min-width="180" show-overflow-tooltip />
              <el-table-column prop="status" :label="t('docs.status')" width="120" />
              <el-table-column :label="t('docs.contentHash')" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">{{ shortenHash(row.content_hash) }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-drawer>

    <el-dialog v-model="editVisible" :title="t('docs.editTitle')" width="520px">
      <el-form label-position="top">
        <el-form-item :label="t('docs.titleColumn')">
          <el-input v-model="editForm.title" />
        </el-form-item>
        <el-form-item :label="t('kb.tags')">
          <el-input v-model="editForm.tagsText" :placeholder="t('kb.tagsTip')" />
        </el-form-item>
        <el-form-item :label="t('docs.documentType')">
          <el-select v-model="editForm.document_type">
            <el-option label="pdf" value="pdf" />
            <el-option label="markdown" value="markdown" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('kb.enabled')">
          <el-switch v-model="editForm.enabled" />
        </el-form-item>
        <el-form-item :label="t('kb.notes')">
          <el-input v-model="editForm.notes" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">{{ t("common.cancel") }}</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">{{ t("common.save") }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// ---- 导入 ----
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Loading } from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import {
  deleteDocument,
  getDocumentProgress,
  getDocResult,
  listDocuments,
  listDocumentVersions,
  reprocessDocument,
  updateDocument,
  uploadDocument,
  uploadDocumentVersion,
  type DocumentProgressResponse,
  type DocParseResult,
  type DocumentRecord,
} from "@/api/docs";
import ImageCard from "@/components/ImageCard.vue";
import UploadZone from "@/components/UploadZone.vue";
import { imgSrc } from "@/utils/image";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

// ---- 文件上传与进度状态 ----
const selectedFiles = ref<File[]>([]);
const selectedFile = computed(() => selectedFiles.value[0] || null);
const uploading = ref(false);
const uploadMsg = ref("");
const uploadSuccess = ref(false);
const saving = ref(false);
const versionUploading = ref(false);
const versionsLoading = ref(false);
const uploadPercent = ref(0);
const progressDocId = ref("");
const progressStage = ref("idle");
const progressPercent = ref(0);
const progressMessage = ref("");
let progressTimer: number | null = null;

// ---- 文档列表过滤条件 ----
const filters = reactive({
  keyword: "",
  status: "",
  enabled: undefined as boolean | undefined,
  tag: "",
});

// ---- 文档列表与详情抽屉状态 ----
const docList = ref<DocumentRecord[]>([]);
const loadingList = ref(false);
const drawerVisible = ref(false);
const activeDoc = ref<DocumentRecord | null>(null);
const parseResult = ref<DocParseResult | null>(null);
const documentVersions = ref<DocumentRecord[]>([]);
const loadingResult = ref(false);
const resultTab = ref("chunks");
const activeChunkIndex = ref<number | null>(null);
const chunkItemRefs = new Map<number, HTMLElement>();

// ---- 文档编辑弹窗状态 ----
const editVisible = ref(false);
const currentDocId = ref("");
const editForm = reactive({
  title: "",
  tagsText: "",
  notes: "",
  enabled: true,
  document_type: "pdf",
});

// ---- 计算属性 ----

/** 按页码 → 表格索引 → 标题排序的解析结果图片列表 */
const sortedResultImages = computed(() => {
  if (!parseResult.value) return [];
  return [...parseResult.value.images].sort((left, right) => {
    const leftPage = left.page_number ?? Number.MAX_SAFE_INTEGER;
    const rightPage = right.page_number ?? Number.MAX_SAFE_INTEGER;
    if (leftPage !== rightPage) return leftPage - rightPage;

    const leftIndex = left.table_index_on_page ?? Number.MAX_SAFE_INTEGER;
    const rightIndex = right.table_index_on_page ?? Number.MAX_SAFE_INTEGER;
    if (leftIndex !== rightIndex) return leftIndex - rightIndex;

    return (left.title || left.id).localeCompare(right.title || right.id);
  });
});

/** 当前文档的文本片段数量（优先取解析结果，回退到文档记录） */
const activeChunkCount = computed(() => parseResult.value?.chunks.length ?? activeDoc.value?.chunk_count ?? 0);
/** 当前文档的提取图片数量 */
const activeImageCount = computed(() => parseResult.value?.images.length ?? activeDoc.value?.image_count ?? 0);
/** 是否显示上传/处理进度面板 */
const showProgressPanel = computed(() => uploading.value || !!progressDocId.value);

/** 进度面板标题（上传中 vs 处理中） */
const progressTitle = computed(() => {
  if (uploading.value && uploadPercent.value < 100) return t("docs.uploadingProgress");
  return t("docs.processingProgress");
});

/** 进度条状态样式（失败=exception，完成=success，其余=默认） */
const progressStatus = computed(() => {
  if (progressStage.value === "failed") return "exception";
  if (progressStage.value === "completed") return "success";
  return undefined;
});

// ---- 工具函数 ----

/** 将日期时间字符串格式化为本地显示格式 */
function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

/** 截断并缩写哈希值用于展示（保留前10位和后6位） */
function shortenHash(value?: string | null): string {
  if (!value) return "-";
  return value.length > 16 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

/** 清除文档处理进度的定时轮询 */
function clearProgressPolling() {
  if (progressTimer !== null) {
    window.clearTimeout(progressTimer);
    progressTimer = null;
  }
}

/** 获取处理阶段的回退显示标签（当后端未返回 message 时使用） */
function stageFallbackLabel(stage: string) {
  const fallbackMap: Record<string, string> = {
    idle: "",
    uploading: t("docs.progressStages.uploading"),
    queued: t("docs.progressStages.queued"),
    submitting: t("docs.progressStages.submitting"),
    parsing_text: t("docs.progressStages.parsing_text"),
    extracting_images: t("docs.progressStages.extracting_images"),
    vectorizing: t("docs.progressStages.vectorizing"),
    completed: t("docs.progressStages.completed"),
    failed: t("docs.progressStages.failed"),
  };
  return fallbackMap[stage] || stage;
}

/** 将后端返回的进度数据应用到组件状态 */
function applyProgress(progress: DocumentProgressResponse) {
  progressStage.value = progress.stage;
  progressPercent.value = progress.progress_percent ?? 0;
  progressMessage.value = progress.message || stageFallbackLabel(progress.stage);
}

/** 轮询文档处理进度，直到完成或失败 */
async function pollDocumentProgress(docId: string) {
  clearProgressPolling();
  progressDocId.value = docId;

  const run = async () => {
    try {
      const progress = await getDocumentProgress(docId);
      applyProgress(progress);
      await loadDocList(false);
      if (activeDoc.value?.id === docId) {
        activeDoc.value = progress.document;
      }
      if (progress.status === "Completed" || progress.status === "Failed") {
        progressDocId.value = "";
        return;
      }
      progressTimer = window.setTimeout(run, 1500);
    } catch {
      progressTimer = window.setTimeout(run, 2500);
    }
  };

  await run();
}

/** 加载指定文档的所有版本记录 */
async function loadDocVersions(docId: string) {
  try {
    versionsLoading.value = true;
    documentVersions.value = await listDocumentVersions(docId);
  } catch (error) {
    console.error("加载文档版本失败:", error);
    ElMessage.error(t("docs.versionLoadFailed"));
  } finally {
    versionsLoading.value = false;
  }
}

// ---- 核心操作方法 ----

/** 上传选中的 PDF 文件，启动进度轮询 */
async function doUpload() {
  if (!selectedFile.value) return;
  uploading.value = true;
  uploadPercent.value = 0;
  uploadMsg.value = "";
  try {
    const res = await uploadDocument(selectedFile.value, (percent) => {
      uploadPercent.value = percent;
      progressStage.value = "uploading";
      progressPercent.value = percent;
      progressMessage.value = t("docs.uploadingMessage", { percent });
    });
    uploadSuccess.value = true;
    uploadMsg.value = res.message || t("docs.uploadQueued");
    selectedFiles.value = [];
    progressStage.value = res.document.parse_stage || "queued";
    progressPercent.value = Math.max(progressPercent.value, res.document.progress_percent ?? 0);
    progressMessage.value = res.document.progress_message || stageFallbackLabel(progressStage.value);
    await loadDocList();
    await pollDocumentProgress(res.document.id);
  } catch (e: any) {
    uploadSuccess.value = false;
    uploadMsg.value = e?.response?.data?.detail || t("docs.uploadFailed");
    progressStage.value = "failed";
    progressMessage.value = uploadMsg.value;
  } finally {
    uploading.value = false;
  }
}

/** 加载文档列表，可选自动启动对处理中文档的进度轮询 */
async function loadDocList(autostartPoll = true) {
  loadingList.value = true;
  try {
    docList.value = await listDocuments({
      keyword: filters.keyword || undefined,
      status: filters.status || undefined,
      enabled: filters.enabled,
      tag: filters.tag || undefined,
    });
    if (autostartPoll && !progressDocId.value) {
      const processingDoc = docList.value.find((item) => item.status === "Processing");
      if (processingDoc) {
        progressStage.value = processingDoc.parse_stage || "queued";
        progressPercent.value = processingDoc.progress_percent ?? 0;
        progressMessage.value = processingDoc.progress_message || stageFallbackLabel(progressStage.value);
        void pollDocumentProgress(processingDoc.id);
      }
    }
  } catch {
    ElMessage.error(t("docs.loadFailed"));
  } finally {
    loadingList.value = false;
  }
}

/** 将文档状态映射为 Element Plus Tag 类型 */
function statusType(status: string) {
  if (status === "Completed") return "success";
  if (status === "Failed") return "danger";
  return "warning";
}

/** 将标签数组格式化为逗号分隔字符串 */
function formatTags(tags?: string[]) {
  return tags?.length ? tags.join(", ") : "-";
}

/** 将资源类型映射为可读标签（表格截图/整页渲染/页面渲染） */
function assetTypeLabel(img: DocParseResult["images"][number]) {
  if (img.asset_type === "table_crop") return t("docs.tableCrop");
  if (img.asset_type === "table_page_render") return t("docs.tablePageRender");
  if (img.asset_type === "page_render") return t("docs.pageRender");
  return "";
}

/** 判断资源是否跨页延续 */
function isCrossPageAsset(img: DocParseResult["images"][number]) {
  return Boolean(img.continued_from_previous_page || img.continued_to_next_page);
}

/** 拼接资源的详情描述文本（表格索引、回退原因、跨页分组信息） */
function assetDetailText(img: DocParseResult["images"][number]) {
  const parts: string[] = [];
  if (img.asset_type === "table_crop" && typeof img.table_index_on_page === "number") {
    parts.push(t("docs.tableIndexLabel", { index: img.table_index_on_page + 1 }));
  }
  if ((img.asset_type === "table_page_render" || img.asset_type === "page_render") && img.fallback_reason) {
    parts.push(t(`docs.fallbackReason.${img.fallback_reason}`));
  }
  if (img.table_group_id) {
    parts.push(t("docs.crossPageGroup"));
  }
  return parts.join(" · ");
}

/** 收集/清理文本片段卡片的 DOM 引用，用于滚动定位 */
function setChunkItemRef(chunkIndex: number, element: Element | { $el?: Element } | null) {
  const actualElement = element instanceof HTMLElement
    ? element
    : element && "$el" in element && element.$el instanceof HTMLElement
      ? element.$el
      : null;
  if (actualElement) {
    chunkItemRefs.set(chunkIndex, actualElement);
    return;
  }
  chunkItemRefs.delete(chunkIndex);
}

/** 滚动到指定索引的文本片段卡片并高亮显示 */
async function scrollToTargetChunk(chunkIndex: number | null) {
  if (chunkIndex === null || chunkIndex === undefined) {
    activeChunkIndex.value = null;
    return;
  }
  activeChunkIndex.value = chunkIndex;
  await nextTick();
  const target = chunkItemRefs.get(chunkIndex);
  target?.scrollIntoView({ behavior: "smooth", block: "center" });
  window.setTimeout(() => {
    if (activeChunkIndex.value === chunkIndex) {
      activeChunkIndex.value = null;
    }
  }, 2600);
}

/** 从路由查询参数（chunk 或 page）解析目标片段索引 */
function resolveChunkIndexFromRoute(result: DocParseResult): number | null {
  const chunkParam = route.query.chunk;
  if (typeof chunkParam === "string" && chunkParam !== "") {
    const parsed = Number(chunkParam);
    if (!Number.isNaN(parsed) && result.chunks.some((chunk) => chunk.chunk_index === parsed)) {
      return parsed;
    }
  }
  const pageParam = route.query.page;
  if (typeof pageParam === "string" && pageParam !== "") {
    const parsed = Number(pageParam);
    if (!Number.isNaN(parsed)) {
      const matched = result.chunks.find((chunk) => chunk.page_number === parsed);
      if (matched) {
        return matched.chunk_index;
      }
    }
  }
  return null;
}

/** 根据路由参数切换 Tab 并定位到目标片段 */
async function applyRouteTarget(result: DocParseResult) {
  const requestedTab = typeof route.query.tab === "string" ? route.query.tab : "chunks";
  resultTab.value = ["chunks", "images", "versions"].includes(requestedTab) ? requestedTab : "chunks";
  if (resultTab.value === "chunks") {
    await scrollToTargetChunk(resolveChunkIndexFromRoute(result));
  } else {
    activeChunkIndex.value = null;
  }
}

/** 打开文档详情抽屉，加载解析结果和版本列表 */
async function openDrawer(doc: DocumentRecord) {
  activeDoc.value = doc;
  drawerVisible.value = true;
  loadingResult.value = true;
  resultTab.value = "chunks";
  parseResult.value = null;
  try {
    const [result] = await Promise.all([
      getDocResult(doc.id).catch(() => null),
      loadDocVersions(doc.id),
    ]);
    if (result) {
      parseResult.value = result;
      activeDoc.value = result.document;
      await applyRouteTarget(result);
    }
  } catch {
    ElMessage.error(t("docs.loadResultFailed"));
  } finally {
    loadingResult.value = false;
  }
}

/** 根据路由中的 docId 打开对应文档（先在当前列表查找，未找到则重新加载列表） */
async function openDocumentFromRoute(docId: string) {
  const target = docList.value.find((item) => item.id === docId);
  if (target) {
    await openDrawer(target);
    return;
  }
  try {
    await loadDocList(false);
    const reloaded = docList.value.find((item) => item.id === docId);
    if (reloaded) {
      await openDrawer(reloaded);
    }
  } catch {
    // keep existing load error handling
  }
}

/** 同步路由参数到抽屉状态：打开文档或切换 Tab/片段定位 */
async function syncRouteTarget() {
  const docId = typeof route.query.docId === "string" ? route.query.docId : "";
  if (!docId) return;

  if (!drawerVisible.value || activeDoc.value?.id !== docId) {
    await openDocumentFromRoute(docId);
    return;
  }

  if (parseResult.value) {
    await applyRouteTarget(parseResult.value);
  }
}

/** 打开文档编辑弹窗，填充当前文档信息 */
function openEdit(doc: DocumentRecord) {
  currentDocId.value = doc.id;
  editForm.title = doc.title || "";
  editForm.tagsText = doc.tags?.join(", ") || "";
  editForm.notes = doc.notes || "";
  editForm.enabled = doc.enabled ?? true;
  editForm.document_type = doc.document_type || "pdf";
  editVisible.value = true;
}

/** 提交文档编辑（标题、标签、备注、启用状态、文档类型） */
async function submitEdit() {
  try {
    saving.value = true;
    const updated = await updateDocument(currentDocId.value, {
      title: editForm.title || null,
      tags: editForm.tagsText.split(",").map((item) => item.trim()).filter(Boolean),
      notes: editForm.notes || null,
      enabled: editForm.enabled,
      document_type: editForm.document_type,
    });
    ElMessage.success(t("docs.updateSuccess"));
    editVisible.value = false;
    await loadDocList();
    if (activeDoc.value?.id === currentDocId.value) {
      activeDoc.value = updated;
      await loadDocVersions(updated.id);
    }
  } catch {
    ElMessage.error(t("docs.updateFailed"));
  } finally {
    saving.value = false;
  }
}

/** 删除文档（含二次确认），同时关闭已打开的抽屉 */
async function handleDelete(doc: DocumentRecord) {
  await ElMessageBox.confirm(
    t("docs.deleteConfirm", { title: doc.title || doc.file_name, chunks: doc.chunk_count, images: doc.image_count }),
    t("common.confirm"),
    { type: "warning" }
  );
  try {
    await deleteDocument(doc.id);
    ElMessage.success(t("docs.deleteSuccess"));
    if (activeDoc.value?.id === doc.id) {
      drawerVisible.value = false;
      activeDoc.value = null;
      parseResult.value = null;
      documentVersions.value = [];
    }
    await loadDocList();
  } catch {
    ElMessage.error(t("docs.deleteFailed"));
  }
}

/** 重新处理文档（触发后端重新解析），启动进度轮询 */
async function handleReprocess(doc: DocumentRecord) {
  try {
    await reprocessDocument(doc.id);
    ElMessage.success(t("docs.reprocessQueued"));
    progressStage.value = "queued";
    progressPercent.value = 0;
    progressMessage.value = t("docs.reprocessQueued");
    await loadDocList(false);
    await pollDocumentProgress(doc.id);
    if (activeDoc.value?.id === doc.id) {
      await openDrawer(doc);
    }
  } catch {
    ElMessage.error(t("docs.reprocessFailed"));
  }
}

/** 上传文档新版本文件，触发重新解析并刷新版本列表 */
async function handleVersionFileChange(uploadFile: { raw?: File }) {
  if (!uploadFile.raw || !activeDoc.value) return;
  try {
    versionUploading.value = true;
    const response = await uploadDocumentVersion(activeDoc.value.id, uploadFile.raw);
    ElMessage.success(t("docs.versionUploadSuccess"));
    progressStage.value = response.document.parse_stage || "queued";
    progressPercent.value = response.document.progress_percent ?? 0;
    progressMessage.value = response.document.progress_message || stageFallbackLabel(progressStage.value);
    await loadDocList(false);
    await loadDocVersions(activeDoc.value.id);
    activeDoc.value = response.document;
    resultTab.value = "versions";
    await pollDocumentProgress(response.document.id);
  } catch (error) {
    console.error("上传文档新版本失败:", error);
    ElMessage.error(t("docs.versionUploadFailed"));
  } finally {
    versionUploading.value = false;
  }
}

// ---- 生命周期与路由侦听 ----

onMounted(async () => {
  await loadDocList();
  await syncRouteTarget();
});

watch(
  () => route.query,
  async () => {
    await syncRouteTarget();
  },
);

/** 抽屉关闭时清理路由中的文档相关查询参数 */
watch(drawerVisible, (visible) => {
  if (visible || !route.query.docId) return;
  const nextQuery = { ...route.query };
  delete nextQuery.docId;
  delete nextQuery.tab;
  delete nextQuery.chunk;
  delete nextQuery.page;
  router.replace({ path: route.path, query: nextQuery });
});

onBeforeUnmount(() => {
  clearProgressPolling();
});
</script>

<style scoped>
.doc-kb {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.accent-icon {
  color: var(--accent-primary);
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
  margin-top: 0;
  min-width: 196px;
  min-height: 38px;
  padding: 0 18px;
  border-radius: 12px;
}

.upload-progress-panel {
  margin-top: 16px;
  padding: 14px 16px;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.76);
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--text-primary);
}

.progress-message {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.filter-bar {
  display: grid;
  grid-template-columns: minmax(220px, 2fr) repeat(3, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.row-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.dark-table {
  --el-table-bg-color: var(--bg-secondary);
  --el-table-tr-bg-color: var(--bg-secondary);
  --el-table-header-bg-color: var(--bg-tertiary);
}

.status-completed {
  --el-tag-bg-color: rgba(103, 194, 58, 0.1);
  --el-tag-border-color: rgba(103, 194, 58, 0.3);
  --el-tag-text-color: #67c23a;
}

.status-failed {
  --el-tag-bg-color: rgba(245, 108, 108, 0.1);
  --el-tag-border-color: rgba(245, 108, 108, 0.3);
  --el-tag-text-color: #f56c6c;
}

.status-processing {
  --el-tag-bg-color: rgba(0, 212, 255, 0.1);
  --el-tag-border-color: rgba(0, 212, 255, 0.3);
  --el-tag-text-color: var(--accent-primary);
}

.dark-drawer :deep(.el-drawer__header) {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 0;
}

@media (max-width: 960px) {
  .upload-entry-row {
    grid-template-columns: 1fr;
  }

  .upload-btn {
    width: 100%;
  }
}

.dark-drawer :deep(.el-drawer__body) {
  background: var(--bg-primary);
}

.dark-descriptions :deep(.el-descriptions__label) {
  background: var(--bg-tertiary);
}

.detail-loading {
  text-align: center;
  padding: 40px;
}

.doc-result-tabs :deep(.el-tabs__nav-wrap::after) {
  background: var(--border-color);
}

.doc-result-tabs :deep(.el-tabs__item) {
  color: var(--text-secondary);
}

.doc-result-tabs :deep(.el-tabs__item.is-active) {
  color: var(--accent-primary);
}

.chunks-toolbar,
.version-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.chunks-hint,
.version-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.chunks-container {
  max-height: 520px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.chunk-card {
  padding: 0;
  height: auto;
  overflow: visible;
}

.chunk-card-active {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 1px rgba(0, 212, 255, 0.16), 0 10px 28px rgba(15, 23, 42, 0.12);
}

.chunk-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.chunk-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: "JetBrains Mono", "Cascadia Code", monospace;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
}

.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px;
}

.doc-image-item {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.doc-image-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.doc-image-meta {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}

@media (max-width: 900px) {
  .filter-bar {
    grid-template-columns: 1fr;
  }

  .version-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
