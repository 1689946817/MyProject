<template>
  <div class="doc-kb">
    <div class="page-intro">
      <div class="page-intro-main">
        <h1 class="page-title">{{ t("docs.title") }}</h1>
        <p class="page-subtitle">{{ t("docs.subtitle") }}</p>
      </div>
    </div>
    <el-card class="glass-card">
      <template #header>
        <div class="card-header">
          <i class="i-ep-document mr-2 accent-icon"></i>
          <span>{{ t("docs.title") }}</span>
        </div>
      </template>
      <UploadZone
        v-model:files="selectedFiles"
        :text="t('docs.uploadArea')"
        :hint="t('docs.uploadTip')"
        :accept="'.pdf'"
        :multiple="false"
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
              <el-button size="small" :disabled="row.status !== 'Completed'" @click="viewResult(row)">
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
      <div v-if="loadingResult" style="text-align:center;padding:40px">
        <el-icon class="is-loading" style="font-size:32px"><Loading /></el-icon>
        <p>{{ t("common.loading") }}</p>
      </div>
      <template v-else-if="parseResult">
        <el-descriptions :column="3" border style="margin-bottom: 20px" class="dark-descriptions">
          <el-descriptions-item :label="t('docs.chunks')">{{ parseResult.chunks.length }}</el-descriptions-item>
          <el-descriptions-item :label="t('docs.images')">{{ parseResult.images.length }}</el-descriptions-item>
          <el-descriptions-item :label="t('docs.status')">
            <el-tag :type="statusType(parseResult.document.status)">{{ parseResult.document.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('docs.documentType')">{{ parseResult.document.document_type }}</el-descriptions-item>
          <el-descriptions-item :label="t('kb.enabled')">
            {{ parseResult.document.enabled ? t("kb.enabled") : t("kb.disabled") }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('kb.tags')">{{ formatTags(parseResult.document.tags) }}</el-descriptions-item>
        </el-descriptions>

        <el-tabs v-model="resultTab" class="doc-result-tabs">
          <el-tab-pane :label="`${t('docs.chunksTitle')} (${parseResult.chunks.length})`" name="chunks">
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
          </el-tab-pane>

          <el-tab-pane :label="`${t('docs.imagesTitle')} (${parseResult.images.length})`" name="images">
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
  reprocessDocument,
  updateDocument,
  uploadDocument,
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

const selectedFiles = ref<File[]>([]);
const selectedFile = computed(() => selectedFiles.value[0] || null);
const uploading = ref(false);
const uploadMsg = ref("");
const uploadSuccess = ref(false);
const saving = ref(false);
const uploadPercent = ref(0);
const progressDocId = ref("");
const progressStage = ref("idle");
const progressPercent = ref(0);
const progressMessage = ref("");
let progressTimer: number | null = null;

const filters = reactive({
  keyword: "",
  status: "",
  enabled: undefined as boolean | undefined,
  tag: "",
});

const docList = ref<DocumentRecord[]>([]);
const loadingList = ref(false);
const drawerVisible = ref(false);
const activeDoc = ref<DocumentRecord | null>(null);
const parseResult = ref<DocParseResult | null>(null);
const loadingResult = ref(false);
const resultTab = ref("chunks");
const activeChunkIndex = ref<number | null>(null);
const chunkItemRefs = new Map<number, HTMLElement>();

const editVisible = ref(false);
const currentDocId = ref("");
const editForm = reactive({
  title: "",
  tagsText: "",
  notes: "",
  enabled: true,
  document_type: "pdf",
});

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

const showProgressPanel = computed(() => uploading.value || !!progressDocId.value);

const progressTitle = computed(() => {
  if (uploading.value && uploadPercent.value < 100) return t("docs.uploadingProgress");
  return t("docs.processingProgress");
});

const progressStatus = computed(() => {
  if (progressStage.value === "failed") return "exception";
  if (progressStage.value === "completed") return "success";
  return undefined;
});

function clearProgressPolling() {
  if (progressTimer !== null) {
    window.clearTimeout(progressTimer);
    progressTimer = null;
  }
}

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

function applyProgress(progress: DocumentProgressResponse) {
  progressStage.value = progress.stage;
  progressPercent.value = progress.progress_percent ?? 0;
  progressMessage.value = progress.message || stageFallbackLabel(progress.stage);
}

async function pollDocumentProgress(docId: string) {
  clearProgressPolling();
  progressDocId.value = docId;

  const run = async () => {
    try {
      const progress = await getDocumentProgress(docId);
      applyProgress(progress);
      await loadDocList(false);
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

function statusType(status: string) {
  if (status === "Completed") return "success";
  if (status === "Failed") return "danger";
  return "warning";
}

function formatTags(tags?: string[]) {
  return tags?.length ? tags.join(", ") : "-";
}

function assetTypeLabel(img: DocParseResult["images"][number]) {
  if (img.asset_type === "table_crop") return t("docs.tableCrop");
  if (img.asset_type === "table_page_render") return t("docs.tablePageRender");
  if (img.asset_type === "page_render") return t("docs.pageRender");
  return "";
}

function isCrossPageAsset(img: DocParseResult["images"][number]) {
  return Boolean(img.continued_from_previous_page || img.continued_to_next_page);
}

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

async function applyRouteTarget(result: DocParseResult) {
  const requestedTab = route.query.tab === "images" ? "images" : "chunks";
  resultTab.value = requestedTab;
  if (requestedTab === "chunks") {
    await scrollToTargetChunk(resolveChunkIndexFromRoute(result));
  } else {
    activeChunkIndex.value = null;
  }
}

async function viewResult(doc: DocumentRecord) {
  activeDoc.value = doc;
  drawerVisible.value = true;
  loadingResult.value = true;
  resultTab.value = "chunks";
  parseResult.value = null;
  try {
    parseResult.value = await getDocResult(doc.id);
    await applyRouteTarget(parseResult.value);
  } catch {
    ElMessage.error(t("docs.loadResultFailed"));
  } finally {
    loadingResult.value = false;
  }
}

async function openDocumentFromRoute(docId: string) {
  const target = docList.value.find((item) => item.id === docId);
  if (target) {
    await viewResult(target);
    return;
  }
  try {
    await loadDocList(false);
    const reloaded = docList.value.find((item) => item.id === docId);
    if (reloaded) {
      await viewResult(reloaded);
    }
  } catch {
    // keep existing load error handling
  }
}

async function syncRouteTarget() {
  const docId = typeof route.query.docId === "string" ? route.query.docId : "";
  if (!docId) {
    return;
  }

  if (!drawerVisible.value || activeDoc.value?.id !== docId || !parseResult.value) {
    await openDocumentFromRoute(docId);
    return;
  }

  await applyRouteTarget(parseResult.value);
}

function openEdit(doc: DocumentRecord) {
  currentDocId.value = doc.id;
  editForm.title = doc.title || "";
  editForm.tagsText = doc.tags?.join(", ") || "";
  editForm.notes = doc.notes || "";
  editForm.enabled = doc.enabled ?? true;
  editForm.document_type = doc.document_type || "pdf";
  editVisible.value = true;
}

async function submitEdit() {
  try {
    saving.value = true;
    await updateDocument(currentDocId.value, {
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
      activeDoc.value = docList.value.find((item) => item.id === currentDocId.value) || activeDoc.value;
    }
  } catch {
    ElMessage.error(t("docs.updateFailed"));
  } finally {
    saving.value = false;
  }
}

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
    }
    await loadDocList();
  } catch {
    ElMessage.error(t("docs.deleteFailed"));
  }
}

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
      await viewResult(doc);
    }
  } catch {
    ElMessage.error(t("docs.reprocessFailed"));
  }
}

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

watch(drawerVisible, (visible) => {
  if (visible || !route.query.docId) {
    return;
  }
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

.upload-btn {
  margin-top: 16px;
  width: 100%;
  min-height: 44px;
  border-radius: 14px;
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

.dark-drawer :deep(.el-drawer__body) {
  background: var(--bg-primary);
}

.dark-descriptions :deep(.el-descriptions__label) {
  background: var(--bg-tertiary);
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

.chunks-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.chunks-hint {
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
  border-color: rgba(59, 130, 246, 0.42);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.12), 0 16px 32px rgba(59, 130, 246, 0.1);
}

.chunk-card :deep(.el-card__header) {
  padding: 10px 16px;
}

.chunk-card :deep(.el-card__body) {
  padding: 14px 16px;
  overflow: visible;
}

.chunk-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.chunk-content {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  color: var(--text-primary);
  user-select: text;
  font-family: "Cascadia Code", "SFMono-Regular", Consolas, monospace;
}

.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.doc-image-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doc-image-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.doc-image-meta {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.doc-kb :deep(.el-card__body) {
  padding: 22px;
}
</style>
