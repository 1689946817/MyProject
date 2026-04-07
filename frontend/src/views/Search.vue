<template>
  <div class="search-page">
    <div class="page-intro">
      <div class="page-intro-main">
        <h1 class="page-title">{{ t("search.title") }}</h1>
        <p class="page-subtitle">{{ t("search.subtitle") }}</p>
      </div>
    </div>
    <el-row :gutter="20">
      <!-- 文本检索 -->
      <el-col :span="12">
        <el-card class="search-card glass-card">
          <template #header>
            <div class="card-header">
              <i class="i-ep-search mr-2 accent-icon"></i>
              <span>{{ t('search.textToImage') }}</span>
            </div>
          </template>

          <el-input
            v-model="textQuery"
            :placeholder="t('search.textQueryPlaceholder')"
            type="textarea"
            :rows="3"
            class="dark-input"
          />

          <el-button
            type="primary"
            class="search-btn"
            :loading="loadingText"
            @click="doTextSearch"
          >
            <i class="i-ep-search mr-2"></i>
            {{ t('search.searchBtn') }}
          </el-button>

          <el-divider />

          <!-- 文本检索结果 -->
          <div class="results-section">
            <h4 class="section-title">
              <span v-if="textResults.length > 0">{{ t('search.similarity') }} ({{ textResults.length }})</span>
              <span v-else>{{ t('search.noResults') }}</span>
            </h4>
            <div v-if="textResults.length > 0" class="result-grid">
              <div v-for="item in textResults" :key="item.id" class="search-image-item">
                <div v-if="resultBadgeVisible(item)" class="search-image-badges">
                  <el-tag v-if="assetTypeLabel(item)" size="small" type="primary" effect="dark">
                    {{ assetTypeLabel(item) }}
                  </el-tag>
                  <el-tag v-if="pageLabel(item)" size="small" effect="plain">
                    {{ pageLabel(item) }}
                  </el-tag>
                  <el-tag v-if="isCrossPageResult(item)" size="small" type="warning" effect="plain">
                    {{ t("docs.crossPageContinued") }}
                  </el-tag>
                </div>
                <ImageCard
                  :src="getImageSrc(item.file_path || '')"
                  :title="item.id"
                  :description="item.description"
                  :score="clampScore(item.score)"
                  @click="openPreview(item)"
                />
              </div>
            </div>
            <el-empty v-else-if="!loadingText" :description="t('search.noResults')" />
          </div>
        </el-card>
      </el-col>

      <!-- 以图搜图 -->
      <el-col :span="12">
        <el-card class="search-card glass-card">
          <template #header>
            <div class="card-header">
              <i class="i-ep-picture mr-2 accent-icon"></i>
              <span>{{ t('search.imageToImage') }}</span>
            </div>
          </template>

          <UploadZone
            v-model:files="imageFiles"
            :text="t('search.imageQueryPlaceholder')"
            :accept="'image/*'"
            :multiple="false"
          />

          <el-button
            type="primary"
            class="search-btn"
            :loading="loadingImage"
            @click="doImageSearch"
          >
            <i class="i-ep-picture mr-2"></i>
            {{ t('search.imageSearchBtn') }}
          </el-button>

          <!-- MLLM 生成的查询描述 -->
          <div v-if="imageQueryDescription" class="query-desc-card">
            <div class="query-desc-header">
              <i class="i-ep-bot mr-2"></i>
              <span>{{ t('search.queryDescription') }}</span>
            </div>
            <p class="query-desc-text">{{ imageQueryDescription }}</p>
          </div>

          <el-divider />

          <!-- 图像检索结果 -->
          <div class="results-section">
            <h4 class="section-title">
              <span v-if="imageResults.length > 0">{{ t('search.similarity') }} ({{ imageResults.length }})</span>
              <span v-else>{{ t('search.noResults') }}</span>
            </h4>
            <div v-if="imageResults.length > 0" class="result-grid">
              <div v-for="item in imageResults" :key="item.id" class="search-image-item">
                <div v-if="resultBadgeVisible(item)" class="search-image-badges">
                  <el-tag v-if="assetTypeLabel(item)" size="small" type="primary" effect="dark">
                    {{ assetTypeLabel(item) }}
                  </el-tag>
                  <el-tag v-if="pageLabel(item)" size="small" effect="plain">
                    {{ pageLabel(item) }}
                  </el-tag>
                  <el-tag v-if="isCrossPageResult(item)" size="small" type="warning" effect="plain">
                    {{ t("docs.crossPageContinued") }}
                  </el-tag>
                </div>
                <ImageCard
                  :src="getImageSrc(item.file_path || '')"
                  :title="item.id"
                  :description="item.description"
                  :score="clampScore(item.score)"
                  @click="openPreview(item)"
                />
              </div>
            </div>
            <el-empty v-else-if="!loadingImage" :description="t('search.noResults')" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图片预览 -->
    <ImagePreviewModal
      v-model:visible="previewVisible"
      :src="previewItem?.file_path ? getImageSrc(previewItem.file_path) : ''"
      :title="previewItem?.id"
      :description="previewItem?.description"
      :id="previewItem?.id"
      :score="previewItem ? clampScore(previewItem.score) : undefined"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  textToImageSearch,
  imageToImageSearch,
  type SearchResultItem
} from '@/api/search'
import { imgSrc } from '@/utils/image'
import UploadZone from '@/components/UploadZone.vue'
import ImageCard from '@/components/ImageCard.vue'
import ImagePreviewModal from '@/components/ImagePreviewModal.vue'

