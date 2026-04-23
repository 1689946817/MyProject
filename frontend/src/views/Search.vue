<template>
  <div class="search-page">
    <div class="page-intro">
      <div class="page-intro-main">
        <h1 class="page-title">{{ t("search.title") }}</h1>
        <p class="page-subtitle">{{ t("search.subtitle") }}</p>
      </div>
    </div>

    <div class="search-layout">
      <el-card class="search-card workspace-card glass-card">
        <template #header>
          <div class="card-header">
            <div class="card-header-main">
              <i class="i-ep-search accent-icon"></i>
              <span>{{ t("search.textToImage") }}</span>
            </div>
            <span class="card-header-note">{{ t("search.searchBtn") }}</span>
          </div>
        </template>

        <div class="workspace-body">
          <div class="workspace-surface text-surface">
            <el-input
              v-model="textQuery"
              :placeholder="t('search.textQueryPlaceholder')"
              type="textarea"
              :rows="6"
              class="dark-input workspace-input"
            />
          </div>

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
        </div>

        <div class="workspace-footer">
          <el-button
            type="primary"
            class="search-btn"
            :loading="loadingText"
            @click="doTextSearch"
          >
            <i class="i-ep-search mr-2"></i>
            {{ t("search.searchBtn") }}
          </el-button>
        </div>
      </el-card>

      <el-card class="search-card workspace-card glass-card">
        <template #header>
          <div class="card-header">
            <div class="card-header-main">
              <i class="i-ep-picture accent-icon"></i>
              <span>{{ t("search.imageToImage") }}</span>
            </div>
            <span class="card-header-note">{{ t("search.imageSearchBtn") }}</span>
          </div>
        </template>

        <div class="workspace-body">
          <div class="workspace-surface upload-surface">
            <UploadZone
              v-model:files="imageFiles"
              :text="t('search.imageQueryPlaceholder')"
              :accept="'image/*'"
              :multiple="false"
            />
          </div>

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
        </div>

        <div class="workspace-footer">
          <el-button
            type="primary"
            class="search-btn"
            :loading="loadingImage"
            @click="doImageSearch"
          >
            <i class="i-ep-picture mr-2"></i>
            {{ t("search.imageSearchBtn") }}
          </el-button>
        </div>
      </el-card>
    </div>

    <el-card class="results-card glass-card">
      <template #header>
        <div class="results-toolbar">
          <div class="results-toolbar-main">
            <div class="results-toolbar-title">{{ t("search.similarity") }}</div>
            <div class="results-toolbar-subtitle">{{ activeResultLabel }}</div>
          </div>
          <div class="results-mode-switch">
            <button
              type="button"
              class="results-mode-btn"
              :class="{ active: activeResultMode === 'text' }"
              @click="activeResultMode = 'text'"
            >
              <i class="i-ep-search"></i>
              <span>{{ t("search.textToImage") }}</span>
              <span class="mode-count">{{ textResults.length }}</span>
            </button>
            <button
              type="button"
              class="results-mode-btn"
              :class="{ active: activeResultMode === 'image' }"
              @click="activeResultMode = 'image'"
            >
              <i class="i-ep-picture"></i>
              <span>{{ t("search.imageToImage") }}</span>
              <span class="mode-count">{{ imageResults.length }}</span>
            </button>
          </div>
        </div>
      </template>

      <div class="results-section unified-results">
        <div v-if="activeResultMode === 'image' && imageQueryDescription" class="query-desc-card">
          <div class="query-desc-header">
            <i class="i-ep-bot mr-2"></i>
            <span>{{ t("search.queryDescription") }}</span>
          </div>
          <p class="query-desc-text">{{ imageQueryDescription }}</p>
        </div>

        <div class="results-head">
          <h4 class="section-title">
            <span v-if="activeResults.length > 0">{{ t("search.similarity") }} ({{ activeResults.length }})</span>
            <span v-else-if="hasAnySearch">{{ t("search.noResults") }}</span>
            <span v-else>{{ activeResultLabel }}</span>
          </h4>
          <el-alert
            v-if="activeFilterNotice"
            :title="activeFilterNotice"
            type="info"
            :closable="false"
            show-icon
            class="inline-alert"
          />
        </div>

        <div v-if="activeResults.length > 0" class="result-grid">
          <div v-for="item in activeResults" :key="item.id" class="search-image-item">
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
        <div v-else-if="activeLoading" class="results-loading">
          <i class="i-ep-loading"></i>
          <span>{{ activeResultLabel }}</span>
        </div>
        <div v-else-if="hasAnySearch" class="results-empty-state">
          <el-empty :description="t('search.noResults')" />
        </div>
        <div v-else class="results-placeholder">
          <div class="results-placeholder-title">{{ activeResultLabel }}</div>
          <p>{{ activeResultMode === "text" ? t("search.textQueryPlaceholder") : t("search.imageQueryPlaceholder") }}</p>
        </div>
      </div>
    </el-card>

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
const textSearched = ref(false);

