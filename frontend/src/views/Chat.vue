<template>
  <div class="chat-page">
    <el-row :gutter="20">
      <!-- 左侧会话列表 -->
      <el-col :span="6">
        <el-card class="session-panel glass-card">
          <SessionList
            :sessions="sessions"
            :active-id="currentSessionId"
            @select="selectSession"
            @create="handleCreateSession"
            @rename="handleRenameSession"
            @update-title="updateSessionTitle"
            @delete="handleDeleteSession"
            ref="sessionListRef"
          />
        </el-card>
      </el-col>

      <!-- 右侧聊天区域 -->
      <el-col :span="18">
        <el-card class="chat-panel glass-card">
          <template #header>
            <div class="chat-header">
              <span class="chat-title">{{ currentSessionTitle || t('chat.title') }}</span>
            </div>
          </template>

          <!-- 消息区域 -->
          <div class="messages-container" ref="messagesContainer">
            <div v-if="messages.length === 0" class="empty-chat">
              <div class="empty-icon">
                <i class="i-ep-chat-dot-round"></i>
              </div>
              <p>{{ t('chat.inputPlaceholder') }}</p>
            </div>

            <div v-else class="messages-list">
              <div
                v-for="msg in messages"
                :key="msg.id"
                class="message-item"
                :class="[msg.role, msg.role === 'assistant' ? `mode-${getPresentationMode(msg)}` : '']"
              >
                <div class="message-avatar">
                  <i v-if="msg.role === 'user'" class="i-ep-user"></i>
                  <i v-else class="i-ep-bot"></i>
                </div>
                <div class="message-content">
                  <div class="message-bubble">
                    <div
                      v-if="msg.role === 'assistant'"
                      class="assistant-meta"
                    >
                      <span class="assistant-mode-badge">
                        {{ getModeLabel(msg) }}
                      </span>
                    </div>
                    <div
                      v-if="shouldShowImagesFirst(msg)"
                      class="referenced-images"
                      :class="{ prominent: isImageFocusedMode(msg) }"
                    >
                      <div
                        v-for="source in getImageSources(msg)"
                        :key="source.source_id"
                        class="ref-image-item"
                        @click="showPreview(source)"
                      >
                        <img :src="getSourceImageSrc(source)" @error="onImgError" />
                      </div>
                    </div>
                    <p
                      v-if="msg.content"
                      class="message-text"
                      :class="[
                        { 'typing': msg.role === 'assistant' && String(msg.id) === streamingId },
                        msg.role === 'assistant' ? `mode-text-${getPresentationMode(msg)}` : ''
                      ]"
                    >
                      {{ msg.content }}
                    </p>
                    <div
                      v-if="shouldShowImagesAfterText(msg)"
                      class="referenced-images"
                      :class="{ prominent: isImageFocusedMode(msg) }"
                    >
                      <div
                        v-for="source in getImageSources(msg)"
                        :key="source.source_id"
                        class="ref-image-item"
                        @click="showPreview(source)"
                      >
                        <img :src="getSourceImageSrc(source)" @error="onImgError" />
                      </div>
                    </div>
                  </div>
                  <span class="message-time">{{ formatTime(msg.created_at) }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 输入区域 -->
          <div class="input-area">
            <div class="input-row">
              <el-upload
                :auto-upload="false"
                :show-file-list="false"
                :on-change="onImageChange"
              >
                <el-button text class="attach-btn">
                  <i class="i-ep-plus"></i>
                </el-button>
              </el-upload>
              <el-input
                v-model="query"
                :placeholder="t('chat.inputPlaceholder')"
                class="chat-input"
                @keyup.enter="doChat"
                :disabled="loading"
              />
              <el-button
                type="primary"
                class="send-btn"
                :loading="loading"
                @click="doChat"
              >
                <i class="i-ep-send"></i>
              </el-button>
            </div>
            <div v-if="attachedImage" class="attached-preview">
              <img :src="attachedImagePreview" />
              <button class="remove-attached" @click="removeAttached">
                <i class="i-ep-close"></i>
              </button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 引用图片预览 -->
    <ImagePreviewModal
      v-model:visible="previewVisible"
      :src="previewSrc"
      :title="previewTitle"
      :description="previewDescription"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { UploadFile } from 'element-plus'
import {
  getSessions,
  createSession,
  renameSession,
  deleteSession,
  getSessionMessages,
  ragChat,
  type ChatSession
} from '@/api/chat'
import { imgSrc } from '@/utils/image'
import SessionList from '@/components/SessionList.vue'
import ImagePreviewModal from '@/components/ImagePreviewModal.vue'
import type { ChatMessage, ChatSourceItem } from '@/types'

const { t } = useI18n()

type SourceItem = ChatSourceItem
type Message = ChatMessage

const sessions = ref<ChatSession[]>([])
const currentSessionId = ref<string | undefined>()
const currentSessionTitle = ref('')
const messages = ref<Message[]>([])
const query = ref('')
const loading = ref(false)
const attachedImage = ref<File | null>(null)
const attachedImagePreview = ref('')
const streamingId = ref('')
const sessionListRef = ref<InstanceType<typeof SessionList>>()

// 预览
const previewVisible = ref(false)
const previewSrc = ref('')
const previewTitle = ref('')
const previewDescription = ref('')

const messagesContainer = ref<HTMLElement>()

async function loadSessions() {
  try {
    sessions.value = await getSessions()
  } catch (e) {
    console.error('加载会话列表失败:', e)
  }
}

async function loadSession(id: string) {
  messages.value = []
  try {
    const msgs = await getSessionMessages(id)
    messages.value = msgs
    const session = sessions.value.find(s => s.id === id)
    currentSessionTitle.value = session?.title || ''
  } catch (e) {
    console.error('加载会话消息失败:', e)
    messages.value = []
  }
}

function selectSession(id: string) {
  currentSessionId.value = id
}

watch(currentSessionId, (newId) => {
  if (newId) {
    loadSession(newId)
  } else {
    messages.value = []
    currentSessionTitle.value = ''
  }
})

async function handleCreateSession() {
  try {
    const session = await createSession()
    sessions.value.unshift(session)
    currentSessionId.value = session.id
  } catch (e) {
    console.error('创建会话失败:', e)
    ElMessage.error('创建会话失败')
  }
}

function handleRenameSession(id: string) {
  const session = sessions.value.find(s => s.id === id)
  if (session) {
    sessionListRef.value?.openRenameDialog(id, session.title || '')
  }
}

async function updateSessionTitle(id: string, title: string) {
  try {
    await renameSession(id, title)
    const session = sessions.value.find(s => s.id === id)
    if (session) {
      session.title = title
    }
    if (currentSessionId.value === id) {
      currentSessionTitle.value = title
    }
  } catch (e) {
    console.error('重命名会话失败:', e)
  }
}

async function handleDeleteSession(id: string) {
  try {
    await deleteSession(id)
    sessions.value = sessions.value.filter(s => s.id !== id)
    if (currentSessionId.value === id) {
      currentSessionId.value = undefined
      messages.value = []
      currentSessionTitle.value = ''
    }
  } catch (e) {
    console.error('删除会话失败:', e)
  }
}

function onImageChange(file: UploadFile) {
  revokeAttachedPreview()
  attachedImage.value = file.raw || null
  if (file.raw) {
    attachedImagePreview.value = URL.createObjectURL(file.raw)
  }
}

function revokeAttachedPreview() {
  if (attachedImagePreview.value) {
    URL.revokeObjectURL(attachedImagePreview.value)
    attachedImagePreview.value = ''
  }
}

function removeAttached() {
  attachedImage.value = null
  revokeAttachedPreview()
}

function getPresentationMode(msg: Message): string {
  return msg.presentation_mode || msg.retrieval_params?.presentation_mode || 'rag_answer'
}

function getImageSources(msg: Message): SourceItem[] {
  return (msg.sources || []).filter(source => source.source_type === 'image')
}

function isImageFocusedMode(msg: Message): boolean {
  const mode = getPresentationMode(msg)
  return mode === 'image_only' || mode === 'image_plus_answer'
}

function shouldShowImagesFirst(msg: Message): boolean {
  if (msg.role !== 'assistant') {
    return false
  }
  return isImageFocusedMode(msg) && getImageSources(msg).length > 0
}

function shouldShowImagesAfterText(msg: Message): boolean {
  if (msg.role !== 'assistant') {
    return false
  }
  return !isImageFocusedMode(msg) && getImageSources(msg).length > 0
}

function getModeLabel(msg: Message): string {
  switch (getPresentationMode(msg)) {
    case 'direct_answer':
      return '直接回答'
    case 'image_only':
      return '图片结果'
    case 'image_plus_answer':
      return '图文回答'
    case 'rag_answer':
    default:
      return '知识库回答'
  }
}

async function doChat() {
  if (!query.value.trim() && !attachedImage.value) {
    ElMessage.warning(t('chat.enterQuestion'))
    return
  }

  // 如果没有会话，先创建一个
  if (!currentSessionId.value) {
    await handleCreateSession()
    if (!currentSessionId.value) {
      ElMessage.error('会话创建失败')
      return
    }
  }

  const sessionId = currentSessionId.value
  const userMessage: Message = {
    id: Date.now().toString(),
    session_id: sessionId,
    role: 'user',
    content: query.value,
    created_at: new Date().toISOString(),
    has_image: Boolean(attachedImage.value),
    sources: [],
    retrieval_params: null
  }

  messages.value.push(userMessage)
  const userQuery = query.value
  query.value = ''

  await nextTick()
  scrollToBottom()

  try {
    loading.value = true
    const response = await ragChat({
      query: userQuery,
      sessionId,
      topK: 5,
      image: attachedImage.value
    })

    const effectiveSessionId = response.session_id || sessionId
    currentSessionId.value = effectiveSessionId

    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      session_id: effectiveSessionId,
      role: 'assistant',
      content: response.answer,
      created_at: new Date().toISOString(),
      has_image: false,
      sources: response.sources || [],
      presentation_mode: response.presentation_mode,
      execution_mode: response.execution_mode,
      use_rag: response.use_rag,
      retrieval_params: {
        presentation_mode: response.presentation_mode,
        execution_mode: response.execution_mode,
        use_rag: response.use_rag,
      }
    }
    messages.value.push(assistantMessage)

    // 更新会话标题（如果是第一条用户消息）
    const userMsgCount = messages.value.filter(m => m.role === 'user').length
    if (userMsgCount === 1) {
      const title = userQuery.slice(0, 30) + (userQuery.length > 30 ? '...' : '')
      await updateSessionTitle(effectiveSessionId, title)
    }

    await nextTick()
    scrollToBottom()
  } catch (e) {
    console.error('RAG 问答失败:', e)
    ElMessage.error(t('chat.chatFailed'))
  } finally {
    loading.value = false
    streamingId.value = ''
    removeAttached()
  }
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function getSourceImageSrc(source: SourceItem): string {
  if (source.file_path) {
    return imgSrc(source.file_path)
  }
  // 如果没有 file_path，尝试使用 source_id
  if (source.source_id) {
    return imgSrc(`storage/${source.source_id}`)
  }
  return ''
}

function showPreview(source: SourceItem) {
  previewTitle.value = source.title || source.source_id
  previewDescription.value = source.content || ''
  previewSrc.value = getSourceImageSrc(source)
  previewVisible.value = true
}

function formatTime(isoString: string): string {
  const date = new Date(isoString)
  return date.toLocaleTimeString()
}

function onImgError(e: Event) {
  (e.target as HTMLImageElement).style.display = 'none'
}

onMounted(async () => {
  await loadSessions()
  // 如果有会话但当前未选中，自动选中第一个
  if (!currentSessionId.value && sessions.value.length > 0) {
    currentSessionId.value = sessions.value[0].id
  }
})

onBeforeUnmount(() => {
  revokeAttachedPreview()
})
</script>

<style scoped>
.chat-page {
  height: calc(100vh - 100px);
}

.session-panel {
  height: calc(100vh - 140px);
  overflow: hidden;
}

.chat-panel {
  height: calc(100vh - 140px);
  display: flex;
  flex-direction: column;
}

.chat-header {
  display: flex;
  align-items: center;
}

.chat-title {
  font-size: 16px;
  font-weight: 500;
}

/* 消息容器 */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.empty-chat {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 48px;
  color: var(--accent-primary);
  opacity: 0.5;
  margin-bottom: 16px;
}

.empty-chat p {
  margin: 0;
}

.messages-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 消息项 */
.message-item {
  display: flex;
  gap: 12px;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-item.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.message-item.user .message-avatar {
  background: var(--accent-gradient);
  color: #fff;
}

.message-item.assistant .message-avatar {
  background: var(--bg-tertiary);
  color: var(--accent-primary);
}

.message-content {
  max-width: 70%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.message-item.user .message-content {
  align-items: flex-end;
}

.message-bubble {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;
}

.message-item.user .message-bubble {
  background: var(--accent-gradient);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message-item.assistant .message-bubble {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
}

.assistant-meta {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.assistant-mode-badge {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.2px;
  background: rgba(0, 212, 255, 0.12);
  color: var(--accent-primary);
}

.mode-direct_answer .assistant-mode-badge {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
}

.mode-image_only .assistant-mode-badge,
.mode-image_plus_answer .assistant-mode-badge {
  background: rgba(245, 158, 11, 0.14);
  color: #d97706;
}

.message-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.mode-text-image_only {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.mode-text-image_plus_answer {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.mode-text-rag_answer {
  color: var(--text-primary);
}

.mode-text-direct_answer {
  color: var(--text-primary);
}

.referenced-images {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
  gap: 10px;
}

.referenced-images.prominent {
  grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
  gap: 12px;
}

.ref-image-item {
  position: relative;
  overflow: hidden;
  min-height: 96px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.ref-image-item:hover {
  transform: translateY(-2px);
  border-color: var(--accent-primary);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12);
}

.ref-image-item img {
  width: 100%;
  height: 100%;
  min-height: 96px;
  object-fit: cover;
  display: block;
}

.message-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-text.typing::after {
  content: '|';
  animation: typing-cursor 0.8s ease-in-out infinite;
  color: var(--accent-primary);
}

.message-time {
  font-size: 11px;
  color: var(--text-secondary);
}

/* 引用图片 */
.referenced-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.ref-image-item {
  width: 60px;
  height: 60px;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s ease;
}

.ref-image-item:hover {
  border-color: var(--accent-primary);
  transform: scale(1.05);
}

.ref-image-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 输入区域 */
.input-area {
  padding: 16px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.attach-btn {
  color: var(--text-secondary);
}

.attach-btn:hover {
  color: var(--accent-primary);
}

.chat-input {
  flex: 1;
}

.chat-input :deep(.el-input__wrapper) {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
}

.chat-input :deep(.el-input__wrapper:focus-within) {
  border-color: var(--accent-primary);
  box-shadow: 0 0 10px rgba(0, 212, 255, 0.2);
}

.send-btn {
  background: var(--accent-gradient);
  border: none;
}

.send-btn:hover {
  opacity: 0.9;
}

.attached-preview {
  position: relative;
  display: inline-block;
  margin-top: 8px;
}

.attached-preview img {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 8px;
  border: 2px solid var(--accent-primary);
}

.remove-attached {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 20px;
  height: 20px;
  border: none;
  background: #f56c6c;
  color: #fff;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

/* 动画 */
@keyframes typing-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
