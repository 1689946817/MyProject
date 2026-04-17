<template>
  <div class="search-page">
    <div class="page-intro">
      <div class="page-intro-main">
        <h1 class="page-title">{{ t("search.title") }}</h1>
        <p class="page-subtitle">{{ t("search.subtitle") }}</p>
      </div>
    </div>

    <el-row :gutter="20" class="search-layout">
      <el-col :xs="24" :lg="12">
        <el-card class="search-card glass-card">
          <template #header>
            <div class="card-header">
              <i class="i-ep-search mr-2 accent-icon"></i>
              <span>{{ t("search.textToImage") }}</span>
            </div>
          </template>

          <el-input
            v-model="textQuery"
            :placeholder="t('search.textQueryPlaceholder')"
            type="textarea"
            :rows="3"
            class="dark-input"
          />

          <div class="advanced-toggle-row">
            <el-button text class="advanced-toggle" @click="textPanelOpen = !textPanelOpen">
              <i :class="textPanelOpen ? 'i-ep-arrow-up-bold' : 'i-ep-arrow-down-bold'"></i>
              <span>{{ t("search.advancedSettings") }}</span>
              <span class="advanced-summary">{{ textSummary }}</span>
            </el-button>
          </div>

          <el-collapse-transition>
            <div v-show="textPanelOpen" class="advanced-panel">
              <div class="advanced-grid">
                <div class="advanced-item">
                  <span class="advanced-label">{{ t("search.topK") }}</span>
                  <el-input-number v-model="textTopK" :min="1" :max="50" />
                </div>
                <div class="advanced-item switch-item">
                  <span class="advanced-label">{{ t("search.enableScoreFilter") }}</span>
                  <el-switch v-model="textEnableScoreFilter" />
                </div>
                <div class="advanced-item">
                  <span class="advanced-label">{{ t("search.minRelevanceScore") }}</span>
                  <el-input-number
                    v-model="textMinRelevanceScore"
                    :step="0.1"
                    :precision="3"
                    :disabled="!textEnableScoreFilter"
                  />
                </div>
              </div>
            </div>
          </el-collapse-transition>

          <el-button
            type="primary"
            class="search-btn"
            :loading="loadingText"
            @click="doTextSearch"
          >
            <i class="i-ep-search mr-2"></i>
            {{ t("search.searchBtn") }}
          </el-button>

          <el-divider />

          <div class="results-section">
            <div class="results-head">
              <h4 class="section-title">
                <span v-if="textResults.length > 0">{{ t("search.similarity") }} ({{ textResults.length }})</span>
                <span v-else>{{ t("search.noResults") }}</span>
              </h4>
              <el-alert
                v-if="textFilterNotice"
                :title="textFilterNotice"
                type="info"
                :closable="false"
                show-icon
                class="inline-alert"
              />
            </div>
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
                  :score-label="getScoreLabel(item)"
                  @click="openPreview(item)"
                />
              </div>
            </div>
            <el-empty v-else-if="!loadingText" :description="t('search.noResults')" />
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card class="search-card glass-card">
          <template #header>
            <div class="card-header">
              <i class="i-ep-picture mr-2 accent-icon"></i>
              <span>{{ t("search.imageToImage") }}</span>
            </div>
          </template>

          <UploadZone
            v-model:files="imageFiles"
            :text="t('search.imageQueryPlaceholder')"
            :accept="'image/*'"
            :multiple="false"
          />

          <div class="advanced-toggle-row">
            <el-button text class="advanced-toggle" @click="imagePanelOpen = !imagePanelOpen">
              <i :class="imagePanelOpen ? 'i-ep-arrow-up-bold' : 'i-ep-arrow-down-bold'"></i>
              <span>{{ t("search.advancedSettings") }}</span>
              <span class="advanced-summary">{{ imageSummary }}</span>
            </el-button>
          </div>

          <el-collapse-transition>
            <div v-show="imagePanelOpen" class="advanced-panel">
              <div class="advanced-grid">
                <div class="advanced-item">
                  <span class="advanced-label">{{ t("search.topK") }}</span>
                  <el-input-number v-model="imageTopK" :min="1" :max="50" />
                </div>
                <div class="advanced-item switch-item">
                  <span class="advanced-label">{{ t("search.enableScoreFilter") }}</span>
                  <el-switch v-model="imageEnableScoreFilter" />
                </div>
                <div class="advanced-item">
                  <span class="advanced-label">{{ t("search.minRelevanceScore") }}</span>
                  <el-input-number
                    v-model="imageMinRelevanceScore"
                    :step="0.1"
                    :precision="3"
                    :disabled="!imageEnableScoreFilter"
                  />
                </div>
              </div>
            </div>
          </el-collapse-transition>

          <el-button
            type="primary"
            class="search-btn"
            :loading="loadingImage"
            @click="doImageSearch"
          >
            <i class="i-ep-picture mr-2"></i>
            {{ t("search.imageSearchBtn") }}
          </el-button>

          <div v-if="imageQueryDescription" class="query-desc-card">
            <div class="query-desc-header">
              <i class="i-ep-bot mr-2"></i>
              <span>{{ t("search.queryDescription") }}</span>
            </div>
            <p class="query-desc-text">{{ imageQueryDescription }}</p>
          </div>

          <el-divider />

          <div class="results-section">
            <div class="results-head">
              <h4 class="section-title">
                <span v-if="imageResults.length > 0">{{ t("search.similarity") }} ({{ imageResults.length }})</span>
                <span v-else>{{ t("search.noResults") }}</span>
              </h4>
              <el-alert
                v-if="imageFilterNotice"
                :title="imageFilterNotice"
                type="info"
                :closable="false"
                show-icon
                class="inline-alert"
              />
            </div>
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
                  :score-label="getScoreLabel(item)"
                  @click="openPreview(item)"
                />
              </div>
            </div>
            <el-empty v-else-if="!loadingImage" :description="t('search.noResults')" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <ImagePreviewModal
      v-model:visible="previewVisible"
      :src="previewItem?.file_path ? getImageSrc(previewItem.file_path) : ''"
      :title="previewItem?.id"
      :description="previewItem?.description"
      :id="previewItem?.id"
      :score-label="previewItem ? getScoreLabel(previewItem) : undefined"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import {
  textToImageSearch,
  imageToImageSearch,
  type SearchResultItem,
} from "@/api/search";
import { getSystemConfig } from "@/api/settings";
import { imgSrc } from "@/utils/image";
import UploadZone from "@/components/UploadZone.vue";
import ImageCard from "@/components/ImageCard.vue";
import ImagePreviewModal from "@/components/ImagePreviewModal.vue";

