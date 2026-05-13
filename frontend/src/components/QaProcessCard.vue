<!--
  QaProcessCard - RAG 问答过程可视化卡片
  功能：以折叠面板形式展示 RAG 流式问答的完整处理过程，包括意图路由、查询改写、检索、重排、压缩、生成等阶段。
  支持实时流式（live）和历史回顾两种模式，实时模式下自动刷新计时器并按阶段排序显示步骤。
-->
<template>
  <details v-if="shouldRender" class="thinking-inline-wrap" :open="detailsOpen">
    <summary class="thinking-inline" :class="{ done: isDone, live: isLive }" @click="handleSummaryClick">
      <span class="thinking-dot" :class="dotClass"></span>
      <span class="thinking-text">{{ primaryText }}</span>
      <span v-if="secondaryText" class="thinking-subtext">{{ secondaryText }}</span>
      <span class="thinking-toggle">{{ detailsOpen ? t("chat.processCollapse") : t("chat.processExpand") }}</span>
    </summary>

    <div class="thinking-details" :class="{ card: !isLive }">
      <template v-if="isLive">
        <QaProcessStepList :steps="processSteps" compact />
        <div v-if="detailItems.length > 0" class="thinking-detail-grid">
          <div v-for="detail in detailItems" :key="detail.key" class="thinking-detail-item">
            <span class="thinking-detail-label">{{ detail.label }}</span>
            <span class="thinking-detail-value">{{ detail.value }}</span>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="thinking-overview">
          <div v-if="formatChatMode(modeValue)" class="thinking-overview-item">
            <span class="thinking-overview-label">{{ t("chat.processChatMode") }}</span>
            <span class="thinking-overview-value">{{ formatChatMode(modeValue) }}</span>
          </div>
          <div v-if="executionModeValue" class="thinking-overview-item">
            <span class="thinking-overview-label">{{ t("chat.processExecutionMode") }}</span>
            <span class="thinking-overview-value">{{ executionModeValue }}</span>
          </div>
          <div v-if="typeof useRagValue === 'boolean'" class="thinking-overview-item">
            <span class="thinking-overview-label">{{ t("chat.processKnowledgeRoute") }}</span>
            <span class="thinking-overview-value">{{ useRagValue ? t("chat.processEnabled") : t("chat.processDisabled") }}</span>
          </div>
        </div>
        <QaProcessStepList :steps="processSteps" />
        <div v-if="detailItems.length > 0" class="thinking-detail-grid card">
          <div v-for="detail in detailItems" :key="detail.key" class="thinking-detail-item card">
            <span class="thinking-detail-label">{{ detail.label }}</span>
            <span class="thinking-detail-value">{{ detail.value }}</span>
          </div>
        </div>
      </template>
    </div>
  </details>
</template>

<script setup lang="ts">
// ---- 导入依赖 ----
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import QaProcessStepList from "@/components/QaProcessStepList.vue";
import type {
  ChatMessage,
  ChatMode,
  ChatProgressEvent,
  QaProcessStepViewModel,
  RetrievalStepItem,
  TimingStage,
  TimingSummary,
} from "@/types";

// ---- Props ----
const props = defineProps<{
  /** 当前助手消息，包含流式进度、检索步骤和耗时信息 */
  message: ChatMessage;
}>();

const { t } = useI18n();

// ---- 响应式状态 ----
const now = ref(Date.now());           // 当前时间戳，用于实时计算已耗时
const detailsOpen = ref(false);        // 详情面板是否展开
let timer = 0;                         // 定时器 ID，每 300ms 刷新 now

// ---- 流式进度计算属性 ----
/** 从消息中提取所有流式进度步骤 */
const liveSteps = computed<ChatProgressEvent[]>(() => props.message.live_progress_steps || []);
/** 最近一条进度事件，优先取 live_progress 字段 */
const latestStep = computed<ChatProgressEvent | null>(() => props.message.live_progress || liveSteps.value.at(-1) || null);
/** 历史检索步骤（非流式模式使用） */
const rawSteps = computed<RetrievalStepItem[]>(() => props.message.retrieval_steps || []);
/** 是否处于流式接收中 */
const isLive = computed(() => liveSteps.value.length > 0);
/** 流式是否已完成 */
const isDone = computed(() => Boolean(props.message.live_progress_done) || (!isLive.value && rawSteps.value.length > 0));

