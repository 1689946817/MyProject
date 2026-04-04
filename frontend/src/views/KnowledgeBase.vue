<template>
  <div class="kb-page">
    <!-- 上传区域 -->
    <el-card class="upload-card glass-card">
      <template #header>
        <div class="card-header">
          <span>{{ t('kb.title') }}</span>
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
        {{ t('kb.uploadBtn') }}
      </el-button>
    </el-card>

    <!-- 已上传图片 -->
    <el-card class="images-card glass-card">
      <template #header>
        <div class="card-header">
          <span>{{ t('kb.uploadedImages') }}</span>
          <div class="view-toggle">
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

      <!-- 网格视图 -->
      <div v-if="viewMode === 'grid'" class="image-grid">
        <ImageCard
          v-for="img in images"
          :key="img.id"
          :src="getImageSrc(img.file_path)"
          :title="img.id"
          :description="img.generated_description || ''"
          :status="img.status"
          @click="openPreview(img)"
        />
        <el-empty v-if="images.length === 0" :description="t('kb.noImages')" />
      </div>

      <!-- 表格视图 -->
      <el-table v-else v-loading="loading" :data="images" height="400" class="dark-table">
        <el-table-column prop="id" label="ID" width="260" show-overflow-tooltip />
        <el-table-column prop="file_path" label="路径" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="path-text">{{ row.file_path }}</span>
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
        <el-table-column :label="t('kb.description')" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.generated_description }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 图片预览 -->
    <ImagePreviewModal
      v-model:visible="previewVisible"
      :src="previewImage?.file_path ? getImageSrc(previewImage.file_path) : ''"
      :title="previewImage?.id"
      :description="previewImage?.generated_description || ''"
      :id="previewImage?.id"
      :upload-time="previewImage?.upload_time"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { listImages, uploadImages, type ImageRecord } from '@/api/kb'
import { imgSrc } from '@/utils/image'
import UploadZone from '@/components/UploadZone.vue'
import ImageCard from '@/components/ImageCard.vue'
import ImagePreviewModal from '@/components/ImagePreviewModal.vue'

const { t } = useI18n()

const fileList = ref<File[]>([])
const images = ref<ImageRecord[]>([])
const uploading = ref(false)
const loading = ref(false)
const viewMode = ref<'grid' | 'table'>('grid')
const previewVisible = ref(false)
const previewImage = ref<ImageRecord | null>(null)

function getImageSrc(filePath: string): string {
  return imgSrc(filePath)
}

function openPreview(img: ImageRecord) {
  previewImage.value = img
  previewVisible.value = true
}

async function loadImages() {
  try {
    loading.value = true
    const data = await listImages()
    images.value = data
  } catch (e) {
    console.error('加载图片列表失败:', e)
    ElMessage.error(t('kb.loadFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadImages()
})

async function doUpload() {
  if (!fileList.value.length) {
    ElMessage.warning(t('kb.selectFiles'))
    return
  }
  try {
    uploading.value = true
    await uploadImages(fileList.value)
    await loadImages()
    ElMessage.success(t('kb.uploadSuccess'))
    fileList.value = []
  } catch (e) {
    console.error('上传失败:', e)
    ElMessage.error(t('kb.uploadFailed'))
  } finally {
    uploading.value = false
  }
}

function statusTagType(status: string) {
  if (status === 'Completed') return 'success'
  if (status === 'Failed') return 'danger'
  return 'warning'
}

function statusLabel(status: string) {
  switch (status) {
    case 'Processing': return t('kb.processing')
    case 'Completed': return t('kb.completed')
    case 'Failed': return t('kb.failed')
    default: return status
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

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.view-toggle {
  display: flex;
  gap: 8px;
}

/* 网格视图 */
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 20px;
}

/* 表格样式 */
.dark-table {
  --el-table-bg-color: var(--bg-secondary);
  --el-table-tr-bg-color: var(--bg-secondary);
  --el-table-header-bg-color: var(--bg-tertiary);
}

.path-text {
  font-family: monospace;
  font-size: 12px;
}

/* 状态标签 */
.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
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
