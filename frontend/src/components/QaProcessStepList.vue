<template>
  <div class="qa-process-steps">
    <div v-for="step in steps" :key="step.key" class="qa-process-step">
      <div class="qa-process-step-marker"></div>
      <div class="qa-process-step-body">
        <div class="qa-process-step-head">
          <span class="qa-process-step-label">{{ step.label }}</span>
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
import type { QaProcessStepViewModel } from "@/types";

defineProps<{
  steps: QaProcessStepViewModel[];
}>();

function formatDuration(value: number): string {
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} s`;
  }
  return `${Math.round(value)} ms`;
}
</script>

<style scoped>
.qa-process-steps {
  display: flex;
  flex-direction: column;
  gap: 12px;
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
  background: linear-gradient(135deg, rgba(13, 148, 136, 0.95), rgba(14, 116, 144, 0.95));
  box-shadow: 0 0 0 4px rgba(13, 148, 136, 0.12);
}

.qa-process-step-body {
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.78);
}

.qa-process-step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
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