// ---- 耗时统计 ----
/** 耗时汇总信息，兼容两种消息结构 */
const timingSummary = computed<TimingSummary | null>(() => {
  return (props.message.timings as TimingSummary | null | undefined)
    || (props.message.retrieval_params?.timings as TimingSummary | null | undefined)
    || null;
});

/** 按阶段名称分组的耗时阶段列表 */
const timingStageMap = computed<Record<string, TimingStage[]>>(() => {
  return (timingSummary.value?.stages || []).reduce<Record<string, TimingStage[]>>((acc, stage) => {
    const bucket = acc[stage.name] || [];
    bucket.push(stage);
    acc[stage.name] = bucket;
    return acc;
  }, {});
});

/** 合并所有流式步骤的 meta 信息 */
const liveMeta = computed<Record<string, unknown>>(() => {
  return liveSteps.value.reduce<Record<string, unknown>>((acc, step) => {
    Object.assign(acc, step.meta || {});
    return acc;
  }, {});
});

/** 总耗时（毫秒），优先从最新步骤获取，其次从汇总获取，实时模式下自动计算 */
const totalMs = computed<number | null>(() => {
  const latestElapsed = latestStep.value?.elapsed_ms;
  if (typeof latestElapsed === "number") {
    return latestElapsed;
  }
  if (timingSummary.value?.total_ms) {
    return timingSummary.value.total_ms;
  }
  if (props.message.live_progress_started_at && isLive.value && !props.message.live_progress_done) {
    return Math.max(0, now.value - new Date(props.message.live_progress_started_at).getTime());
  }
  return null;
});

// ---- 渲染控制 ----
/** 仅助手消息且有进度数据时才渲染整个卡片 */
const shouldRender = computed(() => props.message.role === "assistant" && (isLive.value || rawSteps.value.length > 0 || Boolean(timingSummary.value)));

// ---- 步骤视图模型 ----
/** 将流式/历史步骤转换为统一的视图模型列表，按优先级排序并计算每步耗时 */
const processSteps = computed<QaProcessStepViewModel[]>(() => {
  if (isLive.value) {
    const preferredOrder = ["routing", "rewrite", "retrieve", "rerank", "compress", "agentic", "generate", "complete"];
    const sortedSteps = [...liveSteps.value].sort((left, right) => preferredOrder.indexOf(left.phase) - preferredOrder.indexOf(right.phase));
    let previousElapsed = 0;
    return sortedSteps.map((step) => {
      const currentElapsed = typeof step.elapsed_ms === "number" ? step.elapsed_ms : null;
      const durationMs = currentElapsed !== null ? Math.max(0, currentElapsed - previousElapsed) : null;
      if (currentElapsed !== null) previousElapsed = currentElapsed;
      return {
        key: step.step_key || step.phase,
        label: mapPhaseLabel(step.phase),
        summary: step.detail || resolveProgressSummary(step.status),
        status: step.status,
        isActive: latestStep.value?.phase === step.phase && !props.message.live_progress_done,
        durationMs,
        details: toDetailItems(step.meta || {}),
      };
    });
  }

  const preferredOrder = ["intent", "query", "retrieve", "retrieval", "grade", "grading", "retry", "generate"];
  const sortedSteps = [...rawSteps.value].sort((left, right) => {
    const leftIdx = preferredOrder.indexOf(left.key);
    const rightIdx = preferredOrder.indexOf(right.key);
    return (leftIdx === -1 ? preferredOrder.length : leftIdx) - (rightIdx === -1 ? preferredOrder.length : rightIdx);
  });
  return sortedSteps.map((step) => ({
    key: step.key,
    label: mapLegacyStepLabel(step),
    summary: step.summary,
    status: "completed" as const,
    durationMs: lookupDuration(step.key),
    details: toDetailItems(step.details || {}),
  }));
});

