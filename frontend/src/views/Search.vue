<!-- 搜索页面：支持文本→图像和图像→图像两种检索模式，提供高级参数设置和结果预览 -->
<template>
  <div class="search-page">
    <div class="page-intro">
      <div class="page-intro-main">
        <h1 class="page-title">{{ t("search.title") }}</h1>
        <p class="page-subtitle">{{ t("search.subtitle") }}</p>
      </div>
    </div>

    <el-card class="search-workbench glass-card">
      <template #header>
        <div class="workbench-header">
          <div class="subpage-tabs" role="tablist">
            <button
              type="button"
              class="subpage-tab"
              :class="{ active: activeResultMode === 'text' }"
              role="tab"
              :aria-selected="activeResultMode === 'text'"
              @click="activeResultMode = 'text'"
            >
              <i class="i-ep-search"></i>
              <span>{{ t("search.textMode") }}</span>
            </button>
            <button
              type="button"
              class="subpage-tab"
              :class="{ active: activeResultMode === 'image' }"
              role="tab"
              :aria-selected="activeResultMode === 'image'"
              @click="activeResultMode = 'image'"
            >
              <i class="i-ep-picture"></i>
              <span>{{ t("search.imageMode") }}</span>
            </button>
          </div>
        </div>
      </template>

      <div class="subpage-shell">
        <section v-if="activeResultMode === 'text'" class="query-panel text-panel">
          <div class="text-entry-row">
            <div class="query-input-shell">
              <el-input
                v-model="textQuery"
                :placeholder="t('search.textQueryPlaceholder')"
                type="textarea"
                :rows="2"
                class="dark-input query-input"
              />
            </div>

            <div class="entry-actions">
              <el-button
                type="primary"
                class="search-btn"
                :loading="loadingText"
                @click="doTextSearch"
              >
                <i class="i-ep-search mr-2"></i>
                {{ t("search.searchBtn") }}
              </el-button>

              <el-button text class="advanced-toggle compact-toggle" @click="textPanelOpen = !textPanelOpen">
                <i :class="textPanelOpen ? 'i-ep-arrow-up-bold' : 'i-ep-arrow-down-bold'"></i>
                <span>{{ t("search.advancedSettings") }}</span>
              </el-button>
            </div>
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
        </section>

        <section v-else class="query-panel image-panel">
          <div class="upload-entry-row">
            <UploadZone
              v-model:files="imageFiles"
              :text="t('search.imageQueryPlaceholder')"
              :accept="'image/*'"
              :multiple="false"
              compact
            />

            <div class="entry-actions">
              <el-button
                type="primary"
                class="search-btn"
                :loading="loadingImage"
                @click="doImageSearch"
              >
                <i class="i-ep-picture mr-2"></i>
                {{ t("search.imageSearchBtn") }}
              </el-button>

              <el-button text class="advanced-toggle compact-toggle" @click="imagePanelOpen = !imagePanelOpen">
                <i :class="imagePanelOpen ? 'i-ep-arrow-up-bold' : 'i-ep-arrow-down-bold'"></i>
                <span>{{ t("search.advancedSettings") }}</span>
              </el-button>
            </div>
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
        </section>
      </div>
    </el-card>

    <el-card class="results-card glass-card">
      <template #header>
        <div class="results-toolbar">
          <div class="results-toolbar-main">
            <div class="results-toolbar-title">{{ t("search.results") }}</div>
          </div>
          <div v-if="activeResults.length > 0" class="results-count-chip">{{ activeResults.length }}</div>
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
          <span>{{ activeModeLabel }}</span>
        </div>
        <div v-else-if="hasAnySearch" class="results-empty-state">
          <el-empty :description="t('search.noResults')" />
        </div>
        <div v-else class="results-placeholder">
          <div class="results-placeholder-title">{{ activeModeLabel }}</div>
          <p>{{ activeResultMode === "text" ? t("search.textHint") : t("search.imageHint") }}</p>
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
// ---- 导入 ----
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

// ---- 文本检索相关状态 ----
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

// ---- 图像检索相关状态 ----
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

// ---- 图片预览弹窗状态 ----
const previewVisible = ref(false);
const previewItem = ref<SearchResultItem | null>(null);

// ---- 计算属性 ----

/** 文本检索高级设置的摘要描述（如"Top-K: 20 / 过滤 ≥ 0.500"） */
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

/** 图像检索高级设置的摘要描述 */
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

// 当前激活结果模式对应的过滤提示、结果列表、加载状态等派生属性
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
const activeModeLabel = computed(() =>
  activeResultMode.value === "text" ? t("search.textMode") : t("search.imageMode"),
);
const hasAnySearch = computed(() =>
  textSearched.value || imageSearched.value,
);

// ---- 侦听器 ----

/** 当高级设置参数偏离默认值时自动展开面板 */
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

/** 图像检索高级设置参数变化时自动管理面板展开状态 */
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

// ---- 工具函数 ----

/** 判断高级设置面板是否应保持展开（参数偏离默认值时展开） */
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

