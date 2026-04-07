<template>
  <div class="chat-page page-shell">
    <div class="page-intro">
      <div class="page-intro-main">
        <h1 class="page-title">{{ t("chat.title") }}</h1>
        <p class="page-subtitle">{{ t("chat.emptySubtitle") }}</p>
      </div>
      <div class="status-inline">
        <span class="status-dot" :class="loading ? 'warning' : 'success'"></span>
        <span>{{ loading ? t("chat.thinking") : t("app.connectionOk") }}</span>
      </div>
    </div>
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
              <h3>{{ t("chat.emptyTitle") }}</h3>
              <p>{{ t("chat.emptySubtitle") }}</p>
              <div class="empty-actions">
                <el-button type="primary" class="empty-action-btn" @click="router.push('/search')">
                  <i class="i-ep-search mr-1"></i>
                  {{ t("chat.quickSearch") }}
                </el-button>
                <el-button class="empty-action-btn" @click="router.push('/kb')">
                  <i class="i-ep-picture mr-1"></i>
                  {{ t("chat.quickKnowledgeBase") }}
                </el-button>
                <el-button class="empty-action-btn" @click="router.push('/docs')">
                  <i class="i-ep-document mr-1"></i>
                  {{ t("chat.quickDocs") }}
                </el-button>
              </div>
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
                      v-if="msg.role === 'user' && (msg.local_image_url || msg.has_image)"
                      class="user-attachment-card"
                    >
                      <img v-if="msg.local_image_url" :src="msg.local_image_url" class="user-attachment-image" />
                      <div class="user-attachment-meta">
                        <span class="user-attachment-label">{{ t("chat.attachedImage") }}</span>
                        <span class="user-attachment-hint">{{ t("chat.attachedImageHint") }}</span>
                      </div>
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
                        <div v-if="getSourceAssetLabel(source) || getSourcePageLabel(source) || getSourceScoreLabel(source)" class="ref-image-badges">
                          <span v-if="getSourceAssetLabel(source)" class="ref-image-badge primary">
                            {{ getSourceAssetLabel(source) }}
                          </span>
                          <span v-if="getSourcePageLabel(source)" class="ref-image-badge subtle">
                            {{ getSourcePageLabel(source) }}
                          </span>
                          <span v-if="getSourceScoreLabel(source)" class="ref-image-badge score">
                            {{ getSourceScoreLabel(source) }}
                          </span>
                          <span v-if="isCrossPageSource(source)" class="ref-image-badge warn">
                            {{ t("docs.crossPageContinued") }}
                          </span>
                        </div>
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
                    <details v-if="hasRetrievalSteps(msg)" class="trace-panel">
                      <summary class="trace-summary">
                        {{ t('chat.ragTrace') }}
                      </summary>
                      <div class="trace-list">
                        <div
                          v-for="step in msg.retrieval_steps"
                          :key="`${msg.id}-${step.key}`"
                          class="trace-step"
                        >
                          <div class="trace-step-header">
                            <span class="trace-step-label">{{ step.label }}</span>
                            <span v-if="step.summary" class="trace-step-summary">{{ step.summary }}</span>
                          </div>
                          <div
                            v-if="step.details && Object.keys(step.details).length > 0"
                            class="trace-step-details"
                          >
                            <div
                              v-for="(value, key) in step.details"
                              :key="`${msg.id}-${step.key}-${String(key)}`"
                              class="trace-detail-row"
                            >
                              <span class="trace-detail-key">{{ key }}</span>
                              <span class="trace-detail-value">{{ formatTraceDetailValue(value) }}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </details>
                    <div
                      v-if="shouldShowImagesAfterText(msg)"
                      class="referenced-images"
                      :class="{ prominent: isImageFocusedMode(msg) }"
                    >
                      <div class="sources-heading">{{ t("chat.sourceImages") }}</div>
                      <div
                        v-for="source in getImageSources(msg)"
                        :key="source.source_id"
                        class="ref-image-item"
                        @click="showPreview(source)"
                      >
                        <div v-if="getSourceAssetLabel(source) || getSourcePageLabel(source) || getSourceScoreLabel(source)" class="ref-image-badges">
                          <span v-if="getSourceAssetLabel(source)" class="ref-image-badge primary">
                            {{ getSourceAssetLabel(source) }}
                          </span>
                          <span v-if="getSourcePageLabel(source)" class="ref-image-badge subtle">
                            {{ getSourcePageLabel(source) }}
                          </span>
                          <span v-if="getSourceScoreLabel(source)" class="ref-image-badge score">
                            {{ getSourceScoreLabel(source) }}
                          </span>
                          <span v-if="isCrossPageSource(source)" class="ref-image-badge warn">
                            {{ t("docs.crossPageContinued") }}
                          </span>
                        </div>
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
            <div v-if="loading && currentSessionId && sessionDrafts[currentSessionId]" class="pending-banner">
              <i class="i-ep-loading"></i>
              <span>{{ t("chat.pendingSession") }}</span>
            </div>
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
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 5 }"
                resize="none"
                @keydown.enter.exact.prevent="doChat"
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
            <div class="input-hint">{{ t("chat.inputHint") }}</div>
            <div v-if="attachedImage" class="attached-preview">
              <img :src="attachedImagePreview" />
              <div class="attached-copy">
                <span class="attached-title">{{ t("chat.attachedImage") }}</span>
                <span class="attached-desc">{{ attachedImage?.name }}</span>
              </div>
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
import { useRouter } from 'vue-router'
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
const router = useRouter()

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
const sessionDrafts = ref<Record<string, { messages: Message[]; title: string }>>({})
const objectUrls = new Set<string>()
let loadSessionToken = 0

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
  const token = ++loadSessionToken
  const draft = sessionDrafts.value[id]
  messages.value = draft?.messages ? draft.messages.map(cloneMessage) : []
  currentSessionTitle.value = draft?.title || sessions.value.find(s => s.id === id)?.title || ''
  try {
    const msgs = await getSessionMessages(id)
    if (token !== loadSessionToken || currentSessionId.value !== id) {
      return
    }
    if (msgs.length > 0 || !draft?.messages?.length) {
      messages.value = msgs.map(cloneMessage)
    }
    const session = sessions.value.find(s => s.id === id)
    currentSessionTitle.value = session?.title || draft?.title || ''
    if (draft?.messages?.length && msgs.length >= draft.messages.length) {
      clearSessionDraft(id)
    }
  } catch (e) {
    console.error('加载会话消息失败:', e)
    if (!draft?.messages?.length) {
      messages.value = []
    }
  }
}