// ---- 参数详情 ----
/** 检索参数详情项列表（来源范围、查询改写、候选数量等），过滤空值后展示 */
const detailItems = computed(() => {
  const metadata = isLive.value ? liveMeta.value : (props.message.retrieval_params || {});

  return [
    { key: "source_scope", label: t("chat.processSourceScope"), value: formatBoolean(metadata.source_scope_enabled) },
    { key: "query_rewrite", label: t("chat.processQueryRewrite"), value: formatBoolean(metadata.query_rewrite_enabled) },
    { key: "candidate_count", label: t("chat.processCandidateCount"), value: formatScalar(metadata.retrieved_candidates) },
    { key: "rerank", label: t("chat.processRerank"), value: formatBoolean(metadata.rerank_enabled) },
    { key: "compression", label: t("chat.processCompression"), value: formatBoolean(metadata.compression_enabled) },
    { key: "agentic", label: t("chat.processAgentic"), value: formatBoolean(metadata.agentic_enabled) },
  ].filter((item) => item.value !== "");
});

// ---- 折叠栏文本 ----
/** 主标题文本：流式中显示当前阶段，完成后显示"可查看处理过程" */
const primaryText = computed(() => {
  if (isLive.value && latestStep.value) {
    if (latestStep.value.phase === "complete" || props.message.live_progress_done) {
      return t("chat.thinkingDone");
    }
    return mapPhaseText(latestStep.value.phase);
  }
  if (rawSteps.value.length > 0 || timingSummary.value) {
    return t("chat.processReviewReady");
  }
  return t("chat.thinking");
});

/** 副标题文本：显示步骤详情或总耗时 */
const secondaryText = computed(() => {
  if (isLive.value) {
    const detail = latestStep.value?.detail?.trim();
    if (detail) return detail;
    if (totalMs.value !== null) return formatDuration(totalMs.value);
    return "";
  }
  if (totalMs.value !== null) {
    return `${t("chat.processTotal")} ${formatDuration(totalMs.value)}`;
  }
  return t("chat.processReviewHint");
});

/** 状态指示点的 CSS 类名：active(进行中) | done(已完成) | 空(待定) */
const dotClass = computed(() => {
  if (isLive.value) return "active";
  if (isDone.value) return "done";
  return "";
});

/** 聊天模式（fast / expert / default） */
const modeValue = computed(() => props.message.chat_mode || (props.message.retrieval_params?.chat_mode as ChatMode | undefined));
/** 执行模式值 */
const executionModeValue = computed(() => props.message.execution_mode || props.message.retrieval_params?.execution_mode || "");
/** 是否启用知识库路由 */
const useRagValue = computed(() => props.message.use_rag ?? props.message.retrieval_params?.use_rag);

// ---- 生命周期与监听 ----
/** 流式开始时自动收起详情面板 */
watch(isLive, (value) => {
  if (value) {
    detailsOpen.value = false;
  }
}, { immediate: true });

/** 挂载时启动 300ms 定时器，实时刷新已耗时显示 */
onMounted(() => {
  timer = window.setInterval(() => {
    if (isLive.value && !props.message.live_progress_done) {
      now.value = Date.now();
    }
  }, 300);
});

/** 卸载时清除定时器 */
onBeforeUnmount(() => {
  window.clearInterval(timer);
});

// ---- 事件处理 ----
/** 点击折叠栏标题时切换详情面板展开状态（流式中禁止展开） */
function handleSummaryClick() {
  if (isLive.value) {
    return;
  }
  detailsOpen.value = !detailsOpen.value;
}

// ---- 国际化映射函数 ----
/** 将阶段标识映射为流式状态显示文本 */
function mapPhaseText(phase: ChatProgressEvent["phase"]): string {
  if (phase === "routing") return t("chat.thinkingRouting");
  if (phase === "rewrite") return t("chat.thinkingRewrite");
  if (phase === "retrieve") return t("chat.thinkingRetrieve");
  if (phase === "rerank") return t("chat.thinkingRerank");
  if (phase === "compress") return t("chat.thinkingCompress");
  if (phase === "agentic") return t("chat.thinkingAgentic");
  if (phase === "generate") return t("chat.thinkingGenerate");
  return t("chat.thinking");
}

