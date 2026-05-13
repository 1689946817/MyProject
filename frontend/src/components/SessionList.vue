<!--
  SessionList - 聊天会话侧栏列表组件
  功能：展示用户的聊天会话列表，支持新建、重命名、删除会话，以及折叠/展开侧栏。
  当前活跃会话高亮显示，悬停时显示编辑和删除操作按钮。
-->
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
// ---- 导入依赖 ----
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessageBox } from 'element-plus'
import type { ChatSession } from '@/types'
import { formatDate } from '@/utils/image'

const { t } = useI18n()

// ---- Props ----
defineProps<{
  /** 会话列表数据 */
  sessions: ChatSession[]
  /** 当前活跃会话 ID */
  activeId?: string
  /** 是否折叠侧栏 */
  collapsed?: boolean
}>()

// ---- 事件定义 ----
const emit = defineEmits<{
  /** 选择会话 */
  select: [string]
  /** 新建会话 */
  create: []
  /** 请求重命名会话（打开对话框） */
  rename: [string]
  /** 提交会话标题修改 */
  updateTitle: [string, string]
  /** 删除会话 */
  delete: [string]
  /** 切换侧栏折叠状态 */
  toggleCollapse: []
}>()

// ---- 重命名对话框状态 ----
const renameDialogVisible = ref(false)   // 对话框是否可见
const renameValue = ref('')               // 重命名输入框的值
const renameTargetId = ref('')            // 当前正在重命名的会话 ID

// ---- 方法 ----
/** 弹出确认对话框，用户确认后触发 delete 事件 */
function confirmDelete(id: string) {
  ElMessageBox.confirm(t('common.confirmDelete'), t('common.delete'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning'
  }).then(() => {
    emit('delete', id)
  }).catch(() => {})
}

/** 执行重命名：提交新标题并关闭对话框 */
function doRename() {
  if (renameTargetId.value && renameValue.value.trim()) {
    emit('updateTitle', renameTargetId.value, renameValue.value.trim())
  }
  renameDialogVisible.value = false
}

/** 打开重命名对话框并填充当前标题（通过 defineExpose 暴露给父组件调用） */
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
  gap: 10px;
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
  width: 40px;
  height: 40px;
  border: 1px solid var(--border-color);
  background: rgba(255, 255, 255, 0.68);
  color: var(--text-secondary);
  border-radius: 14px;
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
  padding: 13px 16px;
  font-size: 14px;
  font-weight: 600;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.18);
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
  padding: 14px 14px 14px 16px;
  border-radius: 18px;
  cursor: pointer;
  position: relative;
  transition: border-color 0.18s ease, background-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--border-color);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.04);
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.92);
  border-color: var(--border-strong);
  transform: translateY(-1px);
}

.session-item.is-active {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.1), rgba(96, 165, 250, 0.05));
  border-color: rgba(37, 99, 235, 0.2);
  box-shadow: 0 18px 40px rgba(37, 99, 235, 0.12);
}

.session-content {
  padding-right: 60px;
}

.session-title {
  font-size: 14px;
  font-weight: 700;
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
  background: rgba(255, 255, 255, 0.72);
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
