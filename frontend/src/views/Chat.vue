<template>
  <div class="chat-page page-shell">
    <div class="chat-shell">
      <el-drawer v-model="historyDrawerOpen" direction="rtl" size="340px" :with-header="false" class="history-drawer">
        <div class="history-drawer-body">
          <div class="history-panel-head drawer-head">
            <div>
              <div class="history-title">{{ t("chat.history") }}</div>
              <div class="history-subtitle">{{ sessions.length }} {{ t("chat.history") }}</div>
            </div>
          </div>
          <SessionList
            ref="sessionListRef"
            :sessions="sessions"
            :active-id="currentSessionId"
            :collapsed="false"
            @select="selectSessionFromDrawer"
            @create="handleCreateSession"
            @rename="handleRenameSession"
            @update-title="updateSessionTitle"
            @delete="handleDeleteSession"
            @toggle-collapse="historyDrawerOpen = false"
          />
        </div>
      </el-drawer>

      <section class="chat-main">
        <el-card class="chat-panel glass-card">
          <template #header>
            <div class="chat-header">
              <div class="chat-header-main">
                <span class="chat-title">{{ currentSessionTitle || t("chat.title") }}</span>
              </div>
              <div class="chat-header-tools">
                <el-button text class="history-trigger-btn" @click="historyDrawerOpen = true">
                  <i class="i-ep-chat-line-square"></i>
                  <span>{{ t("chat.history") }}</span>
                </el-button>
              </div>
            </div>
          </template>

          <div class="messages-container">
            <div v-if="messages.length === 0" class="empty-chat">
              <div class="empty-icon"><i class="i-ep-chat-dot-round"></i></div>
              <h3>{{ t("chat.emptyTitle") }}</h3>
              <p>{{ t("chat.emptySubtitle") }}</p>
              <div class="empty-actions">
                <el-button class="empty-action-btn" @click="router.push('/search')">
                  <i class="i-ep-search mr-1"></i>{{ t("chat.quickSearch") }}
                </el-button>
                <el-button class="empty-action-btn" @click="router.push('/kb')">
                  <i class="i-ep-picture mr-1"></i>{{ t("chat.quickKnowledgeBase") }}
                </el-button>
                <el-button class="empty-action-btn" @click="router.push('/docs')">
                  <i class="i-ep-document mr-1"></i>{{ t("chat.quickDocs") }}
                </el-button>
              </div>
            </div>

            <div v-else class="messages-list">
              <div
                v-for="(msg, index) in messages"
                :key="msg.id"
                class="message-item"
                :class="[msg.role, msg.role === 'assistant' ? `mode-${getPresentationMode(msg)}` : '']"
              >
                <div class="message-avatar">
                  <template v-if="msg.role === 'user'">
                    <span class="avatar-ring"></span>
                    <i class="i-ep-user"></i>
                  </template>
                  <template v-else>
                    <span class="avatar-ring"></span>
                    <span class="assistant-avatar-mark">KB</span>
                  </template>
                </div>
                <div class="message-content">
                  <div class="message-head">
                    <span class="message-author">{{ getMessageAuthor(msg) }}</span>
                    <span v-if="msg.role === 'assistant'" class="message-role-note">{{ t("chat.assistantRoleNote") }}</span>
                  </div>
                  <div class="message-bubble">
                    <div v-if="msg.role === 'assistant'" class="assistant-meta">
                      <span class="assistant-name">{{ t("chat.assistantName") }}</span>
                      <span class="assistant-mode-badge">{{ getModeLabel(msg) }}</span>
                    </div>
                    <div v-if="msg.role === 'user' && (msg.local_image_url || msg.has_image)" class="user-attachment-card">
                      <img v-if="msg.local_image_url" :src="msg.local_image_url" class="user-attachment-image" />
                      <div class="user-attachment-meta">
                        <span class="user-attachment-label">{{ t("chat.attachedImage") }}</span>
                        <span class="user-attachment-hint">{{ t("chat.attachedImageHint") }}</span>
                      </div>
                    </div>
                    <div v-if="shouldShowImagesFirst(msg)" class="referenced-images" :class="{ prominent: isImageFocusedMode(msg) }">
                      <div v-for="source in getImageSources(msg)" :key="source.source_id" class="ref-image-item" @click="showPreview(source)">
                        <div v-if="getSourceAssetLabel(source) || getSourcePageLabel(source) || getSourceScoreLabel(source)" class="ref-image-badges">
                          <span v-if="getSourceAssetLabel(source)" class="ref-image-badge primary">{{ getSourceAssetLabel(source) }}</span>
                          <span v-if="getSourcePageLabel(source)" class="ref-image-badge subtle">{{ getSourcePageLabel(source) }}</span>
                          <span v-if="getSourceScoreLabel(source)" class="ref-image-badge score">{{ getSourceScoreLabel(source) }}</span>
                          <span v-if="isCrossPageSource(source)" class="ref-image-badge warn">{{ t("docs.crossPageContinued") }}</span>
                        </div>
                        <div class="ref-image-overlay">
                          <i class="i-ep-zoom-in"></i>
                          <span>{{ t("chat.previewImage") }}</span>
                        </div>
                        <img :src="getSourceImageSrc(source)" @error="onImgError" />
                      </div>
                    </div>
                    <p
                      v-if="msg.content"
                      class="message-text"
                      :class="[{ typing: msg.role === 'assistant' && String(msg.id) === streamingId }, msg.role === 'assistant' ? `mode-text-${getPresentationMode(msg)}` : '']"
                    >{{ msg.content }}</p>
                    <el-alert
                      v-if="shouldShowRerankFilterNotice(msg)"
                      :title="t('chat.rerankFilterUnsupported')"
                      type="info"
                      :closable="false"
                      show-icon
                      class="message-notice"
                    />
                    <QaProcessCard v-if="shouldShowProcessCard(msg)" :message="msg" />
                    <div v-if="shouldShowImagesAfterText(msg)" class="referenced-images" :class="{ prominent: isImageFocusedMode(msg) }">
                      <div class="sources-heading">{{ t("chat.sourceImages") }}</div>
                      <div v-for="source in getImageSources(msg)" :key="source.source_id" class="ref-image-item" @click="showPreview(source)">
                        <div v-if="getSourceAssetLabel(source) || getSourcePageLabel(source) || getSourceScoreLabel(source)" class="ref-image-badges">
                          <span v-if="getSourceAssetLabel(source)" class="ref-image-badge primary">{{ getSourceAssetLabel(source) }}</span>
                          <span v-if="getSourcePageLabel(source)" class="ref-image-badge subtle">{{ getSourcePageLabel(source) }}</span>
                          <span v-if="getSourceScoreLabel(source)" class="ref-image-badge score">{{ getSourceScoreLabel(source) }}</span>
                          <span v-if="isCrossPageSource(source)" class="ref-image-badge warn">{{ t("docs.crossPageContinued") }}</span>
                        </div>
                        <div class="ref-image-overlay">
                          <i class="i-ep-zoom-in"></i>
                          <span>{{ t("chat.previewImage") }}</span>
                        </div>
                        <img :src="getSourceImageSrc(source)" @error="onImgError" />
                      </div>
                    </div>
                  </div>
                  <div class="message-footer">
                    <div class="message-actions">
                      <button type="button" class="message-action-btn" @click="copyMessage(msg)">
                        <i class="i-ep-document-copy"></i>
                        <span>{{ t("chat.copyMessage") }}</span>
                      </button>
                      <button type="button" class="message-action-btn" @click="quoteMessage(msg)">
                        <i class="i-ep-chat-line-round"></i>
                        <span>{{ t("chat.quoteMessage") }}</span>
                      </button>
                      <button type="button" class="message-action-btn" @click="resendMessage(msg, index)">
                        <i class="i-ep-refresh-right"></i>
                        <span>{{ msg.role === "assistant" ? t("chat.resendQuestion") : t("chat.resendMessage") }}</span>
                      </button>
                    </div>
                    <span class="message-time">{{ formatTime(msg.created_at) }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div ref="messagesEndRef" class="messages-end-anchor"></div>
          </div>

          <div class="input-area">
            <div v-if="isCurrentSessionPending && currentSessionId && sessionDrafts[currentSessionId]" class="pending-banner">
              <i class="i-ep-loading"></i>
              <span>{{ t("chat.pendingSession") }}</span>
            </div>
            <div class="input-row">
              <el-upload :auto-upload="false" :show-file-list="false" :on-change="onImageChange">
                <el-button text class="attach-btn"><i class="i-ep-plus"></i></el-button>
              </el-upload>
              <el-popover v-model:visible="sourcePanelOpen" placement="top-start" width="360" trigger="manual" popper-class="source-popover">
                <template #reference>
                  <el-button text class="attach-btn" @click="openSourcePanel"><i class="i-ep-collection-tag"></i></el-button>
                </template>
                <div class="source-picker">
                  <el-input
                    v-model="sourceQuery"
                    :placeholder="t('chat.sourceSearchPlaceholder')"
                    clearable
                    @input="loadSourceCandidates(sourceQuery)"
                  />
                  <div v-loading="sourceLoading" class="source-list">
                    <div class="source-group-head">
                      <div class="source-group-title">{{ t("chat.sourceDocs") }}</div>
                      <div class="source-group-meta">{{ documentCandidates.length }} / {{ sourceDocLimit }}</div>
                    </div>
                    <button
                      v-for="doc in documentCandidates"
                      :key="doc.id"
                      class="source-option"
                      type="button"
                      @click="addSourceChip('doc', doc.id, doc.title || doc.file_name)"
                    >
                      <i class="i-ep-document"></i>
                      <span>{{ doc.title || doc.file_name }}</span>
                    </button>
                    <button type="button" class="source-more-btn" @click="loadMoreSources('doc')">{{ t("chat.sourceLoadMore") }}</button>
                    <div class="source-group-head">
                      <div class="source-group-title">{{ t("chat.sourceImages") }}</div>
                      <div class="source-group-meta">{{ imageCandidates.length }} / {{ sourceImageLimit }}</div>
                    </div>
                    <button
                      v-for="image in imageCandidates"
                      :key="image.id"
                      class="source-option"
                      type="button"
                      @click="addSourceChip('image', image.id, image.title || image.id)"
                    >
                      <i class="i-ep-picture"></i>
                      <span>{{ image.title || image.id }}</span>
                    </button>
                    <button type="button" class="source-more-btn" @click="loadMoreSources('image')">{{ t("chat.sourceLoadMore") }}</button>
                  </div>
                </div>
              </el-popover>
              <el-input
                ref="composerInputRef"
                v-model="query"
                :placeholder="t('chat.inputPlaceholder')"
                class="chat-input"
                :class="{ 'slash-active': isSlashMode, 'slash-invalid': hasInvalidSlashCommand }"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 5 }"
                resize="none"
                :disabled="isCurrentSessionPending"
                @keydown="handleInputKeydown"
              />
              <el-button type="primary" class="send-btn" :loading="isCurrentSessionPending" @click="doChat">
                <el-icon v-if="!isCurrentSessionPending"><Promotion /></el-icon>
              </el-button>
            </div>
            <div v-if="selectedSources.length > 0 || effectiveExecutionHint || visibleSlashCommands.length > 0 || isSlashMode" class="composer-tools">
              <div class="composer-tools-head">{{ t("chat.composerTools") }}</div>
              <div v-if="selectedSources.length > 0 || effectiveExecutionHint" class="input-context-row">
                <el-tag
                  v-if="effectiveExecutionHint"
                  type="warning"
                  effect="plain"
                  round
                >
                  {{ t("chat.activeMode") }}：{{ effectiveExecutionHint }}
                </el-tag>
                <el-tag
                  v-for="(source, index) in selectedSources"
                  :key="`${source.type}-${source.id}`"
                  closable
                  effect="plain"
                  round
                  @close="removeSourceChip(index)"
                >
                  {{ source.type === "doc" ? t("chat.sourceDoc") : t("chat.sourceImage") }}：{{ source.title }}
                </el-tag>
              </div>
              <div v-if="visibleSlashCommands.length > 0" class="slash-panel">
                <button
                  v-for="command in visibleSlashCommands"
                  :key="command.command"
                  class="slash-option"
                  type="button"
                  @click="applySlashCommand(command)"
                >
                  <span class="slash-command">{{ command.command }}</span>
                  <span class="slash-desc">{{ command.description }}</span>
                </button>
              </div>
              <div v-else-if="isSlashMode" class="slash-status" :class="{ invalid: hasInvalidSlashCommand }">
                <span v-if="activeSlashCommand">{{ t("chat.commandPreview", { command: activeSlashCommand.command }) }} {{ activeSlashCommand.description }}</span>
                <span v-else>{{ t("chat.commandInvalidHint") }}</span>
              </div>
            </div>
            <div class="input-hint">{{ t("chat.inputHint") }}</div>
            <div class="settings-toggle-row">
              <el-button text class="settings-toggle" @click="settingsPanelOpen = !settingsPanelOpen">
                <i :class="settingsPanelOpen ? 'i-ep-arrow-up-bold' : 'i-ep-arrow-down-bold'"></i>
                <span>{{ t("chat.retrievalSettings") }}</span>
                <span class="settings-summary">{{ settingsSummary }}</span>
              </el-button>
            </div>
            <el-collapse-transition>
              <div v-show="settingsPanelOpen" class="settings-panel">
                <div class="settings-grid">
                  <div class="settings-item">
                    <span class="settings-label">{{ t("chat.topK") }}</span>
                    <el-input-number v-model="chatTopK" :min="1" :max="20" />
                  </div>
                  <div class="settings-item switch-item">
                    <span class="settings-label">{{ t("chat.enableScoreFilter") }}</span>
                    <el-switch v-model="chatEnableScoreFilter" />
                  </div>
                  <div class="settings-item">
                    <span class="settings-label">{{ t("chat.minRelevanceScore") }}</span>
                    <el-input-number v-model="chatMinRelevanceScore" :step="0.1" :precision="3" :disabled="!chatEnableScoreFilter" />
                  </div>
                </div>
              </div>
            </el-collapse-transition>
            <div v-if="attachedImage" class="attached-preview">
              <img :src="attachedImagePreview" />
              <div class="attached-copy">
                <span class="attached-title">{{ t("chat.attachedImage") }}</span>
                <span class="attached-desc">{{ attachedImage?.name }}</span>
                <el-select v-model="attachmentMode" size="small" class="attachment-mode-select">
                  <el-option
                    v-for="option in attachmentModeOptions"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>
              </div>
              <button class="remove-attached" @click="removeAttached"><i class="i-ep-close"></i></button>
            </div>
          </div>
        </el-card>
      </section>
    </div>

    <ImagePreviewModal v-model:visible="previewVisible" :src="previewSrc" :title="previewTitle" :description="previewDescription" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { Promotion } from "@element-plus/icons-vue";