/** 将阶段标识映射为步骤列表标签文本 */
function mapPhaseLabel(phase: ChatProgressEvent["phase"]): string {
  if (phase === "routing") return t("chat.processIntent");
  if (phase === "rewrite") return t("chat.processRewrite");
  if (phase === "retrieve") return t("chat.processRetrieve");
  if (phase === "rerank") return t("chat.processRerank");
  if (phase === "compress") return t("chat.processCompression");
  if (phase === "agentic") return t("chat.processAgentic");
  if (phase === "generate") return t("chat.processGenerate");
  return t("chat.processComplete");
}

/** 将旧版检索步骤 key 显示为标签文本（兼容历史数据） */
function mapLegacyStepLabel(step: RetrievalStepItem): string {
  if (step.key === "intent") return t("chat.processIntent");
  if (step.key === "query") return t("chat.processQuery");
  if (step.key === "retrieve" || step.key === "retrieval") return t("chat.processRetrieve");
  if (step.key === "grade" || step.key === "grading") return t("chat.processGrade");
  if (step.key === "retry") return t("chat.processRetry");
  if (step.key === "generate") return t("chat.processGenerate");
  return step.label;
}

/** 将步骤状态映射为摘要文本 */
function resolveProgressSummary(status: ChatProgressEvent["status"]): string {
  if (status === "completed") return t("chat.processStepCompleted");
  if (status === "skipped") return t("chat.processStepSkipped");
  if (status === "failed") return t("chat.processStepFailed");
  return t("chat.processStepRunning");
}

// ---- 耗时计算 ----
/** 根据步骤 key 从耗时统计中查找对应阶段的总耗时 */
function lookupDuration(stepKey: string): number | null {
  const candidateGroups = timingStageNames(stepKey);
  for (const names of candidateGroups) {
    let total = 0;
    let matched = false;
    for (const name of names) {
      const stageEntries = timingStageMap.value[name] || [];
      if (stageEntries.length > 0) {
        matched = true;
        total += stageEntries.reduce((sum, stage) => sum + (stage.elapsed_ms || 0), 0);
      }
    }
    if (matched) {
      return total;
    }
  }
  return null;
}

/** 将步骤 key 映射为可能的耗时阶段名称组（一个步骤可能对应多个阶段） */
function timingStageNames(stepKey: string): string[][] {
  if (stepKey === "intent") return [["chat_routing"], ["intent_classification"]];
  if (stepKey === "query") return [["chat_rewrite"]];
  if (stepKey === "retrieve" || stepKey === "retrieval") return [
    ["chat_retrieve"],
    ["agentic_retrieve_initial", "agentic_retrieve_retry"],
    ["rag_retrieval", "document_text_retrieval", "image_retrieval"],
  ];
  if (stepKey === "grade" || stepKey === "grading") return [["chat_rerank"], ["agentic_grade"], ["rerank"]];
  if (stepKey === "retry") return [["agentic_retrieve_retry"]];
  if (stepKey === "generate") return [["chat_generate"], ["agentic_generate"], ["final_answer_generation"]];
  return [];
}

// ---- 工具函数 ----
/** 将原始详情对象转换为标签-值对数组，过滤空值 */
function toDetailItems(details: Record<string, unknown>): QaProcessStepViewModel["details"] {
  return Object.entries(details)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => ({
      key,
      label: mapDetailLabel(key),
      value: formatScalar(value),
    }));
}

/** 将详情 key 映射为国际化标签文本 */
function mapDetailLabel(key: string): string {
  if (key === "source_scope_enabled") return t("chat.processSourceScope");
  if (key === "query_rewrite_enabled") return t("chat.processQueryRewrite");
  if (key === "retrieved_candidates") return t("chat.processCandidateCount");
  if (key === "rerank_enabled") return t("chat.processRerank");
  if (key === "compression_enabled") return t("chat.processCompression");
  if (key === "agentic_enabled") return t("chat.processAgentic");
  return key;
}