const { t } = useI18n();

const textQuery = ref("");
const textResults = ref<SearchResultItem[]>([]);
const loadingText = ref(false);
const textTopK = ref(10);
const textEnableScoreFilter = ref(false);
const textMinRelevanceScore = ref(0);
const textDefaultTopK = ref(10);
const textDefaultEnableScoreFilter = ref(false);
const textDefaultMinRelevanceScore = ref(0);
const textPanelOpen = ref(false);

const imageFiles = ref<File[]>([]);
const imageResults = ref<SearchResultItem[]>([]);
const imageQueryDescription = ref("");
const loadingImage = ref(false);
const imageTopK = ref(10);
const imageEnableScoreFilter = ref(false);
const imageMinRelevanceScore = ref(0);
const imagePanelOpen = ref(false);

const previewVisible = ref(false);
const previewItem = ref<SearchResultItem | null>(null);

const textSummary = computed(() =>
  buildSummary(
    textTopK.value,
    textEnableScoreFilter.value,
    textMinRelevanceScore.value,
    textDefaultTopK.value,
    textDefaultEnableScoreFilter.value,
    textDefaultMinRelevanceScore.value,
  ),
);

const imageSummary = computed(() =>
  buildSummary(
    imageTopK.value,
    imageEnableScoreFilter.value,
    imageMinRelevanceScore.value,
    textDefaultTopK.value,
    textDefaultEnableScoreFilter.value,
    textDefaultMinRelevanceScore.value,
  ),
);

