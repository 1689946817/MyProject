<!--
  QaProcessStepList - RAG 处理步骤列表
  功能：以时间线样式展示 RAG 处理过程中的各个步骤（如检索、重排、生成等），
  每个步骤包含状态标记、耗时、摘要和详细参数。支持紧凑（compact）模式用于流式展示。
-->
<template>
  <div class="qa-process-steps" :class="{ compact }">
    <div v-for="step in steps" :key="step.key" class="qa-process-step">
      <div class="qa-process-step-marker" :class="statusClass(step)"></div>
      <div class="qa-process-step-body">
        <div class="qa-process-step-head">
          <div class="qa-process-step-head-main">
            <span class="qa-process-step-label">{{ step.label }}</span>
            <span v-if="step.status" class="qa-process-step-status" :class="statusClass(step)">
              {{ formatStatus(step.status) }}
            </span>
          </div>
          <span v-if="step.durationMs !== null && step.durationMs !== undefined" class="qa-process-step-time">
            {{ formatDuration(step.durationMs) }}
          </span>
        </div>
        <div v-if="step.summary" class="qa-process-step-summary">{{ step.summary }}</div>
        <div v-if="step.details.length > 0" class="qa-process-step-details">
          <div v-for="detail in step.details" :key="`${step.key}-${detail.key}`" class="qa-process-step-detail">
            <span class="qa-process-step-detail-key">{{ detail.label }}</span>
            <span class="qa-process-step-detail-value">{{ detail.value }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// ---- 导入依赖 ----
import { useI18n } from "vue-i18n";
import type { QaProcessStepViewModel } from "@/types";

// ---- Props ----
defineProps<{
  /** 步骤视图模型列表 */
  steps: QaProcessStepViewModel[];
  /** 是否使用紧凑模式（省略卡片背景，间距更小） */
  compact?: boolean;
}>();

const { t } = useI18n();

// ---- 工具函数 ----
/** 将毫秒数格式化为 "X.XX s" 或 "X ms" 格式 */
function formatDuration(value: number): string {
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} s`;
  }
  return `${Math.round(value)} ms`;
}

/** 将步骤状态枚举映射为国际化文本 */
function formatStatus(status: QaProcessStepViewModel["status"]): string {
  if (status === "completed") return t("chat.processStatusCompleted");
  if (status === "skipped") return t("chat.processStatusSkipped");
  if (status === "failed") return t("chat.processStatusFailed");
  return t("chat.processStatusRunning");
}

/** 根据步骤状态和 isActive 标记返回对应的 CSS 类名 */
function statusClass(step: QaProcessStepViewModel): string {
  if (step.status === "completed") return "is-completed";
  if (step.status === "skipped") return "is-skipped";
  if (step.status === "failed") return "is-failed";
  if (step.isActive || step.status === "started" || step.status === "running") return "is-active";
  return "is-pending";
}
</script>

<style scoped>
.qa-process-steps {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.qa-process-steps.compact {
  gap: 8px;
}

.qa-process-step {
  display: grid;
  grid-template-columns: 12px 1fr;
  gap: 12px;
  align-items: flex-start;
}

.qa-process-step-marker {
  width: 12px;
  height: 12px;
  margin-top: 6px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.75);
  box-shadow: 0 0 0 4px rgba(148, 163, 184, 0.14);
}

.qa-process-step-body {
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.78);
}

.qa-process-steps.compact .qa-process-step-body {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.68);
}

.qa-process-step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.qa-process-step-head-main {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}

.qa-process-step-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.qa-process-step-time {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(14, 116, 144, 0.1);
  color: #0f766e;
  font-size: 12px;
  font-weight: 600;
}

.qa-process-step-status {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.qa-process-step-marker.is-active,
.qa-process-step-status.is-active {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.95), rgba(14, 165, 233, 0.95));
  box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.14);
  color: #075985;
}

.qa-process-step-marker.is-completed,
.qa-process-step-status.is-completed {
  background: linear-gradient(135deg, rgba(13, 148, 136, 0.95), rgba(14, 116, 144, 0.95));
  box-shadow: 0 0 0 4px rgba(13, 148, 136, 0.12);
  color: #0f766e;
}

.qa-process-step-marker.is-skipped,
.qa-process-step-status.is-skipped {
  background: rgba(148, 163, 184, 0.18);
  box-shadow: none;
  color: var(--text-tertiary);
}

.qa-process-step-marker.is-failed,
.qa-process-step-status.is-failed {
  background: rgba(220, 38, 38, 0.15);
  box-shadow: 0 0 0 4px rgba(220, 38, 38, 0.08);
  color: #b91c1c;
}

.qa-process-step-summary {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.qa-process-step-details {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.qa-process-step-detail {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  line-height: 1.5;
}

.qa-process-step-detail-key {
  flex-shrink: 0;
  color: var(--text-tertiary);
}

.qa-process-step-detail-value {
  text-align: right;
  color: var(--text-secondary);
  word-break: break-word;
}

@media (max-width: 768px) {
  .qa-process-step {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .qa-process-step-marker {
    display: none;
  }

  .qa-process-step-body {
    padding: 12px;
  }

  .qa-process-step-detail {
    flex-direction: column;
    gap: 2px;
  }

  .qa-process-step-detail-value {
    text-align: left;
  }
}
</style>
