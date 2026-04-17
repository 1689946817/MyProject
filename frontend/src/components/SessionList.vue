<template>
  <div class="session-list" :class="{ compact: collapsed }">
    <div class="session-toolbar">
      <button
        class="toolbar-btn history-toggle-btn"
        :title="collapsed ? t('chat.openHistory') : t('chat.closeHistory')"
        @click="$emit('toggleCollapse')"
      >
        <i :class="collapsed ? 'i-ep-right' : 'i-ep-back'"></i>
      </button>
    </div>

    <!-- 新建会话按钮 -->
    <button v-if="!collapsed" class="new-session-btn btn-gradient" @click="$emit('create')">
      <i class="i-ep-plus mr-2"></i>
      {{ t('chat.newSession') }}
    </button>

    <!-- 会话列表 -->
    <div v-if="sessions.length > 0 && !collapsed" class="sessions">
      <div
        v-for="session in sessions"
        :key="session.id"
        class="session-item"
        :class="{ 'is-active': session.id === activeId }"
        @click="$emit('select', session.id)"
      >
        <div class="session-content">
          <p class="session-title">{{ session.title || t('chat.newSession') }}</p>
          <p class="session-time">{{ formatDate(session.updated_at) }}</p>
        </div>
        <div class="session-actions">
          <button class="action-btn" :title="t('common.rename')" @click.stop="$emit('rename', session.id)">
            <i class="i-ep-edit"></i>
          </button>
          <button class="action-btn delete" :title="t('common.delete')" @click.stop="confirmDelete(session.id)">
            <i class="i-ep-delete"></i>
          </button>
        </div>
      </div>
    </div>
    <el-empty v-else-if="!collapsed" :description="t('chat.noSessions')" />

    <!-- 重命名对话框 -->
    <el-dialog v-model="renameDialogVisible" :title="t('common.rename')" width="400px">
      <el-input v-model="renameValue" :placeholder="t('chat.newSession')" />
      <template #footer>
        <el-button @click="renameDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="doRename">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessageBox } from 'element-plus'
import type { ChatSession } from '@/types'
import { formatDate } from '@/utils/image'

const { t } = useI18n()

defineProps<{
  sessions: ChatSession[]
  activeId?: string
  collapsed?: boolean
}>()

const emit = defineEmits<{
  select: [string]
  create: []
  rename: [string]
  updateTitle: [string, string]
  delete: [string]
  toggleCollapse: []
}>()

const renameDialogVisible = ref(false)
const renameValue = ref('')
const renameTargetId = ref('')

function confirmDelete(id: string) {
  ElMessageBox.confirm(t('common.confirmDelete'), t('common.delete'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning'
  }).then(() => {
    emit('delete', id)
  }).catch(() => {})
}

function doRename() {
  if (renameTargetId.value && renameValue.value.trim()) {
    emit('updateTitle', renameTargetId.value, renameValue.value.trim())
  }
  renameDialogVisible.value = false
}

// 打开重命名对话框（由父组件调用）
function openRenameDialog(id: string, currentTitle: string) {
  renameTargetId.value = id
  renameValue.value = currentTitle || ''
  renameDialogVisible.value = true
}

defineExpose({
  openRenameDialog
})
</script>

<style scoped>
.session-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 12px;
}

.session-list.compact {
  align-items: center;
  justify-content: flex-start;
  gap: 14px;
}

.session-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.session-list.compact .session-toolbar {
  flex-direction: column;
  width: 100%;
}

.toolbar-btn {
  width: 38px;
  height: 38px;
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border-radius: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: border-color 0.18s ease, color 0.18s ease, background-color 0.18s ease, transform 0.18s ease;
}

.toolbar-btn:hover {
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
  border-color: var(--border-strong);
}

.new-session-btn {
  width: 100%;
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 600;
}

.sessions {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}

.session-item {
  padding: 14px;
  border-radius: 14px;
  cursor: pointer;
  position: relative;
  transition: border-color 0.18s ease, background-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  box-shadow: none;
}

.session-item:hover {
  background: var(--bg-tertiary);
  border-color: var(--border-strong);
  transform: translateY(-1px);
}

.session-item.is-active {
  background: var(--bg-accent-soft);
  border-color: rgba(37, 99, 235, 0.2);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.08);
}

.session-content {
  padding-right: 60px;
}

.session-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0;
}

.session-actions {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.session-item:hover .session-actions {
  opacity: 1;
}

.action-btn {
  width: 30px;
  height: 30px;
  border: none;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  border: 1px solid var(--border-color);
  transition: border-color 0.18s ease, color 0.18s ease, background-color 0.18s ease;
}

.action-btn:hover {
  background: var(--bg-accent-soft);
  color: var(--accent-primary);
  border-color: rgba(37, 99, 235, 0.18);
}

.action-btn.delete:hover {
  background: rgba(220, 38, 38, 0.08);
  color: var(--danger-color);
  border-color: rgba(220, 38, 38, 0.14);
}
</style>