const textFilterNotice = computed(() =>
  buildFilterNotice(textResults.value, textEnableScoreFilter.value),
);
const imageFilterNotice = computed(() =>
  buildFilterNotice(imageResults.value, imageEnableScoreFilter.value),
);

watch([textTopK, textEnableScoreFilter, textMinRelevanceScore], () => {
  textPanelOpen.value = shouldKeepPanelOpen(
    textTopK.value,
    textEnableScoreFilter.value,
    textMinRelevanceScore.value,
    textDefaultTopK.value,
    textDefaultEnableScoreFilter.value,
    textDefaultMinRelevanceScore.value,
  );
});

watch([imageTopK, imageEnableScoreFilter, imageMinRelevanceScore], () => {
  imagePanelOpen.value = shouldKeepPanelOpen(
    imageTopK.value,
    imageEnableScoreFilter.value,
    imageMinRelevanceScore.value,
    textDefaultTopK.value,
    textDefaultEnableScoreFilter.value,
    textDefaultMinRelevanceScore.value,
  );
});

function shouldKeepPanelOpen(
  topK: number,
  enableFilter: boolean,
  minScore: number,
  defaultTopK: number,
  defaultEnableFilter: boolean,
  defaultMinScore: number,
): boolean {
  return (
    topK !== defaultTopK ||
    enableFilter !== defaultEnableFilter ||
    (enableFilter && minScore !== defaultMinScore)
  );
}

function buildSummary(
  topK: number,
  enableFilter: boolean,
  minScore: number,
  defaultTopK: number,
  defaultEnableFilter: boolean,
  defaultMinScore: number,
) {
  const parts: string[] = [];
  if (topK !== defaultTopK) {
    parts.push(t("search.activeTopK", { count: topK }));
  }
  if (enableFilter && (enableFilter !== defaultEnableFilter || minScore !== defaultMinScore)) {
    parts.push(`${t("search.activeRerankFilter")} ≥ ${formatNumeric(minScore)}`);
  }
  return parts.length > 0 ? parts.join(" / ") : t("search.defaultSettings");
}

function buildFilterNotice(results: SearchResultItem[], enabled: boolean): string {
  if (!enabled || results.length === 0) {
    return "";
  }
  return results.some((item) => item.score_source !== "rerank")
    ? t("search.rerankFilterUnsupported")
    : "";
}

function getErrorMessage(error: any, fallback: string): string {
  return error?.response?.data?.detail || error?.message || fallback;
}

function getImageSrc(filePath: string): string {
  return imgSrc(filePath);
}

function openPreview(item: SearchResultItem) {
  previewItem.value = item;
  previewVisible.value = true;
}

function assetTypeLabel(item: SearchResultItem): string {
  if (item.asset_type === "table_crop") return t("docs.tableCrop");
  if (item.asset_type === "table_page_render") return t("docs.tablePageRender");
  if (item.asset_type === "page_render") return t("docs.pageRender");
  return "";
}

function pageLabel(item: SearchResultItem): string {
  if (typeof item.page_number === "number") {
    return t("docs.pageLabel", { page: item.page_number });
  }
  return "";
}

function isCrossPageResult(item: SearchResultItem): boolean {
  return Boolean(item.continued_from_previous_page || item.continued_to_next_page);
}

function resultBadgeVisible(item: SearchResultItem): boolean {
  return Boolean(assetTypeLabel(item) || pageLabel(item) || isCrossPageResult(item));
}

function formatNumeric(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(3);
}

function getScoreLabel(item: SearchResultItem): string | undefined {
  if (item.score_source === "rerank" && typeof item.relevance_score === "number") {
    return `RERANK ${formatNumeric(item.relevance_score)}`;
  }
  if (item.score_source && typeof item.relevance_score === "number") {
    return `${String(item.score_source).toUpperCase()} ${formatNumeric(item.relevance_score)}`;
  }
  return undefined;
}