import type { InputInstance, UploadFile } from "element-plus";
import { useRouter } from "vue-router";
import { getSessions, createSession, renameSession, deleteSession, getSessionMessages, ragChat, type ChatSession } from "@/api/chat";
import { listDocuments } from "@/api/docs";
import { listImages } from "@/api/kb";
import { getSystemConfig } from "@/api/settings";
import { imgSrc } from "@/utils/image";
import SessionList from "@/components/SessionList.vue";
import ImagePreviewModal from "@/components/ImagePreviewModal.vue";
import QaProcessCard from "@/components/QaProcessCard.vue";
import type { ChatMessage, ChatSourceItem, DocumentRecord, ImageRecord } from "@/types";

const { t } = useI18n();
const router = useRouter();

type SourceItem = ChatSourceItem;
type Message = ChatMessage;
type ExecutionHint =
  | "direct_llm"
  | "multimodal_rag"
  | "image_similarity"
  | "image_grounded_answer"
  | "uploaded_image_qa"
  | "save_uploaded_image";
type SourceScopeChip = {
  type: "doc" | "image";
  id: string;
  title: string;
};
type SlashCommand = {
  command: string;
  label: string;
  description: string;
  apply: () => void;
};

const sessions = ref<ChatSession[]>([]);
const currentSessionId = ref<string | undefined>();
const currentSessionTitle = ref("");
const messages = ref<Message[]>([]);
const query = ref("");
const pendingSessions = ref<Record<string, boolean>>({});
const attachedImage = ref<File | null>(null);
const attachedImagePreview = ref("");
const attachmentMode = ref<"auto" | "uploaded_image_qa" | "image_similarity" | "save_uploaded_image">("auto");
const selectedExecutionHint = ref<ExecutionHint | "auto">("auto");
const selectedSources = ref<SourceScopeChip[]>([]);
const sourceQuery = ref("");
const sourcePanelOpen = ref(false);
const sourceLoading = ref(false);
const sourceDocLimit = ref(8);
const sourceImageLimit = ref(8);
const documentCandidates = ref<DocumentRecord[]>([]);
const imageCandidates = ref<ImageRecord[]>([]);
const streamingId = ref("");
const chatTopK = ref(5);
const chatEnableScoreFilter = ref(false);
const chatMinRelevanceScore = ref(0);
const chatDefaultTopK = ref(5);
const chatDefaultEnableScoreFilter = ref(false);
const chatDefaultMinRelevanceScore = ref(0);
const settingsPanelOpen = ref(false);
const historyDrawerOpen = ref(false);
const isMobile = ref(false);
const sessionListRef = ref<InstanceType<typeof SessionList>>();
const composerInputRef = ref<InputInstance>();
const sessionDrafts = ref<Record<string, { messages: Message[]; title: string }>>({});
const objectUrls = new Set<string>();
const previewVisible = ref(false);
const previewSrc = ref("");
const previewTitle = ref("");
const previewDescription = ref("");
const messagesEndRef = ref<HTMLElement>();
let loadSessionToken = 0;

