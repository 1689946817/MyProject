<template>
  <div class="session-list">
    <!-- 新建会话按钮 -->
    <button class="new-session-btn btn-gradient" @click="$emit('create')">
      <i class="i-ep-plus mr-2"></i>
      {{ t('chat.newSession') }}
    </button>

    <!-- 会话列表 -->
    <div v-if="sessions.length > 0" class="sessions">
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
    <el-empty v-else :description="t('chat.noSessions')" />

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
}>()

const emit = defineEmits<{
  select: [string]
  create: []
  rename: [string]
  updateTitle: [string, string]
  delete: [string]
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
}

.new-session-btn {
  width: 100%;
  padding: 12px 16px;
  font-size: 14px;
  margin-bottom: 16px;
}

.sessions {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-item {
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  position: relative;
  transition: all 0.3s ease;
  background: var(--bg-tertiary);
  border: 1px solid transparent;
}

.session-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 0;
  background: var(--accent-primary);
  border-radius: 0 2px 2px 0;
  transition: height 0.3s ease;
}

.session-item:hover {
  background: rgba(0, 212, 255, 0.1);
  border-color: rgba(0, 212, 255, 0.3);
}

.session-item.is-active {
  background: rgba(0, 212, 255, 0.15);
  border-color: var(--accent-primary);
}

.session-item.is-active::before {
  height: 24px;
  box-shadow: 0 0 10px var(--accent-primary);
}

.session-content {
  padding-right: 60px;
}

.session-title {
  font-size: 14px;
  color: var(--text-primary);
  margin: 0 0 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  font-size: 11px;
  color: var(--text-secondary);
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
  width: 28px;
  height: 28px;
  border: none;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: var(--accent-primary);
  color: #fff;
}

.action-btn.delete:hover {
  background: #f56c6c;
}
</style>