const { t } = useI18n()

const textQuery = ref('')
const textResults = ref<SearchResultItem[]>([])
const loadingText = ref(false)

const imageFiles = ref<File[]>([])
const imageResults = ref<SearchResultItem[]>([])
const imageQueryDescription = ref('')
const loadingImage = ref(false)

const previewVisible = ref(false)
const previewItem = ref<SearchResultItem | null>(null)

function clampScore(score: number): number {
  return Math.max(0, Math.min(1, 1 - score))
}

function getErrorMessage(error: any, fallback: string): string {
  return error?.response?.data?.detail || error?.message || fallback
}

function getImageSrc(filePath: string): string {
  return imgSrc(filePath)
}

function openPreview(item: SearchResultItem) {
  previewItem.value = item
  previewVisible.value = true
}

function assetTypeLabel(item: SearchResultItem): string {
  if (item.asset_type === 'table_crop') return t('docs.tableCrop')
  if (item.asset_type === 'table_page_render') return t('docs.tablePageRender')
  if (item.asset_type === 'page_render') return t('docs.pageRender')
  return ''
}

function pageLabel(item: SearchResultItem): string {
  if (typeof item.page_number === 'number') {
    return t('docs.pageLabel', { page: item.page_number })
  }
  return ''
}

function isCrossPageResult(item: SearchResultItem): boolean {
  return Boolean(item.continued_from_previous_page || item.continued_to_next_page)
}

function resultBadgeVisible(item: SearchResultItem): boolean {
  return Boolean(assetTypeLabel(item) || pageLabel(item) || isCrossPageResult(item))
}

async function doTextSearch() {
  if (!textQuery.value.trim()) {
    ElMessage.warning(t('search.enterQuery'))
    return
  }
  try {
    loadingText.value = true
    const resp = await textToImageSearch(textQuery.value, 10)
    textResults.value = resp.results
  } catch (e) {
    textResults.value = []
    ElMessage.error(getErrorMessage(e, t('search.textSearchFailed')))
  } finally {
    loadingText.value = false
  }
}

async function doImageSearch() {
  const file = imageFiles.value[0]
  if (!file) {
    ElMessage.warning(t('search.selectImage'))
    return
  }
  try {
    loadingImage.value = true
    const resp = await imageToImageSearch(file, 10)
    imageQueryDescription.value = resp.query_description
    imageResults.value = resp.results
  } catch (e) {
    imageQueryDescription.value = ''
    imageResults.value = []
    ElMessage.error(getErrorMessage(e, t('search.imageSearchFailed')))
  } finally {
    loadingImage.value = false
  }
}
</script>

<style scoped>
.search-page {
  max-width: 1400px;
  margin: 0 auto;
}

.search-card {
  height: calc(100vh - 220px);
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  align-items: center;
}

.accent-icon {
  color: var(--accent-primary);
  font-size: 18px;
}

.dark-input :deep(.el-textarea__inner) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
}

.dark-input :deep(.el-textarea__inner:focus) {
  border-color: var(--accent-primary);
}

.search-btn {
  margin-top: 16px;
  width: 100%;
}

.results-section {
  flex: 1;
  overflow-y: auto;
}

.section-title {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0 0 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.search-image-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.search-image-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* MLLM 查询描述卡片 */
.query-desc-card {
  margin-top: 16px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 14px;
  border: 1px solid var(--border-color);
}

.query-desc-header {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: var(--accent-primary);
  margin-bottom: 8px;
}

.query-desc-text {
  font-size: 13px;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.5;
}
</style>
