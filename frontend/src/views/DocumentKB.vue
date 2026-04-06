<template>
  <div class="doc-kb">
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

        <el-divider content-position="left">{{ t("docs.chunksTitle") }}（{{ parseResult.chunks.length }} 条）</el-divider>
        <div class="chunks-container">
          <el-card
            v-for="chunk in parseResult.chunks"
            :key="chunk.chunk_index"
            class="chunk-card glass-card"
            shadow="never"
          >
            <template #header>
              <span style="font-size:12px;color:var(--text-secondary)">片段 #{{ chunk.chunk_index + 1 }}</span>
            </template>
            <p class="chunk-content">{{ chunk.content }}</p>
          </el-card>
          <el-empty v-if="parseResult.chunks.length === 0" :description="t('docs.noChunks')" />
        </div>

        <el-divider content-position="left">{{ t("docs.imagesTitle") }}（{{ parseResult.images.length }} 张）</el-divider>
        <div class="images-grid">
          <ImageCard
            v-for="img in parseResult.images"
            :key="img.id"
            :src="imgSrc(img.file_path)"
            :title="img.title || img.id"
            :description="img.generated_description || ''"
            :status="img.status"
          />
          <el-empty v-if="parseResult.images.length === 0" :description="t('docs.noImages')" />
        </div>
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
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Loading } from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";
import {
  deleteDocument,
  getDocResult,
  listDocuments,
  reprocessDocument,
  updateDocument,
  uploadDocument,
  type DocParseResult,
  type DocumentRecord,
} from "@/api/docs";
import ImageCard from "@/components/ImageCard.vue";
import UploadZone from "@/components/UploadZone.vue";
import { imgSrc } from "@/utils/image";

const { t } = useI18n();

const selectedFiles = ref<File[]>([]);
const selectedFile = computed(() => selectedFiles.value[0] || null);
const uploading = ref(false);
const uploadMsg = ref("");
const uploadSuccess = ref(false);
const saving = ref(false);

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

const editVisible = ref(false);
const currentDocId = ref("");
const editForm = reactive({
  title: "",
  tagsText: "",
  notes: "",
  enabled: true,
  document_type: "pdf",
});

async function doUpload() {
  if (!selectedFile.value) return;
  uploading.value = true;
  uploadMsg.value = "";
  try {
    const res = await uploadDocument(selectedFile.value);
    uploadSuccess.value = true;
    uploadMsg.value = res.message || t("docs.uploadSuccess");
    selectedFiles.value = [];
    await loadDocList();
  } catch (e: any) {
    uploadSuccess.value = false;
    uploadMsg.value = e?.response?.data?.detail || t("docs.uploadFailed");
  } finally {
    uploading.value = false;
  }
}

async function loadDocList() {
  loadingList.value = true;
  try {
    docList.value = await listDocuments({
      keyword: filters.keyword || undefined,
      status: filters.status || undefined,
      enabled: filters.enabled,
      tag: filters.tag || undefined,
    });
  } catch {
    ElMessage.error(t("docs.loadFailed"));
  } finally {
    loadingList.value = false;
  }
}

onMounted(loadDocList);

function statusType(status: string) {
  if (status === "Completed") return "success";
  if (status === "Failed") return "danger";
  return "warning";
}

function formatTags(tags?: string[]) {
  return tags?.length ? tags.join(", ") : "-";
}

async function viewResult(doc: DocumentRecord) {
  activeDoc.value = doc;
  drawerVisible.value = true;
  loadingResult.value = true;
  parseResult.value = null;
  try {
    parseResult.value = await getDocResult(doc.id);
  } catch {
    ElMessage.error(t("docs.loadResultFailed"));
  } finally {
    loadingResult.value = false;
  }
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
    ElMessage.success(t("docs.reprocessSuccess"));
    await loadDocList();
    if (activeDoc.value?.id === doc.id) {
      await viewResult(doc);
    }
  } catch {
    ElMessage.error(t("docs.reprocessFailed"));
  }
}
</script>

<style scoped>
.doc-kb {
  max-width: 1200px;
  margin: 0 auto;
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
  background: var(--accent-gradient);
  border: none;
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

.chunks-container {
  max-height: 400px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.chunk-card {
  padding: 0;
}

.chunk-content {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  color: var(--text-primary);
}

.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}
</style>