function selectSession(id: string) {
  currentSessionId.value = id
}

watch(currentSessionId, (newId, oldId) => {
  if (oldId) {
    saveSessionDraft(oldId)
  }
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
    currentSessionTitle.value = session.title || t('chat.newSession')
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
    if (sessionDrafts.value[id]) {
      sessionDrafts.value[id].title = title
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
    clearSessionDraft(id)
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

function trackObjectUrl(url: string) {
  objectUrls.add(url)
  return url
}

function cloneMessage(message: Message): Message {
  return {
    ...message,
    sources: message.sources ? [...message.sources] : [],
    retrieval_steps: message.retrieval_steps ? [...message.retrieval_steps] : [],
  }
}

function revokeMessageUrls(list: Message[]) {
  list.forEach((message) => {
    if (message.local_image_url && objectUrls.has(message.local_image_url)) {
      URL.revokeObjectURL(message.local_image_url)
      objectUrls.delete(message.local_image_url)
    }
  })
}

function saveSessionDraft(sessionId: string) {
  if (!sessionId) return
  sessionDrafts.value[sessionId] = {
    messages: messages.value.map(cloneMessage),
    title: currentSessionTitle.value || sessions.value.find(session => session.id === sessionId)?.title || '',
  }
}

function clearSessionDraft(sessionId: string) {
  const draft = sessionDrafts.value[sessionId]
  if (draft?.messages?.length) {
    revokeMessageUrls(draft.messages)
  }
  delete sessionDrafts.value[sessionId]
}

function appendMessageToDraft(sessionId: string, message: Message) {
  if (!sessionId) return
  const existing = sessionDrafts.value[sessionId]
  const draftMessages = existing?.messages ? existing.messages.map(cloneMessage) : []
  draftMessages.push(cloneMessage(message))
  sessionDrafts.value[sessionId] = {
    messages: draftMessages,
    title: existing?.title || sessions.value.find(session => session.id === sessionId)?.title || '',
  }
}

function getSessionDisplayTitle(sessionId: string, fallback?: string) {
  return sessionDrafts.value[sessionId]?.title || fallback || t('chat.newSession')
}

function generateSessionTitle(rawQuery: string): string {
  const normalized = rawQuery.replace(/\s+/g, ' ').trim()
  if (!normalized) return t('chat.newSession')
  const sentence = normalized.split(/[。！？!?；;\n]/)[0] || normalized
  const compact = sentence.replace(/^[,，。！？!?、\s]+/, '').trim()
  if (compact.length <= 18) return compact
  return `${compact.slice(0, 18)}…`
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
  if (msg.execution_mode === 'save_uploaded_image') {
    return '已存入知识库'
  }
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

function getSourceAssetLabel(source: SourceItem): string {
  const assetType = String(source.metadata?.asset_type || '').trim()
  if (assetType === 'table_crop') return t('docs.tableCrop')
  if (assetType === 'table_page_render') return t('docs.tablePageRender')
  if (assetType === 'page_render') return t('docs.pageRender')
  return ''
}

function getSourcePageLabel(source: SourceItem): string {
  const pageNumber = source.metadata?.page_number
  if (typeof pageNumber === 'number') {
    return t('docs.pageLabel', { page: pageNumber })
  }
  return ''
}

function isCrossPageSource(source: SourceItem): boolean {
  return Boolean(
    source.metadata?.continued_from_previous_page ||
    source.metadata?.continued_to_next_page
  )
}

function getSourceScoreLabel(source: SourceItem): string {
  const rerankScore = Number(source.rerank_score)
  if (!Number.isNaN(rerankScore)) {
    return `R ${rerankScore.toFixed(3)}`
  }
  return ''
}

function hasRetrievalSteps(msg: Message): boolean {
  return Array.isArray(msg.retrieval_steps) && msg.retrieval_steps.length > 0
}

function formatTraceDetailValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.join(', ')
  }
  if (value === null || value === undefined) {
    return '-'
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch (_err) {
      return String(value)
    }
  }
  return String(value)
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
  const sentImageUrl = attachedImage.value ? trackObjectUrl(URL.createObjectURL(attachedImage.value)) : ''
  const userMessage: Message = {
    id: Date.now().toString(),
    session_id: sessionId,
    role: 'user',
    content: query.value,
    created_at: new Date().toISOString(),
    has_image: Boolean(attachedImage.value),
    local_image_url: sentImageUrl || undefined,
    sources: [],
    retrieval_params: null
  }

  messages.value.push(userMessage)
  currentSessionTitle.value = getSessionDisplayTitle(sessionId, currentSessionTitle.value)
  saveSessionDraft(sessionId)
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
      retrieval_steps: response.retrieval_steps || [],
      retrieval_params: {
        presentation_mode: response.presentation_mode,
        execution_mode: response.execution_mode,
        use_rag: response.use_rag,
      }
    }
    if (currentSessionId.value === effectiveSessionId) {
      messages.value.push(assistantMessage)
      saveSessionDraft(effectiveSessionId)
    } else {
      appendMessageToDraft(effectiveSessionId, assistantMessage)
    }

    // 更新会话标题（如果是第一条用户消息）
    const userMsgCount = messages.value.filter(m => m.role === 'user').length
    if (userMsgCount === 1) {
      const title = generateSessionTitle(userQuery)
      await updateSessionTitle(effectiveSessionId, title)
      currentSessionTitle.value = title
      saveSessionDraft(effectiveSessionId)
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
  saveSessionDraft(currentSessionId.value || '')
  revokeAttachedPreview()
  objectUrls.forEach((url) => URL.revokeObjectURL(url))
  objectUrls.clear()
})
</script>

<style scoped>
.chat-page {
  min-height: calc(100vh - 120px);
}

.session-panel {
  height: calc(100vh - 182px);
  overflow: hidden;
}

.chat-panel {
  height: calc(100vh - 182px);
  display: flex;
  flex-direction: column;
}

.chat-header {
  display: flex;
  align-items: center;
  min-height: 30px;
}

.chat-title {
  font-size: 18px;
  font-weight: 700;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.72) 0%, rgba(255, 255, 255, 0.4) 100%);
}

