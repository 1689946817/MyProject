<template>
  <div
    class="upload-zone"
    :class="{ 'is-dragover': isDragover }"
    @dragover.prevent="onDragover"
    @dragleave.prevent="onDragleave"
    @drop.prevent="onDrop"
    @click="triggerInput"
  >
    <input
      ref="fileInput"
      type="file"
      :accept="accept"
      :multiple="multiple"
      hidden
      @change="onFileChange"
    />

    <div class="upload-content">
      <div class="upload-icon" :class="{ 'pulse-glow': isDragover }">
        <i class="i-ep-upload"></i>
      </div>
      <p class="upload-text">{{ text }}</p>
      <p v-if="hint" class="upload-hint">{{ hint }}</p>
    </div>

    <!-- 已选择文件预览 -->
    <div v-if="files.length > 0" class="file-list">
      <div v-for="(file, index) in files" :key="index" class="file-item">
        <i class="i-ep-file mr-2"></i>
        <span class="file-name">{{ file.name }}</span>
        <span class="file-size">{{ formatSize(file.size) }}</span>
        <button class="remove-btn" @click.stop="removeFile(index)">
          <i class="i-ep-close"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  text?: string
  hint?: string
  accept?: string
  multiple?: boolean
}>(), {
  text: '',
  hint: '',
  accept: 'image/*',
  multiple: true
})

const emit = defineEmits<{
  'update:files': [File[]]
}>()

const fileInput = ref<HTMLInputElement>()
const isDragover = ref(false)
const files = ref<File[]>([])

function triggerInput() {
  fileInput.value?.click()
}

function onDragover() {
  isDragover.value = true
}

function onDragleave() {
  isDragover.value = false
}

function onDrop(e: DragEvent) {
  isDragover.value = false
  const droppedFiles = Array.from(e.dataTransfer?.files || [])
  addFiles(droppedFiles)
}

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const selectedFiles = Array.from(target.files || [])
  addFiles(selectedFiles)
}

function addFiles(newFiles: File[]) {
  if (props.multiple) {
    files.value = [...files.value, ...newFiles]
  } else {
    files.value = newFiles.slice(0, 1)
  }
  emit('update:files', files.value)
}

function removeFile(index: number) {
  files.value.splice(index, 1)
  emit('update:files', files.value)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function clearFiles() {
  files.value = []
  emit('update:files', [])
}

// 暴露方法给父组件
defineExpose({
  clearFiles
})
</script>

<style scoped>
.upload-zone {
  border: 2px dashed var(--border-color);
  border-radius: 12px;
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: var(--bg-secondary);
}

.upload-zone:hover {
  border-color: var(--accent-primary);
  background: rgba(0, 212, 255, 0.05);
}

.upload-zone.is-dragover {
  border-color: var(--accent-primary);
  background: rgba(0, 212, 255, 0.1);
  box-shadow: 0 0 20px rgba(0, 212, 255, 0.2);
}

.upload-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.upload-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  color: var(--accent-primary);
  background: rgba(0, 212, 255, 0.1);
  border-radius: 12px;
  border: 1px solid rgba(0, 212, 255, 0.3);
  transition: all 0.3s ease;
}

.upload-zone:hover .upload-icon,
.upload-zone.is-dragover .upload-icon {
  transform: scale(1.1);
  box-shadow: 0 0 20px rgba(0, 212, 255, 0.4);
}

.upload-text {
  font-size: 14px;
  color: var(--text-primary);
  margin: 0;
}

.upload-hint {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
}

.file-list {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary);
}

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  margin-left: 12px;
  color: var(--text-secondary);
  font-size: 12px;
}

.remove-btn {
  margin-left: 8px;
  width: 20px;
  height: 20px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s ease;
}

.remove-btn:hover {
  background: rgba(245, 108, 108, 0.2);
  color: #f56c6c;
}
</style>