const hasPendingSessions = computed(() => Object.keys(pendingSessions.value).length > 0);
const isCurrentSessionPending = computed(() => {
  if (!currentSessionId.value) return false;
  return Boolean(pendingSessions.value[currentSessionId.value]);
});

const effectiveExecutionHint = computed<ExecutionHint | undefined>(() => {
  if (attachedImage.value && attachmentMode.value !== "auto") {
    return attachmentMode.value;
  }
  if (selectedExecutionHint.value !== "auto") {
    return selectedExecutionHint.value;
  }
  return undefined;
});

const sourceScope = computed(() => {
  const docIds = selectedSources.value.filter((item) => item.type === "doc").map((item) => item.id);
  const imageIds = selectedSources.value.filter((item) => item.type === "image").map((item) => item.id);
  if (docIds.length === 0 && imageIds.length === 0) {
    return null;
  }
  return {
    doc_ids: docIds,
    image_ids: imageIds,
  };
});

const attachmentModeOptions = computed(() => [
  { label: t("chat.attachmentModeAuto"), value: "auto" },
  { label: t("chat.attachmentModeAskImage"), value: "uploaded_image_qa" },
  { label: t("chat.attachmentModeFindSimilar"), value: "image_similarity" },
  { label: t("chat.attachmentModeSave"), value: "save_uploaded_image" },
]);

const slashCommands = computed<SlashCommand[]>(() => [
  {
    command: "/mode kb",
    label: t("chat.commandModeKb"),
    description: t("chat.commandModeKbDesc"),
    apply: () => {
      selectedExecutionHint.value = "multimodal_rag";
      query.value = "";
    },
  },
  {
    command: "/mode direct",
    label: t("chat.commandModeDirect"),
    description: t("chat.commandModeDirectDesc"),
    apply: () => {
      selectedExecutionHint.value = "direct_llm";
      query.value = "";
    },
  },
  {
    command: "/mode image",
    label: t("chat.commandModeImage"),
    description: t("chat.commandModeImageDesc"),
    apply: () => {
      selectedExecutionHint.value = "image_similarity";
      query.value = "";
    },
  },
  {
    command: "/topk 8",
    label: t("chat.commandTopK"),
    description: t("chat.commandTopKDesc"),
    apply: () => {
      chatTopK.value = 8;
      query.value = "";
    },
  },
  {
    command: "/score 0.45",
    label: t("chat.commandScore"),
    description: t("chat.commandScoreDesc"),
    apply: () => {
      chatEnableScoreFilter.value = true;
      chatMinRelevanceScore.value = 0.45;
      query.value = "";
    },
  },
  {
    command: "/trace on",
    label: t("chat.commandTraceOn"),
    description: t("chat.commandTraceOnDesc"),
    apply: () => {
      settingsPanelOpen.value = true;
      query.value = "";
    },
  },
  {
    command: "/clear_scope",
    label: t("chat.commandClearScope"),
    description: t("chat.commandClearScopeDesc"),
    apply: () => {
      selectedSources.value = [];
      query.value = "";
    },
  },
  {
    command: "/reset",
    label: t("chat.commandReset"),
    description: t("chat.commandResetDesc"),
    apply: () => {
      selectedExecutionHint.value = "auto";
      selectedSources.value = [];
      chatTopK.value = chatDefaultTopK.value;
      chatEnableScoreFilter.value = chatDefaultEnableScoreFilter.value;
      chatMinRelevanceScore.value = chatDefaultMinRelevanceScore.value;
      query.value = "";
    },
  },
]);

