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
                :class="msg.role"
              >
                <div class="message-avatar">
                  <i v-if="msg.role === 'user'" class="i-ep-user"></i>
                  <i v-else class="i-ep-bot"></i>
                </div>
                <div class="message-content">
                  <div class="message-bubble">
                    <p class="message-text" :class="{ 'typing': msg.role === 'assistant' && String(msg.id) === streamingId }">
                      {{ msg.content }}
                    </p>
                    <!-- 引用图片网格 -->
                    <div v-if="msg.role === 'assistant' && msg.sources?.length" class="referenced-images">
                      <div
                        v-for="source in msg.sources.filter(s => s.source_type === 'image')"
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
  type ChatSession
} from '@/api/chat'
import { imgSrc } from '@/utils/image'
import SessionList from '@/components/SessionList.vue'
import ImagePreviewModal from '@/components/ImagePreviewModal.vue'

const { t } = useI18n()

// 来源项类型（对应后端 ChatSourceItem）
interface SourceItem {
  source_type: string
  source_id: string
  title?: string
  file_path?: string
  content?: string
  score?: number
}

// 消息类型（用于本地渲染）
interface Message {
  id: number | string
  session_id: string
  role: string
  content: string
  has_image?: boolean
  sources?: SourceItem[]
  retrieval_params?: Record<string, any> | null
  created_at: string
}

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
    const formData = new FormData()
    formData.append('query', userQuery)
    formData.append('session_id', sessionId)
    formData.append('top_k', '5')
    if (attachedImage.value) {
      formData.append('image', attachedImage.value)
    }

    // 调用流式接口
    const response = await fetch('/api/rag/chat/stream', {
      method: 'POST',
      body: formData
    })

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }

    // 创建助手消息
    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      session_id: sessionId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      has_image: false,
      sources: [],
      retrieval_params: null
    }
    messages.value.push(assistantMessage)
    streamingId.value = String(assistantMessage.id)

    // 处理 SSE 流
    const reader = response.body?.getReader()
    const decoder = new TextDecoder()

    if (reader) {
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (data === '[DONE]') {
              continue
            }
            try {
              const parsed = JSON.parse(data)

              if (parsed.type === 'session' && parsed.session_id) {
                currentSessionId.value = parsed.session_id
                assistantMessage.session_id = parsed.session_id
              } else if (parsed.type === 'content' && parsed.content) {
                assistantMessage.content += parsed.content
              } else if (parsed.type === 'results') {
                const items = Array.isArray(parsed.sources) ? parsed.sources : parsed.results
                const sources: SourceItem[] = []
                items?.forEach((item: any) => {
                  if (item?.source_id || item?.id) {
                    sources.push({
                      source_type: item.source_type || 'image',
                      source_id: item.source_id || item.id,
                      title: item.title,
                      file_path: item.file_path,
                      content: item.content,
                      score: item.score
                    })
                  }
                })
                assistantMessage.sources = sources
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }

        await nextTick()
        scrollToBottom()
      }
    }

    streamingId.value = ''

    // 更新会话标题（如果是第一条用户消息）
    const userMsgCount = messages.value.filter(m => m.role === 'user').length
    if (userMsgCount === 1) {
      const title = userQuery.slice(0, 30) + (userQuery.length > 30 ? '...' : '')
      await updateSessionTitle(sessionId, title)
    }
  } catch (e) {
    console.error('RAG 问答失败:', e)
    ElMessage.error(t('chat.chatFailed'))
  } finally {
    loading.value = false
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