async function doTextSearch() {
  if (!textQuery.value.trim()) {
    ElMessage.warning(t("search.enterQuery"));
    return;
  }
  try {
    loadingText.value = true;
    const resp = await textToImageSearch(textQuery.value, {
      topK: textTopK.value,
      enableScoreFilter: textEnableScoreFilter.value,
      minRelevanceScore: textMinRelevanceScore.value,
    });
    textResults.value = resp.results;
  } catch (e) {
    textResults.value = [];
    ElMessage.error(getErrorMessage(e, t("search.textSearchFailed")));
  } finally {
    loadingText.value = false;
  }
}

async function doImageSearch() {
  const file = imageFiles.value[0];
  if (!file) {
    ElMessage.warning(t("search.selectImage"));
    return;
  }
  try {
    loadingImage.value = true;
    const resp = await imageToImageSearch(file, {
      topK: imageTopK.value,
      enableScoreFilter: imageEnableScoreFilter.value,
      minRelevanceScore: imageMinRelevanceScore.value,
    });
    imageQueryDescription.value = resp.query_description;
    imageResults.value = resp.results;
  } catch (e) {
    imageQueryDescription.value = "";
    imageResults.value = [];
    ElMessage.error(getErrorMessage(e, t("search.imageSearchFailed")));
  } finally {
    loadingImage.value = false;
  }
}

async function loadSearchDefaults() {
  try {
    const payload = await getSystemConfig();
    const itemMap = Object.fromEntries(payload.items.map((item) => [item.key, item.value]));
    textDefaultTopK.value = Number(itemMap.SEARCH_DEFAULT_TOP_K ?? 10);
    textDefaultEnableScoreFilter.value = Boolean(itemMap.SEARCH_ENABLE_SCORE_FILTER ?? false);
    textDefaultMinRelevanceScore.value = Number(itemMap.SEARCH_MIN_RELEVANCE_SCORE ?? 0);

    textTopK.value = textDefaultTopK.value;
    textEnableScoreFilter.value = textDefaultEnableScoreFilter.value;
    textMinRelevanceScore.value = textDefaultMinRelevanceScore.value;

    imageTopK.value = textDefaultTopK.value;
    imageEnableScoreFilter.value = textDefaultEnableScoreFilter.value;
    imageMinRelevanceScore.value = textDefaultMinRelevanceScore.value;
  } catch (error) {
    console.error("加载搜索默认参数失败:", error);
  }
}

onMounted(() => {
  loadSearchDefaults();
});
</script>

<style scoped>
.search-page {
  max-width: 1400px;
  margin: 0 auto;
}

.search-layout {
  row-gap: 20px;
}

.search-card {
  height: calc(100vh - 220px);
  display: flex;
  flex-direction: column;
}

.search-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  flex: 1;
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

.advanced-toggle-row {
  margin-top: 14px;
}

.advanced-toggle {
  width: 100%;
  justify-content: space-between;
  border-radius: 14px;
  padding: 10px 12px;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
}

.advanced-toggle:hover {
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
}

.advanced-summary {
  margin-left: auto;
  color: var(--text-tertiary);
  font-size: 12px;
  text-align: right;
}

.advanced-panel {
  margin-top: 12px;
  padding: 14px;
  border-radius: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
}

.advanced-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.advanced-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.advanced-item.switch-item {
  justify-content: space-between;
}

.advanced-label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.search-btn {
  margin-top: 16px;
  width: 100%;
}

.results-section {
  flex: 1;
  overflow-y: auto;
}

.results-head {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inline-alert {
  margin-bottom: 4px;
}

.section-title {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0 0 8px;
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

@media (max-width: 1100px) {
  .advanced-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .search-card {
    height: auto;
    min-height: 540px;
  }

  .advanced-toggle {
    align-items: flex-start;
    gap: 8px;
  }

  .advanced-summary {
    white-space: normal;
  }
}
</style>