type ParsedSlashResult = {
  applied: boolean;
  valid: boolean;
  remainder: string;
  previewCommand: string | null;
};

function parseLeadingSlashCommands(input: string, apply = false): ParsedSlashResult {
  let rest = input.trim();
  let applied = false;
  let previewCommand: string | null = null;

  while (rest.startsWith("/")) {
    if (rest.startsWith("/mode ")) {
      const match = rest.match(/^\/mode\s+(kb|direct|image|auto)(?:\s+|$)/);
      if (!match) return { applied, valid: false, remainder: rest, previewCommand: "/mode" };
      previewCommand = `/mode ${match[1]}`;
      if (apply) {
        selectedExecutionHint.value =
          match[1] === "kb" ? "multimodal_rag" :
          match[1] === "direct" ? "direct_llm" :
          match[1] === "image" ? "image_similarity" :
          "auto";
        ElMessage.success(t("chat.commandApplied", { command: previewCommand }));
      }
      applied = true;
      rest = rest.slice(match[0].length).trim();
      continue;
    }

    if (rest.startsWith("/topk ")) {
      const match = rest.match(/^\/topk\s+(\d+)(?:\s+|$)/);
      if (!match) return { applied, valid: false, remainder: rest, previewCommand: "/topk" };
      previewCommand = `/topk ${match[1]}`;
      if (apply) {
        chatTopK.value = Math.max(1, Math.min(20, Number(match[1])));
        ElMessage.success(t("chat.commandApplied", { command: `/topk ${chatTopK.value}` }));
      }
      applied = true;
      rest = rest.slice(match[0].length).trim();
      continue;
    }

    if (rest.startsWith("/score ")) {
      const match = rest.match(/^\/score\s+([0-9]*\.?[0-9]+)(?:\s+|$)/);
      if (!match) return { applied, valid: false, remainder: rest, previewCommand: "/score" };
      previewCommand = `/score ${match[1]}`;
      if (apply) {
        chatEnableScoreFilter.value = true;
        chatMinRelevanceScore.value = Number(match[1]);
        ElMessage.success(t("chat.commandApplied", { command: `/score ${chatMinRelevanceScore.value}` }));
      }
      applied = true;
      rest = rest.slice(match[0].length).trim();
      continue;
    }

    if (rest === "/clear_scope" || rest.startsWith("/clear_scope ")) {
      previewCommand = "/clear_scope";
      if (apply) {
        selectedSources.value = [];
        ElMessage.success(t("chat.commandApplied", { command: previewCommand }));
      }
      applied = true;
      rest = rest.slice("/clear_scope".length).trim();
      continue;
    }

    if (rest === "/reset" || rest.startsWith("/reset ")) {
      previewCommand = "/reset";
      if (apply) {
        selectedExecutionHint.value = "auto";
        selectedSources.value = [];
        chatTopK.value = chatDefaultTopK.value;
        chatEnableScoreFilter.value = chatDefaultEnableScoreFilter.value;
        chatMinRelevanceScore.value = chatDefaultMinRelevanceScore.value;
        attachmentMode.value = "auto";
        ElMessage.success(t("chat.commandApplied", { command: previewCommand }));
      }
      applied = true;
      rest = rest.slice("/reset".length).trim();
      continue;
    }

    return { applied, valid: false, remainder: rest, previewCommand: previewCommand || rest.split(/\s+/)[0] || null };
  }

  return { applied, valid: true, remainder: rest, previewCommand };
}

const visibleSlashCommands = computed(() => {
  const normalized = query.value.trim().toLowerCase();
  if (!normalized.startsWith("/")) return [];
  const firstToken = normalized.split(/\s+/).slice(0, 2).join(" ");
  return slashCommands.value.filter((item) => item.command.startsWith(firstToken) || item.command.startsWith(normalized) || item.label.toLowerCase().includes(normalized.slice(1)));
});

const isSlashMode = computed(() => query.value.trim().startsWith("/"));
const slashParseResult = computed(() => parseLeadingSlashCommands(query.value, false));
const activeSlashCommand = computed(() => {
  if (visibleSlashCommands.value.length > 0) return visibleSlashCommands.value[0];
  if (slashParseResult.value.previewCommand) {
    return slashCommands.value.find((item) => item.command.startsWith(slashParseResult.value.previewCommand || ""));
  }
  return null;
});
const hasInvalidSlashCommand = computed(() => isSlashMode.value && !slashParseResult.value.valid);

const settingsSummary = computed(() => {
  const parts: string[] = [];
  if (chatTopK.value !== chatDefaultTopK.value) {
    parts.push(t("chat.activeTopK", { count: chatTopK.value }));
  }
  if (chatEnableScoreFilter.value && (chatEnableScoreFilter.value !== chatDefaultEnableScoreFilter.value || chatMinRelevanceScore.value !== chatDefaultMinRelevanceScore.value)) {
    parts.push(`${t("chat.activeRerankFilter")} ≥ ${formatNumeric(chatMinRelevanceScore.value)}`);
  }
  return parts.length > 0 ? parts.join(" / ") : t("chat.defaultSettings");
});

watch([chatTopK, chatEnableScoreFilter, chatMinRelevanceScore], () => {
  settingsPanelOpen.value =
    chatTopK.value !== chatDefaultTopK.value ||
    chatEnableScoreFilter.value !== chatDefaultEnableScoreFilter.value ||
    (chatEnableScoreFilter.value && chatMinRelevanceScore.value !== chatDefaultMinRelevanceScore.value);
});

watch(query, (value, oldValue) => {
  if (value.endsWith("@")) {
    sourceQuery.value = "";
    sourceDocLimit.value = 8;
    sourceImageLimit.value = 8;
    openSourcePanel();
  }
  if (value !== oldValue && isSlashMode.value) {
    sourcePanelOpen.value = false;
  }
});

function updateViewportState() {
  isMobile.value = window.innerWidth < 1100;
}

