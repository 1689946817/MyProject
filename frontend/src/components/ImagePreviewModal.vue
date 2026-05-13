<!--
  ImagePreviewModal - 图片预览弹窗组件
  功能：以模态弹窗形式全屏预览图片，展示图片详情（标题、描述、ID、上传时间、相似度）。
  使用 teleport 到 body 避免层叠上下文问题，支持 ESC 键关闭和点击遮罩关闭。
  打开时锁定页面滚动，关闭时恢复。
-->
<template>
  <teleport to="body">
    <transition name="modal-fade">
      <div v-if="visible" class="preview-modal" @click.self="close">
        <div class="modal-content">
          <!-- 关闭按钮 -->
          <button class="close-btn" @click="close">
            <i class="i-ep-close"></i>
          </button>

          <!-- 图片 -->
          <div class="image-container">
            <img :src="src" :alt="title" class="preview-image" @error="onImgError" />
          </div>

          <!-- 信息区域 -->
          <div class="info-panel">
            <h3 class="info-title">{{ title || '预览' }}</h3>

            <div v-if="description" class="info-item">
              <label>{{ t('kb.description') }}:</label>
              <p>{{ description }}</p>
            </div>

            <div v-if="id" class="info-item">
              <label>{{ t('kb.id') }}:</label>
              <p class="id-text">{{ id }}</p>
            </div>

            <div v-if="uploadTime" class="info-item">
              <label>{{ t('docs.uploadTime') }}:</label>
              <p>{{ formatDate(uploadTime) }}</p>
            </div>

            <div v-if="scoreLabel" class="info-item">
              <label>{{ t('search.similarity') }}:</label>
              <p>{{ scoreLabel }}</p>
            </div>

            <div v-else-if="score !== undefined" class="info-item">
              <label>{{ t('search.similarity') }}:</label>
              <div class="score-visual">
                <div class="score-bar-large">
                  <div class="score-fill" :style="{ width: `${score * 100}%` }"></div>
                </div>
                <span class="score-value">{{ (score * 100).toFixed(1) }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
// ---- 导入依赖 ----
import { watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatDate } from '@/utils/image'

const { t } = useI18n()

// ---- Props ----
const props = defineProps<{
  /** 弹窗是否可见（v-model 双向绑定） */
  visible: boolean
  /** 图片 URL 地址 */
  src: string
  /** 图片标题 */
  title?: string
  /** 图片描述 */
  description?: string
  /** 图片记录 ID */
  id?: string
  /** 上传时间 */
  uploadTime?: string
  /** 相似度分数（0-1） */
  score?: number
  /** 自定义相似度标签文本 */
  scoreLabel?: string
}>()

// ---- 事件定义 ----
const emit = defineEmits<{
  /** 更新弹窗可见状态（v-model:visible） */
  'update:visible': [boolean]
}>()

// ---- 方法 ----
/** 关闭弹窗 */
function close() {
  emit('update:visible', false)
}

/** 图片加载失败时替换为 SVG 占位图 */
function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200"><rect fill="%231a1a2e" width="200" height="200"/><text fill="%23666" font-size="14" text-anchor="middle" x="100" y="100">Image not available</text></svg>'
}

/** 监听 ESC 键关闭弹窗 */
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.visible) {
    close()
  }
}

// ---- 生命周期 ----
/** 监听弹窗可见性变化，打开时锁定页面滚动，关闭时恢复 */
watch(() => props.visible, (val) => {
  if (val) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
})

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.preview-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(7, 12, 24, 0.78);
  backdrop-filter: blur(14px);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.modal-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  gap: 24px;
  background: var(--accent-surface);
  border-radius: 24px;
  border: 1px solid var(--border-color);
  box-shadow: 0 30px 80px rgba(2, 6, 23, 0.42);
  backdrop-filter: blur(18px);
  overflow: hidden;
}

.close-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 36px;
  height: 36px;
  border: none;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  z-index: 10;
  transition: all 0.3s ease;
}

.close-btn:hover {
  background: var(--accent-primary);
  color: #fff;
}

.image-container {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  padding: 20px;
  min-width: 400px;
  max-width: 60vw;
}

.preview-image {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.2);
}

.info-panel {
  width: 300px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

.info-title {
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
  margin: 0 0 8px;
  word-break: break-all;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-item label {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.info-item p {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
  word-break: break-all;
}

.id-text {
  font-family: monospace;
  font-size: 12px !important;
  background: var(--bg-tertiary);
  padding: 8px;
  border-radius: 4px;
}

.score-visual {
  display: flex;
  align-items: center;
  gap: 12px;
}

.score-bar-large {
  flex: 1;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  background: var(--accent-gradient);
  border-radius: 4px;
}

.score-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent-primary);
}

/* 动画 */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: all 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .modal-content,
.modal-fade-leave-to .modal-content {
  transform: scale(0.9);
}
</style>
