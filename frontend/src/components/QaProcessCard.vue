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

const props = defineProps<{
  message: ChatMessage;
}>();

const { t } = useI18n();
const now = ref(Date.now());
const detailsOpen = ref(false);
let timer = 0;

const liveSteps = computed<ChatProgressEvent[]>(() => props.message.live_progress_steps || []);
const latestStep = computed<ChatProgressEvent | null>(() => props.message.live_progress || liveSteps.value.at(-1) || null);
const rawSteps = computed<RetrievalStepItem[]>(() => props.message.retrieval_steps || []);
const isLive = computed(() => liveSteps.value.length > 0);
const isDone = computed(() => Boolean(props.message.live_progress_done) || (!isLive.value && rawSteps.value.length > 0));

const timingSummary = computed<TimingSummary | null>(() => {
  return (props.message.timings as TimingSummary | null | undefined)
    || (props.message.retrieval_params?.timings as TimingSummary | null | undefined)
    || null;
});

const timingStageMap = computed<Record<string, TimingStage>>(() => {
  return Object.fromEntries((timingSummary.value?.stages || []).map((stage) => [stage.name, stage]));
});

const liveMeta = computed<Record<string, unknown>>(() => {
  return liveSteps.value.reduce<Record<string, unknown>>((acc, step) => {
    Object.assign(acc, step.meta || {});
    return acc;
  }, {});
});

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

const shouldRender = computed(() => props.message.role === "assistant" && (isLive.value || rawSteps.value.length > 0 || Boolean(timingSummary.value)));

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

const dotClass = computed(() => {
  if (isLive.value) return "active";
  if (isDone.value) return "done";
  return "";
});

const modeValue = computed(() => props.message.chat_mode || (props.message.retrieval_params?.chat_mode as ChatMode | undefined));
const executionModeValue = computed(() => props.message.execution_mode || props.message.retrieval_params?.execution_mode || "");
const useRagValue = computed(() => props.message.use_rag ?? props.message.retrieval_params?.use_rag);

watch(isLive, (value) => {
  if (value) {
    detailsOpen.value = false;
  }
}, { immediate: true });

onMounted(() => {
  timer = window.setInterval(() => {
    if (isLive.value && !props.message.live_progress_done) {
      now.value = Date.now();
    }
  }, 300);
});

onBeforeUnmount(() => {
  window.clearInterval(timer);
});

function handleSummaryClick() {
  if (isLive.value) {
    return;
  }
  detailsOpen.value = !detailsOpen.value;
}

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

function mapLegacyStepLabel(step: RetrievalStepItem): string {
  if (step.key === "intent") return t("chat.processIntent");
  if (step.key === "query") return t("chat.processQuery");
  if (step.key === "retrieve" || step.key === "retrieval") return t("chat.processRetrieve");
  if (step.key === "grade" || step.key === "grading") return t("chat.processGrade");
  if (step.key === "retry") return t("chat.processRetry");
  if (step.key === "generate") return t("chat.processGenerate");
  return step.label;
}

function resolveProgressSummary(status: ChatProgressEvent["status"]): string {
  if (status === "completed") return t("chat.processStepCompleted");
  if (status === "skipped") return t("chat.processStepSkipped");
  if (status === "failed") return t("chat.processStepFailed");
  return t("chat.processStepRunning");
}

function lookupDuration(stepKey: string): number | null {
  const names = timingStageNames(stepKey);
  for (const name of names) {
    const stage = timingStageMap.value[name];
    if (stage) return stage.elapsed_ms;
  }
  return null;
}

function timingStageNames(stepKey: string): string[] {
  if (stepKey === "intent") return ["intent_classification"];
  if (stepKey === "retrieve" || stepKey === "retrieval") return ["agentic_retrieve_initial"];
  if (stepKey === "grade" || stepKey === "grading") return ["agentic_grade"];
  if (stepKey === "retry") return ["agentic_retrieve_retry"];
  if (stepKey === "generate") return ["agentic_generate"];
  return [];
}

function toDetailItems(details: Record<string, unknown>): QaProcessStepViewModel["details"] {
  return Object.entries(details)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => ({
      key,
      label: mapDetailLabel(key),
      value: formatScalar(value),
    }));
}

function mapDetailLabel(key: string): string {
  if (key === "source_scope_enabled") return t("chat.processSourceScope");
  if (key === "query_rewrite_enabled") return t("chat.processQueryRewrite");
  if (key === "retrieved_candidates") return t("chat.processCandidateCount");
  if (key === "rerank_enabled") return t("chat.processRerank");
  if (key === "compression_enabled") return t("chat.processCompression");
  if (key === "agentic_enabled") return t("chat.processAgentic");
  return key;
}

function formatBoolean(value: unknown): string {
  if (typeof value !== "boolean") return "";
  return value ? t("chat.processEnabled") : t("chat.processDisabled");
}

function formatScalar(value: unknown): string {
  if (value === undefined || value === null || value === "") return "";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? t("chat.processYes") : t("chat.processNo");
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value);
}

function formatDuration(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
  return `${Math.round(value)} ms`;
}

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