async function loadSourceCandidates(keyword = "") {
  sourceLoading.value = true;
  try {
    const [docs, images] = await Promise.all([
      listDocuments({ limit: sourceDocLimit.value, keyword: keyword || undefined, enabled: true }),
      listImages({ limit: sourceImageLimit.value, keyword: keyword || undefined, enabled: true }),
    ]);
    documentCandidates.value = docs;
    imageCandidates.value = images;
  } catch (error) {
    console.error("加载引用来源失败:", error);
    ElMessage.error(t("chat.sourceLoadFailed"));
  } finally {
    sourceLoading.value = false;
  }
}

function openSourcePanel() {
  sourcePanelOpen.value = true;
  loadSourceCandidates(sourceQuery.value);
}

function loadMoreSources(type: "doc" | "image") {
  if (type === "doc") {
    sourceDocLimit.value += 8;
  } else {
    sourceImageLimit.value += 8;
  }
  loadSourceCandidates(sourceQuery.value);
}

function addSourceChip(type: "doc" | "image", id: string, title?: string | null) {
  if (selectedSources.value.some((source) => source.type === type && source.id === id)) {
    sourcePanelOpen.value = false;
    return;
  }
  selectedSources.value.push({
    type,
    id,
    title: title || id,
  });
  if (query.value.endsWith("@")) {
    query.value = query.value.slice(0, -1);
  }
  sourcePanelOpen.value = false;
  sourceQuery.value = "";
}

function removeSourceChip(index: number) {
  selectedSources.value.splice(index, 1);
}

function applySlashCommand(command: SlashCommand) {
  command.apply();
  ElMessage.success(t("chat.commandApplied", { command: command.command }));
}

function handleInputKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey && query.value.trim().startsWith("/") && query.value.trim() === "/" && visibleSlashCommands.value.length > 0) {
    event.preventDefault();
    applySlashCommand(visibleSlashCommands.value[0]);
    return;
  }
  if (event.key === "Enter" && !event.shiftKey && query.value.trim().startsWith("/")) {
    event.preventDefault();
    const parsed = parseLeadingSlashCommands(query.value, false);
    if (!parsed.valid) {
      ElMessage.warning(t("chat.commandInvalid"));
      return;
    }
    const applied = parseLeadingSlashCommands(query.value, true);
    query.value = applied.remainder;
    if (!applied.remainder) {
      return;
    }
    doChat();
    return;
  }
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    doChat();
  }
}

function getMessageAuthor(msg: Message): string {
  return msg.role === "assistant" ? t("chat.assistantName") : t("chat.userName");
}

function getCopyableMessageText(msg: Message): string {
  return String(msg.content || "").trim();
}

async function copyMessage(msg: Message) {
  const text = getCopyableMessageText(msg);
  if (!text) {
    ElMessage.warning(t("chat.copyEmpty"));
    return;
  }
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    ElMessage.success(t("chat.copySuccess"));
  } catch (error) {
    console.error("复制消息失败:", error);
    ElMessage.error(t("chat.copyFailed"));
  }
}

function buildQuotedMessage(text: string): string {
  return text
    .split("\n")
    .map((line) => `> ${line}`)
    .join("\n");
}

function focusComposer() {
  nextTick(() => {
    composerInputRef.value?.focus?.();
  });
}

function quoteMessage(msg: Message) {
  const text = getCopyableMessageText(msg);
  if (!text) {
    ElMessage.warning(t("chat.copyEmpty"));
    return;
  }
  const quoted = buildQuotedMessage(text);
  query.value = query.value.trim()
    ? `${query.value.trim()}\n\n${quoted}\n`
    : `${quoted}\n`;
  focusComposer();
  ElMessage.success(t("chat.quoteAdded"));
}

function getRelatedUserMessage(index: number): Message | undefined {
  for (let current = index; current >= 0; current -= 1) {
    const candidate = messages.value[current];
    if (candidate?.role === "user" && String(candidate.content || "").trim()) {
      return candidate;
    }
  }
  return undefined;
}

async function resendMessage(msg: Message, index: number) {
  const sourceMessage = msg.role === "user" ? msg : getRelatedUserMessage(index);
  const text = String(sourceMessage?.content || "").trim();
  if (!text) {
    ElMessage.warning(t("chat.resendUnavailable"));
    return;
  }
  query.value = text;
  focusComposer();
  await nextTick();
  await doChat();
}

async function loadSessions() {
  try {
    sessions.value = await getSessions();
  } catch (e) {
    console.error("加载会话列表失败:", e);
  }
}

async function loadSession(id: string) {
  const token = ++loadSessionToken;
  const draft = sessionDrafts.value[id];
  messages.value = draft?.messages ? draft.messages.map(cloneMessage) : [];
  currentSessionTitle.value = draft?.title || sessions.value.find((s) => s.id === id)?.title || "";
  try {
    const msgs = await getSessionMessages(id);
    if (token !== loadSessionToken || currentSessionId.value !== id) {
      return;
    }
    if (msgs.length > 0 || !draft?.messages?.length) {
      messages.value = msgs.map(cloneMessage);
    }
    const session = sessions.value.find((s) => s.id === id);
    currentSessionTitle.value = session?.title || draft?.title || "";
    if (draft?.messages?.length && msgs.length >= draft.messages.length) {
      clearSessionDraft(id);
    }
  } catch (e) {
    console.error("加载会话消息失败:", e);
    if (!draft?.messages?.length) {
      messages.value = [];
    }
  }
}

function selectSession(id: string) {
  currentSessionId.value = id;
}

function selectSessionFromDrawer(id: string) {
  historyDrawerOpen.value = false;
  selectSession(id);
}

watch(currentSessionId, (newId, oldId) => {
  if (oldId) {
    saveSessionDraft(oldId);
  }
  if (newId) {
    loadSession(newId);
  } else {
    messages.value = [];
    currentSessionTitle.value = "";
  }
});

async function handleCreateSession() {
  try {
    const session = await createSession();
    sessions.value.unshift(session);
    currentSessionTitle.value = session.title || t("chat.newSession");
    currentSessionId.value = session.id;
    historyDrawerOpen.value = false;
  } catch (e) {
    console.error("创建会话失败:", e);
    ElMessage.error("创建会话失败");
  }
}

function handleRenameSession(id: string) {
  const session = sessions.value.find((s) => s.id === id);
  if (session) {
    sessionListRef.value?.openRenameDialog(id, session.title || "");
  }
}

async function updateSessionTitle(id: string, title: string) {
  try {
    await renameSession(id, title);
    const session = sessions.value.find((s) => s.id === id);
    if (session) {
      session.title = title;
    }
    if (sessionDrafts.value[id]) {
      sessionDrafts.value[id].title = title;
    }
    if (currentSessionId.value === id) {
      currentSessionTitle.value = title;
    }
  } catch (e) {
    console.error("重命名会话失败:", e);
  }
}

