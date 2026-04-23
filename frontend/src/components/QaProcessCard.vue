<template>
  <details v-if="shouldRender" class="qa-process-card" :open="isAgenticMode">
    <summary class="qa-process-summary">
      <div class="qa-process-summary-main">
        <span class="qa-process-title">{{ t("chat.answerProcess") }}</span>
        <span class="qa-process-caption">{{ processCaption }}</span>
      </div>
      <div class="qa-process-summary-meta">
        <span v-if="summary.totalMs !== null && summary.totalMs !== undefined" class="qa-process-pill">
          {{ t("chat.processTotal") }} {{ formatDuration(summary.totalMs) }}
        </span>
        <span v-if="summary.retryUsed" class="qa-process-pill warn">{{ t("chat.processRetryUsed") }}</span>
      </div>
    </summary>

    <div class="qa-process-content">
      <div class="qa-process-overview">
        <div class="qa-process-overview-item">
          <span class="qa-process-overview-label">{{ t("chat.processExecutionMode") }}</span>
          <span class="qa-process-overview-value">{{ summary.executionMode }}</span>
        </div>
        <div class="qa-process-overview-item">
          <span class="qa-process-overview-label">{{ t("chat.processPresentationMode") }}</span>
          <span class="qa-process-overview-value">{{ summary.presentationMode }}</span>
        </div>
        <div class="qa-process-overview-item">
          <span class="qa-process-overview-label">{{ t("chat.processKnowledgeRoute") }}</span>
          <span class="qa-process-overview-value">{{ summary.useRag ? t("chat.processEnabled") : t("chat.processDisabled") }}</span>
        </div>
      </div>

      <QaProcessStepList :steps="processSteps" />
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import QaProcessStepList from "@/components/QaProcessStepList.vue";
import type { ChatMessage, QaProcessStepViewModel, QaProcessSummaryViewModel, RetrievalStepItem, TimingStage, TimingSummary } from "@/types";

const props = defineProps<{
  message: ChatMessage;
}>();

const { t } = useI18n();

const timingSummary = computed<TimingSummary | null>(() => {
  return (props.message.timings as TimingSummary | null | undefined)
    || (props.message.retrieval_params?.timings as TimingSummary | null | undefined)
    || null;
});

const timingStageMap = computed<Record<string, TimingStage>>(() => {
  return Object.fromEntries((timingSummary.value?.stages || []).map((stage) => [stage.name, stage]));
});

const rawSteps = computed<RetrievalStepItem[]>(() => props.message.retrieval_steps || []);

const processSteps = computed<QaProcessStepViewModel[]>(() => {
  const preferredOrder = ["intent", "query", "retrieve", "retrieval", "grade", "grading", "retry", "generate"];
  const sortedSteps = [...rawSteps.value].sort((left, right) => {
    const leftIdx = preferredOrder.indexOf(left.key);
    const rightIdx = preferredOrder.indexOf(right.key);
    return (leftIdx === -1 ? preferredOrder.length : leftIdx) - (rightIdx === -1 ? preferredOrder.length : rightIdx);
  });
  const mappedSteps = sortedSteps.map((step) => ({
    key: step.key,
    label: mapStepLabel(step),
    summary: step.summary,
    durationMs: lookupDuration(step.key),
    details: toDetailItems(step.details || {}),
  }));

  if (!mappedSteps.some((step) => step.key === "generate") && props.message.role === "assistant" && props.message.content) {
    mappedSteps.push({
      key: "generate",
      label: t("chat.processGenerate"),
      summary: t("chat.processGenerateSummary"),
      durationMs: lookupDuration("generate"),
      details: [],
    });
  }

  return mappedSteps;
});

const summary = computed<QaProcessSummaryViewModel>(() => {
  const executionMode = props.message.execution_mode || props.message.retrieval_params?.execution_mode || "unknown";
  const presentationMode = props.message.presentation_mode || props.message.retrieval_params?.presentation_mode || "unknown";
  const useRag = Boolean(props.message.use_rag ?? props.message.retrieval_params?.use_rag);
  const retryUsed = processSteps.value.some((step) => step.key === "retry")
    || Boolean(timingStageMap.value.agentic_retrieve_retry);
  const totalMs = timingSummary.value?.total_ms
    ?? timingStageMap.value.agentic_graph_total?.elapsed_ms
    ?? timingStageMap.value.rag_chat_total?.elapsed_ms
    ?? null;

  return {
    executionMode,
    presentationMode,
    useRag,
    totalMs,
    retryUsed,
  };
});

const shouldRender = computed(() => props.message.role === "assistant" && (rawSteps.value.length > 0 || Boolean(timingSummary.value)));
const isAgenticMode = computed(() => summary.value.executionMode === "multimodal_rag");
const processCaption = computed(() => {
  if (summary.value.retryUsed) {
    return t("chat.processRetryCaption");
  }
  if (summary.value.useRag) {
    return t("chat.processRagCaption");
  }
  return t("chat.processDirectCaption");
});

function mapStepLabel(step: RetrievalStepItem): string {
  if (step.key === "intent") return t("chat.processIntent");
  if (step.key === "query") return t("chat.processQuery");
  if (step.key === "retrieve" || step.key === "retrieval") return t("chat.processRetrieve");
  if (step.key === "grade" || step.key === "grading") return t("chat.processGrade");
  if (step.key === "retry") return t("chat.processRetry");
  if (step.key === "generate") return t("chat.processGenerate");
  return step.label;
}

function lookupDuration(stepKey: string): number | null {
  const names = timingStageNames(stepKey);
  for (const name of names) {
    const stage = timingStageMap.value[name];
    if (stage) {
      return stage.elapsed_ms;
    }
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
      label: key,
      value: formatDetailValue(value),
    }));
}

function formatDetailValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? t("chat.processYes") : t("chat.processNo");
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch (_error) {
      return String(value);
    }
  }
  return String(value);
}

function formatDuration(value: number): string {
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} s`;
  }
  return `${Math.round(value)} ms`;
}
</script>

<style scoped>
.qa-process-card {
  margin-top: 12px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 20px;
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.14), transparent 34%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(248, 250, 252, 0.96));
  overflow: hidden;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.05);
}

.qa-process-summary {
  list-style: none;
  cursor: pointer;
  padding: 14px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.qa-process-summary::-webkit-details-marker {
  display: none;
}

.qa-process-summary-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.qa-process-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.qa-process-caption {
  font-size: 12px;
  color: var(--text-secondary);
}

.qa-process-summary-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.qa-process-pill {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
}

.qa-process-pill.warn {
  background: rgba(245, 158, 11, 0.16);
  color: #b45309;
}

.qa-process-content {
  padding: 0 18px 18px;
}

.qa-process-overview {
  margin-bottom: 14px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.qa-process-overview-item {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.qa-process-overview-label {
  display: block;
  font-size: 11px;
  color: var(--text-tertiary);
}

.qa-process-overview-value {
  display: block;
  margin-top: 6px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  word-break: break-word;
}

@media (max-width: 768px) {
  .qa-process-summary {
    padding: 12px 14px;
    flex-direction: column;
    align-items: flex-start;
  }

  .qa-process-summary-meta {
    justify-content: flex-start;
  }

  .qa-process-content {
    padding: 0 14px 14px;
  }

  .qa-process-overview {
    grid-template-columns: 1fr;
  }
}
</style>