const imageFiles = ref<File[]>([]);
const imageResults = ref<SearchResultItem[]>([]);
const imageQueryDescription = ref("");
const loadingImage = ref(false);
const imageTopK = ref(10);
const imageEnableScoreFilter = ref(false);
const imageMinRelevanceScore = ref(0);
const imagePanelOpen = ref(false);
const imageSearched = ref(false);
const activeResultMode = ref<"text" | "image">("text");

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
const activeResults = computed(() =>
  activeResultMode.value === "text" ? textResults.value : imageResults.value,
);
const activeLoading = computed(() =>
  activeResultMode.value === "text" ? loadingText.value : loadingImage.value,
);
const activeFilterNotice = computed(() =>
  activeResultMode.value === "text" ? textFilterNotice.value : imageFilterNotice.value,
);
const activeResultLabel = computed(() =>
  activeResultMode.value === "text" ? t("search.textToImage") : t("search.imageToImage"),
);
const hasAnySearch = computed(() =>
  textSearched.value || imageSearched.value,
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
    activeResultMode.value = "text";
    textSearched.value = true;
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
    activeResultMode.value = "image";
    imageSearched.value = true;
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
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.search-layout {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  align-items: stretch;
}

.search-card {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.workspace-card {
  min-height: 0;
}

.search-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: 22px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-header-main {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.card-header-note {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.accent-icon {
  color: var(--accent-primary);
  font-size: 18px;
}

.workspace-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}

.workspace-surface {
  min-height: 232px;
  padding: 14px;
  border-radius: 22px;
  border: 1px solid var(--border-color);
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.08), transparent 32%),
    rgba(255, 255, 255, 0.8);
}

.text-surface {
  display: flex;
}

.upload-surface {
  display: flex;
  align-items: stretch;
}

.upload-surface :deep(.upload-zone) {
  width: 100%;
  min-height: 100%;
}

.workspace-footer {
  margin-top: 14px;
}

.dark-input :deep(.el-textarea__inner) {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
  min-height: 200px !important;
  box-shadow: none;
  padding: 16px 18px;
  border-radius: 18px;
}

.dark-input :deep(.el-textarea__inner:focus) {
  border-color: var(--accent-primary);
}

.workspace-input {
  flex: 1;
}

.advanced-toggle-row {
  margin-top: auto;
}

.advanced-toggle {
  width: 100%;
  justify-content: space-between;
  border-radius: 16px;
  padding: 12px 14px;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.74);
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
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
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
  width: 100%;
  min-height: 44px;
  border-radius: 14px;
}

.results-card :deep(.el-card__body) {
  padding: 20px 22px 22px;
}

.results-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.results-toolbar-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.results-toolbar-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.results-toolbar-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
}

.results-mode-switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.results-mode-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--border-color);
  background: rgba(255, 255, 255, 0.82);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.18s ease;
}

.results-mode-btn.active {
  border-color: rgba(37, 99, 235, 0.18);
  background: var(--bg-accent-soft);
  color: var(--accent-primary);
}

.mode-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  font-size: 11px;
  color: inherit;
}

.results-section {
  padding-top: 4px;
}

.unified-results {
  min-height: 340px;
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
  margin-bottom: 16px;
  padding: 14px 16px;
  background: rgba(255, 255, 255, 0.74);
  border-radius: 16px;
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

.results-loading,
.results-placeholder {
  min-height: 260px;
  border: 1px dashed var(--border-color);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.55);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-secondary);
  text-align: center;
  padding: 24px;
}

.results-loading {
  color: var(--accent-primary);
}

.results-placeholder-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.results-placeholder p {
  max-width: 520px;
  margin: 0;
  line-height: 1.6;
}

.results-empty-state {
  padding-top: 18px;
}

@media (max-width: 1100px) {
  .search-layout {
    grid-template-columns: 1fr;
  }

  .advanced-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .search-card {
    min-height: 0;
  }

  .advanced-toggle {
    align-items: flex-start;
    gap: 8px;
  }

  .advanced-summary {
    white-space: normal;
  }

  .results-toolbar {
    align-items: flex-start;
  }

  .results-mode-switch {
    width: 100%;
  }

  .results-mode-btn {
    flex: 1 1 calc(50% - 4px);
    justify-content: center;
  }
}
</style>