async function handleDeleteSession(id: string) {
  try {
    await deleteSession(id);
    sessions.value = sessions.value.filter((s) => s.id !== id);
    clearSessionDraft(id);
    if (currentSessionId.value === id) {
      currentSessionId.value = undefined;
      messages.value = [];
      currentSessionTitle.value = "";
    }
  } catch (e) {
    console.error("删除会话失败:", e);
  }
}

function onImageChange(file: UploadFile) {
  revokeAttachedPreview();
  attachedImage.value = file.raw || null;
  if (file.raw) {
    attachedImagePreview.value = URL.createObjectURL(file.raw);
  }
}

function revokeAttachedPreview() {
  if (attachedImagePreview.value) {
    URL.revokeObjectURL(attachedImagePreview.value);
    attachedImagePreview.value = "";
  }
}

function removeAttached() {
  attachedImage.value = null;
  attachmentMode.value = "auto";
  revokeAttachedPreview();
}

function trackObjectUrl(url: string) {
  objectUrls.add(url);
  return url;
}

function cloneMessage(message: Message): Message {
  return {
    ...message,
    sources: message.sources ? [...message.sources] : [],
    retrieval_steps: message.retrieval_steps ? [...message.retrieval_steps] : [],
    retrieval_params: message.retrieval_params ? { ...message.retrieval_params } : null,
    timings: message.timings ? { ...message.timings, stages: [...message.timings.stages] } : null,
  };
}

function revokeMessageUrls(list: Message[]) {
  list.forEach((message) => {
    if (message.local_image_url && objectUrls.has(message.local_image_url)) {
      URL.revokeObjectURL(message.local_image_url);
      objectUrls.delete(message.local_image_url);
    }
  });
}

function saveSessionDraft(sessionId: string) {
  if (!sessionId) return;
  sessionDrafts.value[sessionId] = {
    messages: messages.value.map(cloneMessage),
    title: currentSessionTitle.value || sessions.value.find((session) => session.id === sessionId)?.title || "",
  };
}

function clearSessionDraft(sessionId: string) {
  const draft = sessionDrafts.value[sessionId];
  if (draft?.messages?.length) {
    revokeMessageUrls(draft.messages);
  }
  delete sessionDrafts.value[sessionId];
}

function appendMessageToDraft(sessionId: string, message: Message) {
  if (!sessionId) return;
  const existing = sessionDrafts.value[sessionId];
  const draftMessages = existing?.messages ? existing.messages.map(cloneMessage) : [];
  draftMessages.push(cloneMessage(message));
  sessionDrafts.value[sessionId] = {
    messages: draftMessages,
    title: existing?.title || sessions.value.find((session) => session.id === sessionId)?.title || "",
  };
}

function getSessionDisplayTitle(sessionId: string, fallback?: string) {
  return sessionDrafts.value[sessionId]?.title || fallback || t("chat.newSession");
}

function generateSessionTitle(rawQuery: string): string {
  const normalized = rawQuery.replace(/\s+/g, " ").trim();
  if (!normalized) return t("chat.newSession");
  const sentence = normalized.split(/[。！？!?；;\n]/)[0] || normalized;
  const compact = sentence.replace(/^[,，。！？!?、\s]+/, "").trim();
  if (compact.length <= 18) return compact;
  return `${compact.slice(0, 18)}…`;
}

function getPresentationMode(msg: Message): string {
  return msg.presentation_mode || msg.retrieval_params?.presentation_mode || "rag_answer";
}

function getImageSources(msg: Message): SourceItem[] {
  return (msg.sources || []).filter((source) => source.source_type === "image");
}

function isImageFocusedMode(msg: Message): boolean {
  const mode = getPresentationMode(msg);
  return mode === "image_only" || mode === "image_plus_answer";
}

function shouldShowImagesFirst(msg: Message): boolean {
  return msg.role === "assistant" && isImageFocusedMode(msg) && getImageSources(msg).length > 0;
}

function shouldShowImagesAfterText(msg: Message): boolean {
  return msg.role === "assistant" && !isImageFocusedMode(msg) && getImageSources(msg).length > 0;
}

function getModeLabel(msg: Message): string {
  if (msg.execution_mode === "save_uploaded_image") {
    return "已存入知识库";
  }
  switch (getPresentationMode(msg)) {
    case "direct_answer":
      return "直接回答";
    case "image_only":
      return "图片结果";
    case "image_plus_answer":
      return "图文回答";
    default:
      return "知识库回答";
  }
}

function getSourceAssetLabel(source: SourceItem): string {
  const assetType = String(source.metadata?.asset_type || "").trim();
  if (assetType === "table_crop") return t("docs.tableCrop");
  if (assetType === "table_page_render") return t("docs.tablePageRender");
  if (assetType === "page_render") return t("docs.pageRender");
  return "";
}

function getSourcePageLabel(source: SourceItem): string {
  const pageNumber = source.metadata?.page_number;
  if (typeof pageNumber === "number") {
    return t("docs.pageLabel", { page: pageNumber });
  }
  return "";
}

function isCrossPageSource(source: SourceItem): boolean {
  return Boolean(source.metadata?.continued_from_previous_page || source.metadata?.continued_to_next_page);
}

function formatNumeric(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(3);
}

function getSourceScoreLabel(source: SourceItem): string {
  const relevanceScore = Number(source.relevance_score);
  if (!Number.isNaN(relevanceScore)) {
    return `${String(source.score_source || "rel").toUpperCase()} ${formatNumeric(relevanceScore)}`;
  }
  return "";
}

function shouldShowRerankFilterNotice(msg: Message): boolean {
  if (msg.role !== "assistant" || !msg.retrieval_params?.enable_score_filter) {
    return false;
  }
  const imageSources = getImageSources(msg);
  return imageSources.length > 0 && imageSources.some((source) => source.score_source !== "rerank");
}

function shouldShowProcessCard(msg: Message): boolean {
  if (msg.role !== "assistant") {
    return false;
  }
  return Boolean((msg.retrieval_steps && msg.retrieval_steps.length > 0) || msg.timings || msg.retrieval_params?.timings);
}