/** 将布尔值格式化为"启用/禁用"文本 */
function formatBoolean(value: unknown): string {
  if (typeof value !== "boolean") return "";
  return value ? t("chat.processEnabled") : t("chat.processDisabled");
}

/** 将任意值格式化为可显示的字符串（数组用逗号连接，数字保留3位小数） */
function formatScalar(value: unknown): string {
  if (value === undefined || value === null || value === "") return "";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? t("chat.processYes") : t("chat.processNo");
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value);
}

/** 将毫秒数格式化为 "X.X s" 或 "X ms" 格式 */
function formatDuration(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
  return `${Math.round(value)} ms`;
}

/** 将聊天模式枚举值映射为国际化显示文本 */
function formatChatMode(mode?: ChatMode): string {
  if (mode === "fast") return t("chat.chatModeFast");
  if (mode === "expert") return t("chat.chatModeExpert");
  if (mode === "default") return t("chat.chatModeDefault");
  return "";
}
</script>

<style scoped>
.thinking-inline-wrap {
  margin-top: 10px;
}

.thinking-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  max-width: 100%;
  padding: 6px 0;
  color: rgba(15, 23, 42, 0.5);
  font-size: 12px;
  line-height: 1.45;
  cursor: default;
  list-style: none;
}

.thinking-inline::-webkit-details-marker {
  display: none;
}

.thinking-inline.done {
  color: rgba(15, 23, 42, 0.42);
  cursor: pointer;
}

.thinking-inline.live {
  color: rgba(15, 23, 42, 0.48);
}

.thinking-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.55);
}

.thinking-dot.active {
  background: rgba(37, 99, 235, 0.72);
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.08);
  animation: thinking-pulse 1.2s ease-in-out infinite;
}

.thinking-dot.done {
  background: rgba(15, 23, 42, 0.38);
}

.thinking-text {
  color: rgba(15, 23, 42, 0.62);
  font-weight: 500;
  white-space: nowrap;
}

.thinking-inline.done .thinking-text {
  color: rgba(15, 23, 42, 0.52);
}

.thinking-subtext {
  color: rgba(100, 116, 139, 0.82);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thinking-toggle {
  margin-left: 4px;
  color: rgba(37, 99, 235, 0.72);
  font-size: 11px;
  white-space: nowrap;
}

.thinking-details {
  margin-top: 6px;
  padding: 10px 0 4px 14px;
  border-left: 1px solid rgba(148, 163, 184, 0.16);
}

.thinking-details.card {
  margin-top: 10px;
  padding: 14px 16px 16px;
  border-left: none;
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.1), transparent 34%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(248, 250, 252, 0.95));
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.thinking-overview {
  margin-bottom: 14px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.thinking-overview-item {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.thinking-overview-label {
  display: block;
  font-size: 11px;
  color: rgba(100, 116, 139, 0.9);
}

.thinking-overview-value {
  display: block;
  margin-top: 6px;
  font-size: 13px;
  font-weight: 700;
  color: rgba(15, 23, 42, 0.78);
  word-break: break-word;
}

.thinking-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.thinking-detail-item {
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.76);
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.thinking-detail-grid.card {
  margin-top: 12px;
}

.thinking-detail-item.card {
  background: rgba(255, 255, 255, 0.72);
}

.thinking-detail-label {
  display: block;
  font-size: 11px;
  color: rgba(100, 116, 139, 0.88);
}

.thinking-detail-value {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: rgba(15, 23, 42, 0.72);
  word-break: break-word;
}

@keyframes thinking-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.15); opacity: 0.72; }
}

@media (max-width: 768px) {
  .thinking-inline {
    display: flex;
    align-items: flex-start;
  }

  .thinking-text,
  .thinking-subtext {
    white-space: normal;
  }

  .thinking-detail-grid {
    grid-template-columns: 1fr;
  }

  .thinking-overview {
    grid-template-columns: 1fr;
  }
}
</style>
