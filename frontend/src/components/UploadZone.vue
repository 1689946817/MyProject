<!--
  UploadZone - 文件上传入口组件
  功能：提供拖拽上传和点击选择文件能力；默认模式保留传统拖拽区，紧凑模式改为工具栏式入口条。
-->
<template>
  <div
    class="upload-zone"
    :class="{ 'is-dragover': isDragover, 'is-compact': compact }"
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

    <template v-if="compact">
      <div class="upload-toolbar">
        <div class="upload-toolbar-main">
          <div class="upload-toolbar-icon">
            <i class="i-ep-upload"></i>
          </div>
          <div class="upload-toolbar-copy">
            <p class="upload-toolbar-title">{{ text }}</p>
            <div class="upload-toolbar-meta">
              <span v-if="hint">{{ hint }}</span>
              <span v-if="hint" class="upload-toolbar-bullet">•</span>
              <span>{{ t("common.dragDropOptional") }}</span>
            </div>
          </div>
        </div>

        <div class="upload-toolbar-files">
          <template v-if="files.length > 0">
            <div
              v-for="(file, index) in compactVisibleFiles"
              :key="`${file.name}-${index}`"
              class="toolbar-file-chip"
            >
              <i class="i-ep-document"></i>
              <span class="toolbar-file-name">{{ file.name }}</span>
              <button class="remove-btn chip-remove-btn" @click.stop="removeFile(index)">
                <i class="i-ep-close"></i>
              </button>
            </div>
            <span v-if="hiddenFileCount > 0" class="toolbar-file-more">+{{ hiddenFileCount }}</span>
          </template>
          <span v-else class="upload-toolbar-empty">{{ t("common.noFileSelected") }}</span>
        </div>

        <button class="upload-select-btn" @click.stop="triggerInput">
          <i class="i-ep-folder-opened"></i>
          <span>{{ t("common.chooseFiles") }}</span>
        </button>
      </div>
    </template>

    <template v-else>
      <div class="upload-content">
        <div class="upload-icon">
          <i class="i-ep-upload"></i>
        </div>
        <p class="upload-text">{{ text }}</p>
        <p v-if="hint" class="upload-hint">{{ hint }}</p>
      </div>

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
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const props = withDefaults(defineProps<{
  files?: File[]
  text?: string
  hint?: string
  accept?: string
  multiple?: boolean
  compact?: boolean
}>(), {
  files: () => [],
  text: "",
  hint: "",
  accept: "image/*",
  multiple: true,
  compact: false,
});

const emit = defineEmits<{
  "update:files": [File[]]
}>();

const fileInput = ref<HTMLInputElement>();
const isDragover = ref(false);
const files = ref<File[]>([]);

const compactVisibleFiles = computed(() => files.value.slice(0, 2));
const hiddenFileCount = computed(() => Math.max(files.value.length - compactVisibleFiles.value.length, 0));

watch(
  () => props.files,
  (nextFiles) => {
    files.value = [...(nextFiles || [])];
  },
  { immediate: true },
);

function triggerInput() {
  fileInput.value?.click();
}

function onDragover() {
  isDragover.value = true;
}

function onDragleave() {
  isDragover.value = false;
}

function onDrop(event: DragEvent) {
  isDragover.value = false;
  addFiles(Array.from(event.dataTransfer?.files || []));
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement;
  addFiles(Array.from(target.files || []));
}

function addFiles(newFiles: File[]) {
  if (props.multiple) {
    files.value = [...files.value, ...newFiles];
  } else {
    files.value = newFiles.slice(0, 1);
  }
  emit("update:files", files.value);
}

function removeFile(index: number) {
  files.value.splice(index, 1);
  emit("update:files", files.value);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function clearFiles() {
  files.value = [];
  emit("update:files", []);
}

defineExpose({
  clearFiles,
});
</script>

<style scoped>
.upload-zone {
  border: 1.5px dashed rgba(37, 99, 235, 0.24);
  border-radius: 22px;
  padding: 34px 28px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, box-shadow 0.18s ease;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.08), transparent 24%),
    var(--surface-panel);
  backdrop-filter: blur(12px);
}

.upload-zone:hover {
  border-color: var(--border-strong);
  background: var(--bg-tertiary);
}

.upload-zone.is-dragover {
  border-color: var(--accent-primary);
  background: var(--bg-accent-soft);
  box-shadow: var(--shadow-focus);
}

.upload-zone.is-compact {
  padding: 12px 14px;
  border-radius: 18px;
  background: var(--surface-panel);
}

.upload-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
}

.upload-toolbar-main {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.upload-toolbar-icon {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: rgba(37, 99, 235, 0.1);
  color: var(--accent-primary);
  font-size: 18px;
  border: 1px solid rgba(37, 99, 235, 0.14);
}

.upload-toolbar-copy {
  min-width: 0;
  text-align: left;
}

.upload-toolbar-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}

.upload-toolbar-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.upload-toolbar-bullet {
  color: var(--text-tertiary);
}

.upload-toolbar-files {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.upload-toolbar-empty {
  font-size: 12px;
  color: var(--text-tertiary);
}

.toolbar-file-chip {
  max-width: 220px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--border-color);
  background: var(--surface-card);
  font-size: 12px;
  color: var(--text-primary);
}

.toolbar-file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.toolbar-file-more {
  font-size: 12px;
  color: var(--text-secondary);
}

.upload-select-btn {
  height: 34px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background: var(--surface-card);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.18s ease, color 0.18s ease, background-color 0.18s ease;
}

.upload-select-btn:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  background: rgba(37, 99, 235, 0.06);
}

.upload-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.upload-icon {
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
  border-radius: 18px;
  border: 1px solid rgba(37, 99, 235, 0.12);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.upload-zone:hover .upload-icon,
.upload-zone.is-dragover .upload-icon {
  transform: translateY(-1px);
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.14);
}

.upload-text {
  font-size: 15px;
  font-weight: 600;
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
  padding: 10px 12px;
  background: var(--surface-card);
  border-radius: 14px;
  border: 1px solid var(--border-color);
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
  background: rgba(220, 38, 38, 0.12);
  color: var(--danger-color);
}

.chip-remove-btn {
  margin-left: 0;
  width: 16px;
  height: 16px;
}

@media (max-width: 960px) {
  .upload-toolbar {
    grid-template-columns: 1fr;
  }

  .upload-select-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
