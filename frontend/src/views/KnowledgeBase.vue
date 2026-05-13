<!-- 图片知识库管理页面：支持图片上传、列表浏览（网格/表格）、筛选、详情查看、版本管理和编辑 -->
<template>
  <div class="kb-page">
    <div class="page-intro">
      <div class="page-intro-main">
        <h1 class="page-title">{{ t("kb.title") }}</h1>
        <p class="page-subtitle">{{ t("kb.subtitle") }}</p>
      </div>
    </div>
    <el-card class="upload-card upload-entry-card glass-card">
      <div class="upload-entry-row">
        <UploadZone
          v-model:files="fileList"
          :text="t('kb.uploadArea')"
          :accept="'image/*'"
          :multiple="true"
          compact
        />

        <el-button
          type="primary"
          class="upload-btn"
          :loading="uploading"
          @click="doUpload"
        >
          <i class="i-ep-upload mr-2"></i>
          {{ t("kb.uploadBtn") }}
        </el-button>
      </div>
    </el-card>

    <el-card class="images-card glass-card">
      <template #header>
        <div class="card-header">
          <span>{{ t("kb.uploadedImages") }}</span>
          <div class="header-actions">
            <el-button size="small" @click="loadImages">
              <i class="i-ep-refresh mr-1"></i>
              {{ t("docs.refresh") }}
            </el-button>
            <el-button-group>
              <el-button :type="viewMode === 'grid' ? 'primary' : 'default'" @click="viewMode = 'grid'">
                <i class="i-ep-grid"></i>
              </el-button>
              <el-button :type="viewMode === 'table' ? 'primary' : 'default'" @click="viewMode = 'table'">
                <i class="i-ep-list"></i>
              </el-button>
            </el-button-group>
          </div>
        </div>
      </template>

      <div class="filter-bar">
        <el-input v-model="filters.keyword" :placeholder="t('kb.searchPlaceholder')" clearable @keyup.enter="loadImages">
          <template #prefix><i class="i-ep-search"></i></template>
        </el-input>
        <el-select v-model="filters.status" clearable :placeholder="t('kb.status')" @change="loadImages">
          <el-option label="Processing" value="Processing" />
          <el-option label="Completed" value="Completed" />
          <el-option label="Failed" value="Failed" />
        </el-select>
        <el-select v-model="filters.enabled" clearable :placeholder="t('kb.enabled')" @change="loadImages">
          <el-option :label="t('kb.enabledOnly')" :value="true" />
          <el-option :label="t('kb.disabledOnly')" :value="false" />
        </el-select>
        <el-input v-model="filters.tag" :placeholder="t('kb.tagPlaceholder')" clearable @keyup.enter="loadImages" />
      </div>

      <div v-if="viewMode === 'grid'" class="image-grid">
        <div v-for="img in images" :key="img.id" class="grid-item">
          <ImageCard
            :src="getImageSrc(img.file_path)"
            :title="img.title || img.id"
            :description="img.generated_description || ''"
            :status="img.status"
            @click="openDetails(img)"
          />
          <div class="grid-meta">
            <el-tag size="small" :type="img.enabled ? 'success' : 'info'">
              {{ img.enabled ? t("kb.enabled") : t("kb.disabled") }}
            </el-tag>
            <span class="meta-text">{{ formatTags(img.tags) }}</span>
          </div>
          <div class="grid-actions">
            <el-button size="small" @click="openDetails(img)">{{ t("docs.view") }}</el-button>
            <el-button size="small" @click="openEdit(img)">{{ t("common.edit") }}</el-button>
            <el-button size="small" @click="handleReprocess(img)">{{ t("kb.reprocess") }}</el-button>
            <el-button size="small" type="danger" @click="handleDelete(img)">{{ t("common.delete") }}</el-button>
          </div>
        </div>
        <el-empty v-if="images.length === 0" :description="t('kb.noImages')" />
      </div>

      <el-table v-else v-loading="loading" :data="images" height="520" class="dark-table">
        <el-table-column prop="title" :label="t('kb.titleColumn')" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title || row.id }}</template>
        </el-table-column>
        <el-table-column prop="source_dataset" :label="t('kb.source')" width="120" />
        <el-table-column :label="t('kb.enabled')" width="110">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">
              {{ row.enabled ? t("kb.enabled") : t("kb.disabled") }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('kb.status')" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" :class="'status-' + row.status.toLowerCase()">
              <span v-if="row.status === 'Processing'" class="pulse-dot"></span>
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('kb.tags')" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ formatTags(row.tags) }}</template>
        </el-table-column>
        <el-table-column :label="t('kb.description')" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.generated_description }}</template>
        </el-table-column>
        <el-table-column :label="t('docs.action')" width="260" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button size="small" @click="openDetails(row)">{{ t("docs.view") }}</el-button>
              <el-button size="small" @click="openEdit(row)">{{ t("common.edit") }}</el-button>
              <el-button size="small" @click="handleReprocess(row)">{{ t("kb.reprocess") }}</el-button>
              <el-button size="small" type="danger" @click="handleDelete(row)">{{ t("common.delete") }}</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer
      v-model="detailVisible"
      :title="activeImage?.title || activeImage?.id || t('docs.view')"
      size="58%"
      direction="rtl"
      class="dark-drawer"
    >
      <div v-if="detailLoading" class="detail-loading">
        <el-icon class="is-loading" style="font-size:32px"><Loading /></el-icon>
        <p>{{ t("common.loading") }}</p>
      </div>
      <template v-else-if="activeImage">
        <div class="image-detail-top">
          <div class="image-stage">
            <img :src="getImageSrc(activeImage.file_path)" :alt="activeImage.title || activeImage.id" class="detail-image" />
          </div>
          <div class="image-meta-panel">
            <el-descriptions :column="1" border class="dark-descriptions">
              <el-descriptions-item :label="t('kb.description')">
                {{ activeImage.generated_description || "-" }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('kb.source')">
                {{ activeImage.source_dataset || "-" }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('docs.uploadTime')">
                {{ formatDateTime(activeImage.upload_time) }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('kb.tags')">
                {{ formatTags(activeImage.tags) }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </div>

        <el-tabs v-model="detailTab">
          <el-tab-pane :label="t('docs.view')" name="overview">
            <div class="version-hint">{{ t("kb.versionHint") }}</div>
          </el-tab-pane>
          <el-tab-pane :label="t('kb.versionTab')" name="versions">
            <div class="version-toolbar">
              <el-upload
                :auto-upload="false"
                :show-file-list="false"
                accept="image/*"
                :on-change="handleVersionFileChange"
              >
                <el-button type="primary" :loading="versionUploading">
                  <i class="i-ep-upload mr-2"></i>
                  {{ t("kb.uploadNewVersion") }}
                </el-button>
              </el-upload>
            </div>
            <el-table v-loading="versionsLoading" :data="imageVersions" stripe class="dark-table">
              <el-table-column :label="t('kb.versionNumber')" width="100" align="center">
                <template #default="{ row }">v{{ row.version_number || 1 }}</template>
              </el-table-column>
              <el-table-column :label="t('kb.latestVersion')" width="110" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.is_latest" type="success">{{ t("kb.latestVersion") }}</el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('docs.uploadTime')" width="180">
                <template #default="{ row }">{{ formatDateTime(row.upload_time) }}</template>
              </el-table-column>
              <el-table-column prop="title" :label="t('kb.titleColumn')" min-width="140" show-overflow-tooltip>
                <template #default="{ row }">{{ row.title || row.id }}</template>
              </el-table-column>
              <el-table-column prop="status" :label="t('kb.status')" width="120" />
              <el-table-column :label="t('kb.contentHash')" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">{{ shortenHash(row.content_hash) }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-drawer>

    <el-dialog v-model="editVisible" :title="t('kb.editTitle')" width="520px">
      <el-form label-position="top">
        <el-form-item :label="t('kb.titleColumn')">
          <el-input v-model="editForm.title" />
        </el-form-item>
        <el-form-item :label="t('kb.tags')">
          <el-input v-model="editForm.tagsText" :placeholder="t('kb.tagsTip')" />
        </el-form-item>
        <el-form-item :label="t('kb.source')">
          <el-input v-model="editForm.source_dataset" />
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
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Loading } from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";
import {
  deleteImage,
  listImages,
  listImageVersions,
  reprocessImage,
  updateImage,
  uploadImageVersion,
  uploadImages,
  type ImageRecord,
} from "@/api/kb";
import ImageCard from "@/components/ImageCard.vue";
import UploadZone from "@/components/UploadZone.vue";
import { imgSrc } from "@/utils/image";

const { t } = useI18n();

// ---- 上传与列表状态 ----
const fileList = ref<File[]>([]);
const images = ref<ImageRecord[]>([]);
const uploading = ref(false);
const loading = ref(false);
const saving = ref(false);
const versionUploading = ref(false);
const versionsLoading = ref(false);
const viewMode = ref<"grid" | "table">("grid");

// ---- 详情抽屉状态 ----
const detailVisible = ref(false);
const detailLoading = ref(false);
const activeImage = ref<ImageRecord | null>(null);
const imageVersions = ref<ImageRecord[]>([]);
const detailTab = ref<"overview" | "versions">("overview");

// ---- 编辑弹窗状态 ----
const editVisible = ref(false);
const currentImageId = ref<string>("");

// ---- 图片列表过滤条件 ----
const filters = reactive({
  keyword: "",
  status: "",
  enabled: undefined as boolean | undefined,
  tag: "",
});

// ---- 编辑表单数据 ----
const editForm = reactive({
  title: "",
  tagsText: "",
  notes: "",
  enabled: true,
  source_dataset: "",
});

// ---- 工具函数 ----

/** 将文件路径转换为可显示的图片 URL */
function getImageSrc(filePath: string): string {
  return imgSrc(filePath);
}

/** 将标签数组格式化为逗号分隔字符串 */
function formatTags(tags?: string[]) {
  return tags?.length ? tags.join(", ") : "-";
}

/** 将日期时间字符串格式化为本地显示格式 */
function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

/** 截断并缩写哈希值用于展示 */
function shortenHash(value?: string | null): string {
  if (!value) return "-";
  return value.length > 16 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

/** 加载指定图片的所有版本记录 */
async function loadImageVersions(imageId: string) {
  try {
    versionsLoading.value = true;
    imageVersions.value = await listImageVersions(imageId);
  } catch (error) {
    console.error("加载图片版本失败:", error);
    ElMessage.error(t("kb.versionLoadFailed"));
  } finally {
    versionsLoading.value = false;
  }
}

/** 打开图片详情抽屉，加载版本列表并定位到最新版本 */
async function openDetails(img: ImageRecord) {
  detailVisible.value = true;
  detailLoading.value = true;
  detailTab.value = "overview";
  activeImage.value = img;
  try {
    await loadImageVersions(img.id);
    const latest = imageVersions.value.find((item) => item.is_latest) || img;
    activeImage.value = latest;
  } finally {
    detailLoading.value = false;
  }
}

/** 打开图片编辑弹窗，填充当前图片信息 */
function openEdit(img: ImageRecord) {
  currentImageId.value = img.id;
  editForm.title = img.title || "";
  editForm.tagsText = img.tags?.join(", ") || "";
  editForm.notes = img.notes || "";
  editForm.enabled = img.enabled ?? true;
  editForm.source_dataset = img.source_dataset || "";
  editVisible.value = true;
}

// ---- 核心操作方法 ----

/** 根据过滤条件加载图片列表 */
async function loadImages() {
  try {
    loading.value = true;
    images.value = await listImages({
      keyword: filters.keyword || undefined,
      status: filters.status || undefined,
      enabled: filters.enabled,
      tag: filters.tag || undefined,
    });
  } catch (e) {
    console.error("加载图片列表失败:", e);
    ElMessage.error(t("kb.loadFailed"));
  } finally {
    loading.value = false;
  }
}

// ---- 生命周期 ----
onMounted(loadImages);

/** 上传选中的图片文件，成功后刷新列表 */
async function doUpload() {
  if (!fileList.value.length) {
    ElMessage.warning(t("kb.selectFiles"));
    return;
  }
  try {
    uploading.value = true;
    await uploadImages(fileList.value);
    await loadImages();
    ElMessage.success(t("kb.uploadSuccess"));
    fileList.value = [];
  } catch (e) {
    console.error("上传失败:", e);
    ElMessage.error(t("kb.uploadFailed"));
  } finally {
    uploading.value = false;
  }
}

/** 提交图片编辑（标题、标签、备注、启用状态、数据来源） */
async function submitEdit() {
  try {
    saving.value = true;
    const updated = await updateImage(currentImageId.value, {
      title: editForm.title || null,
      tags: editForm.tagsText.split(",").map((item) => item.trim()).filter(Boolean),
      notes: editForm.notes || null,
      enabled: editForm.enabled,
      source_dataset: editForm.source_dataset || null,
    });
    ElMessage.success(t("kb.updateSuccess"));
    editVisible.value = false;
    await loadImages();
    if (activeImage.value?.id === updated.id) {
      activeImage.value = updated;
      await loadImageVersions(updated.id);
    }
  } catch (e) {
    console.error("更新图片失败:", e);
    ElMessage.error(t("kb.updateFailed"));
  } finally {
    saving.value = false;
  }
}

/** 删除图片（含二次确认），同时关闭已打开的详情抽屉 */
async function handleDelete(img: ImageRecord) {
  await ElMessageBox.confirm(
    t("kb.deleteConfirm", { title: img.title || img.id }),
    t("common.confirm"),
    { type: "warning" }
  );
  try {
    await deleteImage(img.id);
    ElMessage.success(t("kb.deleteSuccess"));
    if (activeImage.value?.id === img.id) {
      detailVisible.value = false;
      activeImage.value = null;
      imageVersions.value = [];
    }
    await loadImages();
  } catch (e) {
    console.error("删除图片失败:", e);
    ElMessage.error(t("kb.deleteFailed"));
  }
}

/** 重新处理图片（触发后端重新生成描述和向量） */
async function handleReprocess(img: ImageRecord) {
  try {
    await reprocessImage(img.id);
    ElMessage.success(t("kb.reprocessSuccess"));
    await loadImages();
    if (activeImage.value?.id === img.id) {
      await loadImageVersions(img.id);
    }
  } catch (e) {
    console.error("重处理图片失败:", e);
    ElMessage.error(t("kb.reprocessFailed"));
  }
}

/** 上传图片新版本文件，刷新版本列表并切换到最新版本 */
async function handleVersionFileChange(uploadFile: { raw?: File }) {
  if (!uploadFile.raw || !activeImage.value) return;
  try {
    versionUploading.value = true;
    const response = await uploadImageVersion(activeImage.value.id, uploadFile.raw);
    ElMessage.success(t("kb.versionUploadSuccess"));
    await loadImages();
    await loadImageVersions(activeImage.value.id);
    activeImage.value = response.images[0] || imageVersions.value.find((item) => item.is_latest) || activeImage.value;
    detailTab.value = "versions";
  } catch (error) {
    console.error("上传图片新版本失败:", error);
    ElMessage.error(t("kb.versionUploadFailed"));
  } finally {
    versionUploading.value = false;
  }
}

/** 将图片处理状态映射为 Element Plus Tag 类型 */
function statusTagType(status: string) {
  if (status === "Completed") return "success";
  if (status === "Failed") return "danger";
  return "warning";
}

/** 将状态枚举值翻译为国际化显示文本 */
function statusLabel(status: string) {
  switch (status) {
    case "Processing": return t("kb.processing");
    case "Completed": return t("kb.completed");
    case "Failed": return t("kb.failed");
    default: return status;
  }
}
</script>

<style scoped>
.kb-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.upload-card {
  margin-bottom: 0;
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

.images-card {
  margin-bottom: 0;
}

.card-header,
.header-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.filter-bar {
  display: grid;
  grid-template-columns: minmax(220px, 2fr) repeat(3, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 18px;
}

.grid-item {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.grid-meta,
.grid-actions,
.row-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.meta-text {
  font-family: monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.dark-table {
  --el-table-bg-color: var(--surface-card);
  --el-table-tr-bg-color: var(--surface-card);
  --el-table-header-bg-color: var(--bg-tertiary);
  --el-table-header-text-color: var(--text-primary);
  --el-table-text-color: var(--text-secondary);
  --el-table-row-hover-bg-color: var(--bg-accent-soft);
  --el-table-border-color: var(--border-color);
}

.images-card :deep(.el-card__body) {
  padding: 22px;
}

@media (max-width: 960px) {
  .upload-entry-row {
    grid-template-columns: 1fr;
  }

  .upload-btn {
    width: 100%;
  }
}

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-primary);
  animation: pulse-glow 1.5s ease-in-out infinite;
}

.status-processing {
  --el-tag-bg-color: rgba(0, 212, 255, 0.1);
  --el-tag-border-color: rgba(0, 212, 255, 0.3);
  --el-tag-text-color: var(--accent-primary);
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

.detail-loading {
  text-align: center;
  padding: 40px;
}

.image-detail-top {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(260px, 0.8fr);
  gap: 18px;
  margin-bottom: 18px;
}

.image-stage {
  padding: 18px;
  border-radius: 20px;
  background: var(--surface-panel-muted);
  border: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
}

.detail-image {
  max-width: 100%;
  max-height: 360px;
  object-fit: contain;
  border-radius: 12px;
}

.image-meta-panel {
  display: flex;
  flex-direction: column;
}

.version-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 14px;
}

.version-hint {
  padding: 14px;
  border-radius: 14px;
  background: var(--surface-card);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
}

@media (max-width: 900px) {
  .filter-bar,
  .image-detail-top {
    grid-template-columns: 1fr;
  }
}
</style>