.chat-panel :deep(.el-card__header) {
  padding: 18px 22px;
  border-bottom: 1px solid var(--border-color);
}

.chat-panel :deep(.el-card__body) {
  display: flex;
  flex: 1;
  flex-direction: column;
  padding: 0;
}

.empty-chat {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  text-align: center;
  gap: 10px;
  max-width: 420px;
  margin: 0 auto;
}

.empty-icon {
  width: 72px;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 22px;
  font-size: 34px;
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
  border: 1px solid rgba(37, 99, 235, 0.12);
}

.empty-chat h3 {
  margin: 0;
  font-size: 22px;
  color: var(--text-primary);
}

.empty-chat p {
  margin: 0;
  line-height: 1.6;
}

.empty-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 20px;
  flex-wrap: wrap;
}

.empty-action-btn {
  min-width: 140px;
  border-radius: 12px;
}

.messages-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.message-item {
  display: flex;
  gap: 14px;
  animation: slideUp 0.22s ease;
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
  width: 40px;
  height: 40px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
  border: 1px solid var(--border-color);
}

.message-item.user .message-avatar {
  background: var(--accent-gradient);
  color: #fff;
  border-color: transparent;
}

.message-item.assistant .message-avatar {
  background: var(--bg-secondary);
  color: var(--accent-primary);
}

