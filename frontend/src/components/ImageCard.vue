<template>
  <div class="image-card glass-card" @click="$emit('click')">
    <div class="card-image-wrapper">
      <img
        :src="src"
        :alt="title"
        class="card-image"
        @error="onImgError"
      />
      <div class="card-overlay">
        <p class="card-description">{{ description }}</p>
      </div>
      <!-- 状态标签 -->
      <div v-if="status" class="status-tag" :class="status.toLowerCase()">
        <span v-if="status === 'Processing'" class="pulse-dot"></span>
        {{ statusText }}
      </div>
      <!-- 相似度 -->
      <div v-if="score !== undefined" class="score-badge">
        <div class="score-bar">
          <div class="score-fill" :style="{ width: `${score * 100}%` }"></div>
        </div>
        <span class="score-text">{{ (score * 100).toFixed(0) }}%</span>
      </div>
    </div>
    <div class="card-info">
      <p class="card-title" :title="title">{{ title }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  src: string
  title?: string
  description?: string
  score?: number
  status?: 'Processing' | 'Completed' | 'Failed'
}>()

defineEmits<{
  click: []
}>()

const statusText = computed(() => {
  if (!props.status) return ''
  switch (props.status) {
    case 'Processing': return t('kb.processing')
    case 'Completed': return t('kb.completed')
    case 'Failed': return t('kb.failed')
    default: return props.status
  }
})

function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}
</script>

<style scoped>
.image-card {
  overflow: hidden;
  cursor: pointer;
  border-radius: 16px;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.image-card:hover {
  transform: translateY(-2px);
  border-color: var(--border-strong);
  box-shadow: var(--shadow-md);
}

.card-image-wrapper {
  position: relative;
  width: 100%;
  height: 180px;
  overflow: hidden;
  background: var(--bg-tertiary);
}

.card-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.22s ease;
}

.image-card:hover .card-image {
  transform: scale(1.04);
}

.card-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 12px;
  background: linear-gradient(to top, rgba(15, 23, 42, 0.82), transparent);
  transform: translateY(100%);
  transition: transform 0.3s ease;
}

.image-card:hover .card-overlay {
  transform: translateY(0);
}

.card-description {
  font-size: 12px;
  color: #fff;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.status-tag {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.status-tag.processing {
  color: var(--accent-primary);
  border: 1px solid rgba(37, 99, 235, 0.22);
  background: rgba(255, 255, 255, 0.72);
}

.status-tag.completed {
  color: var(--success-color);
  border: 1px solid rgba(21, 128, 61, 0.24);
  background: rgba(255, 255, 255, 0.72);
}

.status-tag.failed {
  color: var(--danger-color);
  border: 1px solid rgba(220, 38, 38, 0.2);
  background: rgba(255, 255, 255, 0.72);
}

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-primary);
  animation: pulse-glow 1.5s ease-in-out infinite;
}

.score-badge {
  position: absolute;
  bottom: 8px;
  left: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.score-bar {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  background: linear-gradient(90deg, #2563eb 0%, #60a5fa 100%);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.score-text {
  font-size: 10px;
  color: #fff;
  font-weight: 600;
  background: rgba(0, 0, 0, 0.5);
  padding: 2px 6px;
  border-radius: 3px;
}

.card-info {
  padding: 14px;
}

.card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
