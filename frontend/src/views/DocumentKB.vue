<template>
  <div class="doc-kb">
    <!-- 上传区域 -->
    <el-card class="glass-card">
      <template #header>
        <div class="card-header">
          <i class="i-ep-document mr-2 accent-icon"></i>
          <span>{{ t('docs.title') }}</span>
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
        {{ t('docs.uploadBtn') }}
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

    <!-- 文档列表 -->
    <el-card class="glass-card" style="margin-top: 24px">
      <template #header>
        <div class="card-header">
          <span>{{ t('docs.uploadedDocs') }}</span>
          <el-button size="small" @click="loadDocList">
            <i class="i-ep-refresh mr-1"></i>
            {{ t('docs.refresh') }}
          </el-button>
        </div>
      </template>
      <el-table v-loading="loadingList" :data="docList" stripe class="dark-table">
        <el-table-column prop="file_name" :label="t('docs.fileName')" min-width="160" show-overflow-tooltip />
        <el-table-column :label="t('docs.uploadTime')" width="180">
          <template #default="{ row }">
            {{ new Date(row.upload_time).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column :label="t('docs.status')" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" :class="'status-' + row.status.toLowerCase()">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('docs.chunks')" width="90" align="center" prop="chunk_count" />
        <el-table-column :label="t('docs.images')" width="80" align="center" prop="image_count" />
        <el-table-column :label="t('docs.action')" width="100" align="center">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              :disabled="row.status !== 'Completed'"
              @click="viewResult(row)"
            >
              {{ t('docs.view') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 解析结果抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="activeDoc?.file_name || '解析结果'"
      size="60%"
      direction="rtl"
      class="dark-drawer"
    >
      <div v-if="loadingResult" style="text-align:center;padding:40px">
        <el-icon class="is-loading" style="font-size:32px"><Loading /></el-icon>
        <p>{{ t('common.loading') }}</p>
      </div>
      <template v-else-if="parseResult">
        <!-- 统计信息 -->
        <el-descriptions :column="3" border style="margin-bottom: 20px" class="dark-descriptions">
          <el-descriptions-item :label="t('docs.chunks')">{{ parseResult.chunks.length }}</el-descriptions-item>
          <el-descriptions-item :label="t('docs.images')">{{ parseResult.images.length }}</el-descriptions-item>
          <el-descriptions-item :label="t('docs.status')">
            <el-tag :type="statusType(parseResult.document.status)">{{ parseResult.document.status }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 文本片段 -->
        <el-divider content-position="left">{{ t('docs.chunksTitle') }}（{{ parseResult.chunks.length }} 条）</el-divider>
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

        <!-- 提取的图片 -->
        <el-divider content-position="left">{{ t('docs.imagesTitle') }}（{{ parseResult.images.length }} 张）</el-divider>
        <div class="images-grid">
          <ImageCard
            v-for="img in parseResult.images"
            :key="img.id"
            :src="imgSrc(img.file_path)"
            :title="img.id"
            :description="img.generated_description || ''"
            :status="img.status"
          />
          <el-empty v-if="parseResult.images.length === 0" :description="t('docs.noImages')" />
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import {
  uploadDocument,
  listDocuments,
  getDocResult,
  type DocumentRecord,
  type DocParseResult,
} from '@/api/docs'
import { imgSrc } from '@/utils/image'
import UploadZone from '@/components/UploadZone.vue'
import ImageCard from '@/components/ImageCard.vue'

const { t } = useI18n()

// 上传
const selectedFiles = ref<File[]>([])
const selectedFile = computed(() => selectedFiles.value[0] || null)
const uploading = ref(false)
const uploadMsg = ref('')
const uploadSuccess = ref(false)

async function doUpload() {
  if (!selectedFile.value) return
  uploading.value = true
  uploadMsg.value = ''
  try {
    const res = await uploadDocument(selectedFile.value)
    uploadSuccess.value = true
    uploadMsg.value = res.message || t('docs.uploadSuccess')
    selectedFiles.value = []
    await loadDocList()
  } catch (e: any) {
    uploadSuccess.value = false
    uploadMsg.value = e?.response?.data?.detail || t('docs.uploadFailed')
  } finally {
    uploading.value = false
  }
}

// 文档列表
const docList = ref<DocumentRecord[]>([])
const loadingList = ref(false)

async function loadDocList() {
  loadingList.value = true
  try {
    docList.value = await listDocuments()
  } catch {
    ElMessage.error(t('docs.loadFailed'))
  } finally {
    loadingList.value = false
  }
}

onMounted(loadDocList)

function statusType(status: string) {
  if (status === 'Completed') return 'success'
  if (status === 'Failed') return 'danger'
  return 'warning'
}

// 查看解析结果
const drawerVisible = ref(false)
const activeDoc = ref<DocumentRecord | null>(null)
const parseResult = ref<DocParseResult | null>(null)
const loadingResult = ref(false)

async function viewResult(doc: DocumentRecord) {
  activeDoc.value = doc
  drawerVisible.value = true
  loadingResult.value = true
  parseResult.value = null
  try {
    parseResult.value = await getDocResult(doc.id)
  } catch {
    ElMessage.error(t('docs.loadResultFailed'))
  } finally {
    loadingResult.value = false
  }
}
</script>

<style scoped>
.doc-kb {
  max-width: 1100px;
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

/* 表格 */
.dark-table {
  --el-table-bg-color: var(--bg-secondary);
  --el-table-tr-bg-color: var(--bg-secondary);
  --el-table-header-bg-color: var(--bg-tertiary);
}

/* 状态标签 */
.status-tag {
  display: inline-flex;
  align-items: center;
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

/* 抽屉 */
.dark-drawer :deep(.el-drawer__header) {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 0;
}

.dark-drawer :deep(.el-drawer__body) {
  background: var(--bg-primary);
}

/* 描述列表 */
.dark-descriptions :deep(.el-descriptions__label) {
  background: var(--bg-tertiary);
}

/* 片段容器 */
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

/* 图片网格 */
.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}
</style>