.message-content {
  max-width: min(74%, 760px);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-item.user .message-content {
  align-items: flex-end;
}

.message-bubble {
  padding: 14px 16px;
  border-radius: 18px;
  font-size: 14px;
  line-height: 1.65;
  border: 1px solid var(--border-color);
}

.message-item.user .message-bubble {
  background: #f2f6ff;
  color: var(--text-primary);
  border-color: rgba(37, 99, 235, 0.14);
  border-bottom-right-radius: 6px;
}

.message-item.assistant .message-bubble {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-bottom-left-radius: 6px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.assistant-meta {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.assistant-mode-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.2px;
  background: var(--bg-accent-soft);
  color: var(--accent-primary);
}

.mode-direct_answer .assistant-mode-badge {
  background: rgba(21, 128, 61, 0.12);
  color: var(--success-color);
}

.mode-image_only .assistant-mode-badge,
.mode-image_plus_answer .assistant-mode-badge {
  background: rgba(180, 83, 9, 0.12);
  color: var(--warning-color);
}

.message-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.user-attachment-card {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid rgba(37, 99, 235, 0.1);
}

.user-attachment-image {
  width: 72px;
  height: 72px;
  border-radius: 12px;
  object-fit: cover;
  border: 1px solid rgba(37, 99, 235, 0.12);
}

.user-attachment-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-attachment-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.user-attachment-hint {
  font-size: 12px;
  color: var(--text-secondary);
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
  min-height: 120px;
  border-radius: 14px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.ref-image-item:hover {
  transform: translateY(-2px);
  border-color: var(--border-strong);
  box-shadow: var(--shadow-sm);
}

.ref-image-item img {
  width: 100%;
  height: 100%;
  min-height: 120px;
  object-fit: cover;
  display: block;
}

.ref-image-badges {
  position: absolute;
  top: 6px;
  left: 6px;
  right: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  z-index: 2;
}

.ref-image-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 10px;
  line-height: 1.2;
  color: #fff;
  backdrop-filter: blur(4px);
  background: rgba(15, 23, 42, 0.7);
}

.ref-image-badge.primary {
  background: rgba(0, 112, 243, 0.82);
}

.ref-image-badge.subtle {
  background: rgba(15, 23, 42, 0.68);
}

.ref-image-badge.warn {
  background: rgba(217, 119, 6, 0.82);
}

.ref-image-badge.score {
  background: rgba(16, 185, 129, 0.82);
}

.trace-panel {
  margin-top: 12px;
  border: 1px solid var(--border-color);
  border-radius: 14px;
  background: var(--bg-tertiary);
}

.trace-summary {
  cursor: pointer;
  padding: 12px 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  list-style: none;
}

.trace-summary::-webkit-details-marker {
  display: none;
}

.trace-list {
  padding: 0 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.trace-step {
  padding: 10px;
  border-radius: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
}

.trace-step-header {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
}

.trace-step-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
}

.trace-step-summary {
  font-size: 12px;
  color: var(--text-secondary);
}

.trace-step-details {
  margin-top: 8px;
  display: grid;
  gap: 6px;
}

.trace-detail-row {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 8px;
  font-size: 12px;
}

.trace-detail-key {
  color: var(--text-secondary);
}

.trace-detail-value {
  color: var(--text-primary);
  word-break: break-word;
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
  color: var(--text-tertiary);
}

.sources-heading {
  grid-column: 1 / -1;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.input-area {
  padding: 18px 22px 20px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.attach-btn {
  color: var(--text-secondary);
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
}

.attach-btn:hover {
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
}

.chat-input {
  flex: 1;
}

.chat-input :deep(.el-input__wrapper) {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  box-shadow: none;
  padding: 10px 14px;
  border-radius: 16px;
}

.chat-input :deep(.el-input__wrapper:focus-within) {
  border-color: var(--accent-primary);
  box-shadow: var(--shadow-focus);
}

.chat-input :deep(textarea.el-textarea__inner) {
  line-height: 1.6;
  color: var(--text-primary);
}

.send-btn {
  min-width: 48px;
  min-height: 48px;
  border-radius: 16px;
  background: var(--accent-gradient);
  border: none;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.2);
}

.send-btn:hover {
  opacity: 0.95;
}

.input-hint {
  padding-left: 54px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.pending-banner {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(180, 83, 9, 0.08);
  color: var(--warning-color);
  font-size: 12px;
  font-weight: 500;
}

.attached-preview {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
  padding: 10px;
  border-radius: 14px;
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
}

.attached-preview img {
  width: 76px;
  height: 76px;
  object-fit: cover;
  border-radius: 12px;
  border: 1px solid rgba(37, 99, 235, 0.12);
}

.attached-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding-right: 28px;
}

.attached-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.attached-desc {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-attached {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 24px;
  height: 24px;
  border: 1px solid rgba(220, 38, 38, 0.14);
  background: rgba(220, 38, 38, 0.1);
  color: var(--danger-color);
  border-radius: 999px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

@keyframes typing-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

@media (max-width: 1200px) {
  .message-content {
    max-width: 82%;
  }
}
</style>