async function doChat() {
  if (!query.value.trim() && !attachedImage.value) {
    ElMessage.warning(t("chat.enterQuestion"));
    return;
  }

  if (!currentSessionId.value) {
    await handleCreateSession();
    if (!currentSessionId.value) {
      ElMessage.error("会话创建失败");
      return;
    }
  }

  const sessionId = currentSessionId.value;
  if (pendingSessions.value[sessionId]) {
    ElMessage.warning(t("chat.pendingSession"));
    return;
  }
  const sentImageUrl = attachedImage.value ? trackObjectUrl(URL.createObjectURL(attachedImage.value)) : "";
  const userMessage: Message = {
    id: Date.now().toString(),
    session_id: sessionId,
    role: "user",
    content: query.value,
    created_at: new Date().toISOString(),
    has_image: Boolean(attachedImage.value),
    local_image_url: sentImageUrl || undefined,
    sources: [],
    retrieval_params: null,
  };

  messages.value.push(userMessage);
  currentSessionTitle.value = getSessionDisplayTitle(sessionId, currentSessionTitle.value);
  saveSessionDraft(sessionId);
  const userQuery = query.value;
  query.value = "";

  await nextTick();
  scrollToBottom();

  try {
    pendingSessions.value = {
      ...pendingSessions.value,
      [sessionId]: true,
    };
    const response = await ragChat({
      query: userQuery,
      sessionId,
      topK: chatTopK.value,
      enableScoreFilter: chatEnableScoreFilter.value,
      minRelevanceScore: chatMinRelevanceScore.value,
      executionHint: effectiveExecutionHint.value,
      sourceScope: sourceScope.value,
      image: attachedImage.value,
    });

    const effectiveSessionId = response.session_id || sessionId;
    currentSessionId.value = effectiveSessionId;

    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      session_id: effectiveSessionId,
      role: "assistant",
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
        top_k: chatTopK.value,
        enable_score_filter: chatEnableScoreFilter.value,
        min_relevance_score: chatMinRelevanceScore.value,
        execution_hint: effectiveExecutionHint.value,
        source_scope: sourceScope.value,
        timings: response.timings || null,
      },
      timings: response.timings || null,
    };

    if (currentSessionId.value === effectiveSessionId) {
      messages.value.push(assistantMessage);
      saveSessionDraft(effectiveSessionId);
    } else {
      appendMessageToDraft(effectiveSessionId, assistantMessage);
    }

    const userMsgCount = messages.value.filter((m) => m.role === "user").length;
    if (userMsgCount === 1) {
      const title = generateSessionTitle(userQuery);
      await updateSessionTitle(effectiveSessionId, title);
      currentSessionTitle.value = title;
      saveSessionDraft(effectiveSessionId);
    }

    await nextTick();
    scrollToBottom();
  } catch (e) {
    console.error("RAG 问答失败:", e);
    ElMessage.error(t("chat.chatFailed"));
  } finally {
    const { [sessionId]: _completed, ...restPending } = pendingSessions.value;
    pendingSessions.value = restPending;
    streamingId.value = "";
    removeAttached();
  }
}

function scrollToBottom() {
  messagesEndRef.value?.scrollIntoView({ block: "end" });
}

function getSourceImageSrc(source: SourceItem): string {
  if (source.file_path) return imgSrc(source.file_path);
  if (source.source_id) return imgSrc(`storage/${source.source_id}`);
  return "";
}

function showPreview(source: SourceItem) {
  previewTitle.value = source.title || source.source_id;
  previewDescription.value = source.content || "";
  previewSrc.value = getSourceImageSrc(source);
  previewVisible.value = true;
}

function formatTime(isoString: string): string {
  return new Date(isoString).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function onImgError(e: Event) {
  (e.target as HTMLImageElement).style.display = "none";
}

async function loadChatDefaults() {
  try {
    const payload = await getSystemConfig();
    const itemMap = Object.fromEntries(payload.items.map((item) => [item.key, item.value]));
    chatDefaultTopK.value = Number(itemMap.CHAT_DEFAULT_TOP_K ?? 5);
    chatDefaultEnableScoreFilter.value = Boolean(itemMap.CHAT_ENABLE_SCORE_FILTER ?? false);
    chatDefaultMinRelevanceScore.value = Number(itemMap.CHAT_MIN_RELEVANCE_SCORE ?? 0);
    chatTopK.value = chatDefaultTopK.value;
    chatEnableScoreFilter.value = chatDefaultEnableScoreFilter.value;
    chatMinRelevanceScore.value = chatDefaultMinRelevanceScore.value;
  } catch (error) {
    console.error("加载聊天默认参数失败:", error);
  }
}

onMounted(async () => {
  updateViewportState();
  window.addEventListener("resize", updateViewportState);
  await loadChatDefaults();
  await loadSessions();
  if (!currentSessionId.value && sessions.value.length > 0) {
    currentSessionId.value = sessions.value[0].id;
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updateViewportState);
  saveSessionDraft(currentSessionId.value || "");
  revokeAttachedPreview();
  objectUrls.forEach((url) => URL.revokeObjectURL(url));
  objectUrls.clear();
});
</script>

<style scoped>
.chat-page {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  margin: 0;
  padding: 0;
  min-height: 0;
  height: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow: visible;
}

.page-intro {
  display: none;
}

.page-title {
  font-size: 16px;
  font-weight: 700;
}

.page-subtitle {
  display: none;
}

.chat-shell {
  display: block;
  flex: 0 0 auto;
  min-height: 0;
  height: auto;
  overflow: visible;
}

.chat-panel {
  height: auto;
}

.history-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.history-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.history-subtitle {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.chat-main {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.chat-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: visible;
}

.chat-panel :deep(.el-card__header) {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
}

.chat-panel :deep(.el-card__body) {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  padding: 0;
  min-height: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 24px;
}

.chat-header-main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.chat-title {
  font-size: 14px;
  font-weight: 700;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-header-tools {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.history-trigger-btn {
  gap: 6px;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
}

.history-trigger-btn:hover {
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
}

.messages-container {
  flex: 0 0 auto;
  min-height: 0;
  overflow: visible;
  padding: 10px 14px 18px;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.08), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.8) 0%, rgba(255, 255, 255, 0.45) 100%);
}

.empty-chat {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-start;
  color: var(--text-secondary);
  text-align: left;
  gap: 8px;
  max-width: 520px;
  margin: 0 auto;
  padding-top: clamp(16px, 8vh, 64px);
}

.empty-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 18px;
  font-size: 28px;
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
  border: 1px solid rgba(37, 99, 235, 0.12);
}

.empty-chat h3 {
  margin: 0;
  font-size: 24px;
  color: var(--text-primary);
}

.empty-chat p {
  margin: 0;
  line-height: 1.6;
}

