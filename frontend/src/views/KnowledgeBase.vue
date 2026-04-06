<template>
  <div class="kb-page">
    <el-card class="upload-card glass-card">
      <template #header>
        <div class="card-header">
          <span>{{ t("kb.title") }}</span>
        </div>
      </template>

      <UploadZone
        v-model:files="fileList"
        :text="t('kb.uploadArea')"
        :accept="'image/*'"
        :multiple="true"
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
            @click="openPreview(img)"
          />
          <div class="grid-meta">
            <el-tag size="small" :type="img.enabled ? 'success' : 'info'">
              {{ img.enabled ? t("kb.enabled") : t("kb.disabled") }}
            </el-tag>
            <span class="meta-text">{{ formatTags(img.tags) }}</span>
          </div>
          <div class="grid-actions">
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
              <el-button size="small" @click="openPreview(row)">{{ t("docs.view") }}</el-button>
              <el-button size="small" @click="openEdit(row)">{{ t("common.edit") }}</el-button>
              <el-button size="small" @click="handleReprocess(row)">{{ t("kb.reprocess") }}</el-button>
              <el-button size="small" type="danger" @click="handleDelete(row)">{{ t("common.delete") }}</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <ImagePreviewModal
      v-model:visible="previewVisible"
      :src="previewImage?.file_path ? getImageSrc(previewImage.file_path) : ''"
      :title="previewImage?.title || previewImage?.id"
      :description="previewImage?.generated_description || ''"
      :id="previewImage?.id"
      :upload-time="previewImage?.upload_time"
    />

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
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  deleteImage,
  listImages,
  reprocessImage,
  updateImage,
  uploadImages,
  type ImageRecord,
} from "@/api/kb";
import ImageCard from "@/components/ImageCard.vue";
import ImagePreviewModal from "@/components/ImagePreviewModal.vue";
import UploadZone from "@/components/UploadZone.vue";
import { imgSrc } from "@/utils/image";

const { t } = useI18n();

const fileList = ref<File[]>([]);
const images = ref<ImageRecord[]>([]);
const uploading = ref(false);
const loading = ref(false);
const saving = ref(false);
const viewMode = ref<"grid" | "table">("grid");
const previewVisible = ref(false);
const previewImage = ref<ImageRecord | null>(null);
const editVisible = ref(false);
const currentImageId = ref<string>("");

const filters = reactive({
  keyword: "",
  status: "",
  enabled: undefined as boolean | undefined,
  tag: "",
});

const editForm = reactive({
  title: "",
  tagsText: "",
  notes: "",
  enabled: true,
  source_dataset: "",
});

function getImageSrc(filePath: string): string {
  return imgSrc(filePath);
}

function formatTags(tags?: string[]) {
  return tags?.length ? tags.join(", ") : "-";
}

function openPreview(img: ImageRecord) {
  previewImage.value = img;
  previewVisible.value = true;
}

function openEdit(img: ImageRecord) {
  currentImageId.value = img.id;
  editForm.title = img.title || "";
  editForm.tagsText = img.tags?.join(", ") || "";
  editForm.notes = img.notes || "";
  editForm.enabled = img.enabled ?? true;
  editForm.source_dataset = img.source_dataset || "";
  editVisible.value = true;
}

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

onMounted(loadImages);

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

async function submitEdit() {
  try {
    saving.value = true;
    await updateImage(currentImageId.value, {
      title: editForm.title || null,
      tags: editForm.tagsText.split(",").map((item) => item.trim()).filter(Boolean),
      notes: editForm.notes || null,
      enabled: editForm.enabled,
      source_dataset: editForm.source_dataset || null,
    });
    ElMessage.success(t("kb.updateSuccess"));
    editVisible.value = false;
    await loadImages();
  } catch (e) {
    console.error("更新图片失败:", e);
    ElMessage.error(t("kb.updateFailed"));
  } finally {
    saving.value = false;
  }
}

async function handleDelete(img: ImageRecord) {
  await ElMessageBox.confirm(
    t("kb.deleteConfirm", { title: img.title || img.id }),
    t("common.confirm"),
    { type: "warning" }
  );
  try {
    await deleteImage(img.id);
    ElMessage.success(t("kb.deleteSuccess"));
    if (previewImage.value?.id === img.id) {
      previewVisible.value = false;
      previewImage.value = null;
    }
    await loadImages();
  } catch (e) {
    console.error("删除图片失败:", e);
    ElMessage.error(t("kb.deleteFailed"));
  }
}

async function handleReprocess(img: ImageRecord) {
  try {
    await reprocessImage(img.id);
    ElMessage.success(t("kb.reprocessSuccess"));
    await loadImages();
  } catch (e) {
    console.error("重处理图片失败:", e);
    ElMessage.error(t("kb.reprocessFailed"));
  }
}

function statusTagType(status: string) {
  if (status === "Completed") return "success";
  if (status === "Failed") return "danger";
  return "warning";
}

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
  max-width: 1400px;
  margin: 0 auto;
}

.upload-card {
  margin-bottom: 24px;
}

.upload-btn {
  margin-top: 16px;
  width: 100%;
  background: var(--accent-gradient);
  border: none;
}

.images-card {
  margin-bottom: 24px;
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
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
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

.meta-text,
.path-text {
  font-family: monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.dark-table {
  --el-table-bg-color: var(--bg-secondary);
  --el-table-tr-bg-color: var(--bg-secondary);
  --el-table-header-bg-color: var(--bg-tertiary);
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
</style>