/** 构建高级设置的摘要文本，展示与默认值不同的参数 */
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

/** 构建过滤提示信息，当启用了分数过滤但结果来源不支持 rerank 时给出提示 */
function buildFilterNotice(results: SearchResultItem[], enabled: boolean): string {
  if (!enabled || results.length === 0) {
    return "";
  }
  return results.some((item) => item.score_source !== "rerank")
    ? t("search.rerankFilterUnsupported")
    : "";
}

/** 从 API 错误响应中提取用户友好的错误信息 */
function getErrorMessage(error: any, fallback: string): string {
  return error?.response?.data?.detail || error?.message || fallback;
}

function getImageSrc(filePath: string): string {
  return imgSrc(filePath);
}

/** 打开图片预览弹窗 */
function openPreview(item: SearchResultItem) {
  previewItem.value = item;
  previewVisible.value = true;
}

/** 根据资源类型返回对应的中文标签（表格截图/整页渲染等） */
function assetTypeLabel(item: SearchResultItem): string {
  if (item.asset_type === "table_crop") return t("docs.tableCrop");
  if (item.asset_type === "table_page_render") return t("docs.tablePageRender");
  if (item.asset_type === "page_render") return t("docs.pageRender");
  return "";
}

/** 返回页码标签文本 */
function pageLabel(item: SearchResultItem): string {
  if (typeof item.page_number === "number") {
    return t("docs.pageLabel", { page: item.page_number });
  }
  return "";
}

/** 判断搜索结果是否为跨页延续的资源 */
function isCrossPageResult(item: SearchResultItem): boolean {
  return Boolean(item.continued_from_previous_page || item.continued_to_next_page);
}

/** 判断搜索结果是否需要显示标签徽章 */
function resultBadgeVisible(item: SearchResultItem): boolean {
  return Boolean(assetTypeLabel(item) || pageLabel(item) || isCrossPageResult(item));
}

/** 将数值格式化为三位小数字符串，无效值返回 "-" */
function formatNumeric(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(3);
}

/** 根据分数来源生成标签文本（如 "RERANK 0.850"） */
function getScoreLabel(item: SearchResultItem): string | undefined {
  if (item.score_source === "rerank" && typeof item.relevance_score === "number") {
    return `RERANK ${formatNumeric(item.relevance_score)}`;
  }
  if (item.score_source && typeof item.relevance_score === "number") {
    return `${String(item.score_source).toUpperCase()} ${formatNumeric(item.relevance_score)}`;
  }
  return undefined;
}

// ---- 搜索方法 ----

/** 执行文本→图像检索，将查询文本发送到后端并展示结果 */
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

/** 执行图像→图像检索，上传图片并展示相似结果和 MLLM 生成的查询描述 */
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

/** 从后端加载搜索默认参数（Top-K、分数过滤等），初始化两个检索面板的默认值 */
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

// ---- 生命周期 ----

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

.search-workbench :deep(.el-card__body) {
  padding: 12px 16px 14px;
}

.workbench-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.subpage-tabs {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border-radius: 999px;
  border: 1px solid var(--border-color);
  background: rgba(248, 250, 252, 0.88);
}

.subpage-tab {
  min-height: 30px;
  padding: 0 12px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;
}

.subpage-tab.active {
  background: #ffffff;
  color: var(--accent-primary);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08);
}

.subpage-shell {
  min-height: 0;
}

.query-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border-radius: 16px;
  border: 1px solid var(--border-color);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.78)),
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.06), transparent 30%);
}

.accent-icon {
  color: var(--accent-primary);
  font-size: 18px;
}

.text-entry-row,
.upload-entry-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: stretch;
}

.query-input-shell {
  padding: 6px;
  border-radius: 14px;
  border: 1px solid var(--border-color);
  background: rgba(248, 250, 252, 0.88);
}

.entry-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dark-input :deep(.el-textarea__inner) {
  background: transparent;
  border-color: transparent;
  color: var(--text-primary);
  min-height: 44px !important;
  box-shadow: none;
  padding: 10px 12px;
  border-radius: 14px;
}

.dark-input :deep(.el-textarea__inner:focus) {
  border-color: var(--accent-primary);
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

.compact-toggle {
  width: auto;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
}

.advanced-panel {
  margin-top: 2px;
  padding: 12px 14px;
  border-radius: 14px;
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
  min-width: 148px;
  min-height: 34px;
  padding: 0 16px;
  border-radius: 999px;
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

.results-count-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 26px;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--bg-accent-soft);
  font-size: 12px;
  font-weight: 700;
  color: var(--accent-primary);
}

.results-section {
  padding-top: 0;
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
  .advanced-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .workbench-header {
    align-items: flex-start;
  }

  .subpage-tabs {
    width: 100%;
  }

  .subpage-tab {
    flex: 1;
    justify-content: center;
    padding: 0 10px;
  }

  .text-entry-row,
  .upload-entry-row {
    grid-template-columns: 1fr;
  }

  .entry-actions {
    flex-wrap: wrap;
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

  .search-btn {
    width: 100%;
  }
}
</style>