.empty-actions {
  display: flex;
  justify-content: flex-start;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.empty-action-btn {
  min-width: 124px;
  border-radius: 12px;
}

.messages-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.messages-end-anchor {
  width: 100%;
  height: 1px;
}

.message-item {
  display: flex;
  gap: 10px;
  animation: slideUp 0.22s ease;
  align-items: flex-start;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-item.user {
  flex-direction: row-reverse;
}

.message-avatar {
  position: relative;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
  border: 1px solid rgba(255, 255, 255, 0.35);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
  overflow: hidden;
}

.message-item.user .message-avatar {
  background: var(--accent-gradient);
  color: #fff;
  border-color: transparent;
}

.message-item.assistant .message-avatar {
  background: linear-gradient(160deg, #0f172a 0%, #1e3a8a 100%);
  color: #fff;
}

.avatar-ring {
  position: absolute;
  inset: 4px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.18);
}

.assistant-avatar-mark {
  position: relative;
  z-index: 1;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.message-content {
  max-width: min(100%, 1320px);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.message-item.user .message-content {
  align-items: flex-end;
  max-width: min(74%, 980px);
}

.message-item.assistant .message-content {
  max-width: 100%;
}

.message-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 2px;
  min-height: 18px;
}

.message-author {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
}

.message-role-note {
  font-size: 11px;
  color: var(--text-tertiary);
}

.message-bubble {
  padding: 14px 16px;
  border-radius: 18px;
  font-size: 14px;
  line-height: 1.78;
  border: 1px solid var(--border-color);
}

.message-item.user .message-bubble {
  background: #f2f6ff;
  color: var(--text-primary);
  border-color: rgba(37, 99, 235, 0.14);
  border-bottom-right-radius: 6px;
}

.message-item.assistant .message-bubble {
  background: rgba(255, 255, 255, 0.92);
  color: var(--text-primary);
  border-bottom-left-radius: 8px;
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.06);
}

.assistant-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.assistant-name {
  display: none;
}

.assistant-mode-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
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
  overflow-wrap: anywhere;
  letter-spacing: 0.01em;
  font-size: 14px;
}

.message-text.typing::after {
  content: "|";
  animation: typing-cursor 0.8s ease-in-out infinite;
  color: var(--accent-primary);
}

.message-notice {
  margin-top: 12px;
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

.referenced-images {
  margin-top: 14px;
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
  border-radius: 16px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.ref-image-item:hover {
  transform: translateY(-2px);
  border-color: var(--border-strong);
  box-shadow: 0 18px 36px rgba(15, 23, 42, 0.14);
}

.ref-image-item img {
  width: 100%;
  height: 100%;
  min-height: 120px;
  object-fit: cover;
  display: block;
}

.ref-image-overlay {
  position: absolute;
  inset: auto 10px 10px 10px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  width: fit-content;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: rgba(15, 23, 42, 0.7);
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.ref-image-item:hover .ref-image-overlay,
.ref-image-item:focus-within .ref-image-overlay {
  opacity: 1;
  transform: translateY(0);
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

.sources-heading {
  grid-column: 1 / -1;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.input-area {
  padding: 8px 12px 10px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
  box-shadow: 0 -8px 24px rgba(15, 23, 42, 0.04);
}

.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.composer-tools {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 0;
  padding: 8px 10px;
  border-radius: 14px;
  border: 1px solid var(--border-color);
  background: rgba(248, 250, 252, 0.92);
}

.composer-tools-head {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.input-context-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.slash-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.slash-status {
  font-size: 12px;
  color: var(--accent-primary);
}

.slash-status.invalid {
  color: var(--danger-color);
}

.slash-option,
.source-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  border: 1px solid var(--border-color);
  background: rgba(255, 255, 255, 0.78);
  border-radius: 12px;
  padding: 10px 12px;
  text-align: left;
  cursor: pointer;
}

.slash-command {
  font-family: "Consolas", monospace;
  font-size: 12px;
  color: var(--accent-primary);
}

.slash-desc {
  font-size: 12px;
  color: var(--text-secondary);
}

.source-picker {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 260px;
  overflow: auto;
}

.source-group-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-tertiary);
}

.source-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.source-group-meta {
  font-size: 11px;
  color: var(--text-tertiary);
}

.source-more-btn {
  align-self: flex-start;
  border: none;
  background: transparent;
  color: var(--accent-primary);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 0 6px;
}

.attach-btn {
  color: var(--text-secondary);
  width: 40px;
  height: 40px;
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
  padding: 8px 12px;
  border-radius: 14px;
}

.chat-input :deep(.el-input__wrapper:focus-within) {
  border-color: var(--accent-primary);
  box-shadow: var(--shadow-focus);
}

.chat-input.slash-active :deep(.el-input__wrapper) {
  border-color: rgba(37, 99, 235, 0.45);
  background: rgba(37, 99, 235, 0.05);
}

.chat-input.slash-invalid :deep(.el-input__wrapper) {
  border-color: rgba(220, 38, 38, 0.45);
  background: rgba(220, 38, 38, 0.04);
}

.chat-input :deep(textarea.el-textarea__inner) {
  line-height: 1.6;
  color: var(--text-primary);
}

.send-btn {
  min-width: 44px;
  min-height: 44px;
  border-radius: 14px;
  background: var(--accent-gradient);
  border: none;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.2);
}

.send-btn:hover {
  opacity: 0.95;
}

.input-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.settings-toggle-row {
  margin-top: 2px;
}

.settings-toggle {
  width: 100%;
  justify-content: space-between;
  border-radius: 12px;
  padding: 8px 10px;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
}

.settings-toggle:hover {
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
}

.settings-summary {
  margin-left: auto;
  color: var(--text-tertiary);
  font-size: 11px;
  text-align: right;
}

.settings-panel {
  padding: 12px;
  border-radius: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.settings-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.settings-item.switch-item {
  justify-content: space-between;
}

.settings-label {
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

.attachment-mode-select {
  margin-top: 6px;
  width: 180px;
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

.history-drawer-body {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 18px;
  background: var(--bg-secondary);
}

.drawer-head {
  margin-bottom: 18px;
}

.message-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 2px;
  min-height: 22px;
}

.message-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  opacity: 0.18;
  transition: opacity 0.18s ease;
}

.message-item:hover .message-actions,
.message-item:focus-within .message-actions {
  opacity: 1;
}

.message-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition: color 0.18s ease, background-color 0.18s ease, border-color 0.18s ease;
}

.message-action-btn:hover {
  color: var(--accent-primary);
  background: rgba(37, 99, 235, 0.08);
  border-color: rgba(37, 99, 235, 0.08);
}

.message-time {
  font-size: 11px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

@keyframes typing-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

@media (max-width: 1240px) {
  .message-item.assistant .message-content {
    max-width: 100%;
  }
}

@media (max-width: 1100px) {
  .chat-shell {
    display: block;
    height: auto;
    overflow: visible;
  }

  .chat-page {
    height: auto;
    min-height: 0;
    overflow: visible;
  }
}

@media (max-width: 900px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }

  .settings-panel,
  .chat-header-main {
    width: 100%;
  }

  .chat-header {
    align-items: flex-start;
  }

  .chat-header-tools {
    margin-left: auto;
  }

  .message-content,
  .message-item.user .message-content,
  .message-item.assistant .message-content {
    max-width: 100%;
  }

  .message-actions {
    opacity: 1;
  }
}

@media (max-width: 640px) {
  .messages-container {
    padding: 14px 12px 10px;
  }

  .input-area {
    padding: 14px;
  }

  .input-row {
    align-items: stretch;
  }

  .message-item {
    gap: 10px;
  }

  .message-avatar {
    width: 42px;
    height: 42px;
    border-radius: 14px;
  }

  .message-bubble {
    padding: 14px;
  }

  .message-footer {
    flex-direction: column;
    align-items: flex-start;
  }

  .page-subtitle {
    display: none;
  }
}
</style>
