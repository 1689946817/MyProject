<!-- 聊天页面组件：RAG 智能问答，支持多会话管理、流式响应、检索源可视化 -->
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
                    <div
                      v-if="hasUserAttachment(msg)"
                      class="user-attachment-card"
                      :class="{ 'has-preview': Boolean(getUserAttachmentPreviewSrc(msg)) }"
                    >
                      <button
                        v-if="getUserAttachmentPreviewSrc(msg)"
                        type="button"
                        class="user-attachment-preview"
                        @click="showUserAttachmentPreview(msg)"
                      >
                        <img
                          :src="getUserAttachmentPreviewSrc(msg)"
                          :alt="getUserAttachmentName(msg) || t('chat.attachedImage')"
                          class="user-attachment-image"
                          @error="onImgError"
                        />
                      </button>
                      <div class="user-attachment-meta">
                        <span class="user-attachment-label">{{ t("chat.attachedImage") }}</span>
                        <span class="user-attachment-hint">{{ getUserAttachmentName(msg) || t("chat.attachedImageHint") }}</span>
                      </div>
                    </div>
                    <div v-if="shouldShowSourcesFirst(msg)" class="source-card-list" :class="{ prominent: isImageFocusedMode(msg), collapsed: !isSourcePanelExpanded(msg) }">
                      <button type="button" class="sources-heading sources-heading-button" @click="toggleSourcePanel(msg)">
                        <span>{{ t("chat.sourceReferences") }}</span>
                        <span class="sources-heading-meta">{{ getVisibleSources(msg).length }}</span>
                        <span class="sources-heading-toggle">{{ isSourcePanelExpanded(msg) ? t("chat.processCollapse") : t("chat.processExpand") }}</span>
                      </button>
                      <template v-if="isSourcePanelExpanded(msg)">
                        <div
                          v-for="source in getVisibleSources(msg)"
                          :key="source.source_id"
                          :ref="(el) => setSourceCardRef(String(msg.id), source.source_id, el)"
                          class="source-card"
                          :class="{ active: isSourceHighlighted(msg, source), clickable: getSourceCitationCount(msg, source) > 0 }"
                          @click="toggleSourceHighlight(msg, source)"
                        >
                          <div class="source-card-main">
                            <div v-if="isImageSource(source)" class="source-card-visual" @click.stop="showPreview(source)">
                              <img :src="getSourceImageSrc(source)" @error="onImgError" />
                            </div>
                            <div class="source-card-copy">
                              <div class="source-card-head">
                                <span class="source-card-title">{{ getSourceDisplayTitle(source) }}</span>
                                <div class="source-card-head-badges">
                                  <span v-if="getSourceCitationCount(msg, source) > 0" class="source-card-refcount">{{ getSourceCitationCount(msg, source) }}</span>
                                  <span v-if="getSourceAssetLabel(source)" class="source-card-badge">{{ getSourceAssetLabel(source) }}</span>
                                </div>
                              </div>
                              <div class="source-card-meta">
                                <span v-if="getSourcePageLabel(source)">{{ getSourcePageLabel(source) }}</span>
                                <span v-if="getSourceChunkLabel(source)">{{ getSourceChunkLabel(source) }}</span>
                                <span v-if="getSourceScoreLabel(source)">{{ getSourceScoreLabel(source) }}</span>
                              </div>
                              <p v-if="getSourceSummary(source)" class="source-card-summary">{{ getSourceSummary(source) }}</p>
                            </div>
                          </div>
                          <div class="source-card-actions-row">
                            <button
                              v-if="isImageSource(source)"
                              type="button"
                              class="message-action-btn compact"
                              @click.stop="showPreview(source)"
                            >
                              <i class="i-ep-zoom-in"></i>
                              <span>{{ t("chat.previewImage") }}</span>
                            </button>
                            <button
                              v-if="canOpenSourceDocument(source)"
                              type="button"
                              class="message-action-btn compact"
                              @click.stop="openSourceDocument(source)"
                            >
                              <i class="i-ep-document"></i>
                              <span>{{ t("chat.openSourceDoc") }}</span>
                            </button>
                          </div>
                        </div>
                      </template>
                    </div>
                    <div v-if="shouldShowLiveProcessText(msg)" class="live-process-wrap">
                      <button
                        type="button"
                        class="live-process-text"
                        :class="{ expanded: isLiveProcessDetailsOpen(msg) }"
                        @click="toggleLiveProcessDetails(msg)"
                      >
                        <span class="live-process-dot" aria-hidden="true"></span>
                        <span class="live-process-text-main">{{ getLiveProcessText(msg) }}</span>
                        <span class="live-process-ellipsis" aria-hidden="true"><span></span><span></span><span></span></span>
                        <span v-if="getLiveProcessSubtext(msg)" class="live-process-text-sub">{{ getLiveProcessSubtext(msg) }}</span>
                        <span class="live-process-toggle">{{ isLiveProcessDetailsOpen(msg) ? t("chat.processCollapse") : t("chat.processExpand") }}</span>
                      </button>
                      <div v-if="shouldShowLiveProcessDetails(msg)" class="live-process-details">
                        <div class="live-process-section">
                          <div class="live-process-section-title">{{ t("chat.processCurrentStep") }}</div>
                          <div class="live-process-current-line">
                            <span class="live-process-current-name">{{ getLiveProcessCurrentStepLabel(msg) }}</span>
                            <span class="live-process-current-status">{{ getLiveProcessCurrentStepStatus(msg) }}</span>
                          </div>
                          <div v-if="getLiveProcessCurrentStepSummary(msg)" class="live-process-current-summary">
                            {{ getLiveProcessCurrentStepSummary(msg) }}
                          </div>
                          <div v-if="getLiveProcessCurrentStepDetailItems(msg).length > 0" class="live-process-meta-list">
                            <div v-for="item in getLiveProcessCurrentStepDetailItems(msg)" :key="item.key" class="live-process-meta-item">
                              <span class="live-process-meta-label">{{ item.label }}</span>
                              <span class="live-process-meta-value">{{ item.value }}</span>
                            </div>
                          </div>
                        </div>
                        <div class="live-process-section">
                          <div class="live-process-section-title">{{ t("chat.processCompletedSteps") }}</div>
                          <div v-if="getLiveProcessCompletedSteps(msg).length > 0" class="live-process-completed-list">
                            <div v-for="step in getLiveProcessCompletedSteps(msg)" :key="step.key" class="live-process-completed-item">
                              <span class="live-process-completed-name">{{ step.label }}</span>
                              <span class="live-process-completed-summary">{{ step.summary }}</span>
                              <span v-if="step.elapsed" class="live-process-completed-time">{{ step.elapsed }}</span>
                            </div>
                          </div>
                          <div v-else class="live-process-empty">{{ t("chat.processCompletedStepsEmpty") }}</div>
                        </div>
                      </div>
                    </div>
                    <QaProcessCard v-if="shouldShowProcessCard(msg)" :message="msg" />
                    <ChatMarkdown
                      v-if="msg.role === 'assistant' && msg.content"
                      class="assistant-markdown"
                      :content="msg.content"
                      :citations="getMessageCitations(msg)"
                      :active-paragraph-keys="getActiveParagraphKeys(msg)"
                      :active-source-ids="getActiveSourceIds(msg)"
                      :source-labels="getSourceLabelMap(msg)"
                      :streaming="String(msg.id) === streamingId"
                      @paragraph-select="handleParagraphSelect(msg, $event)"
                      @citation-open-doc="openCitationDocRef"
                    />
                    <p
                      v-else-if="msg.content"
                      class="message-text"
                    >{{ msg.content }}</p>
                    <el-alert
                      v-if="shouldShowRerankFilterNotice(msg)"
                      :title="t('chat.rerankFilterUnsupported')"
                      type="info"
                      :closable="false"
                      show-icon
                      class="message-notice"
                    />
                    <div v-if="shouldShowSourcesAfterText(msg)" class="source-card-list" :class="{ prominent: isImageFocusedMode(msg), collapsed: !isSourcePanelExpanded(msg) }">
                      <button type="button" class="sources-heading sources-heading-button" @click="toggleSourcePanel(msg)">
                        <span>{{ t("chat.sourceReferences") }}</span>
                        <span class="sources-heading-meta">{{ getVisibleSources(msg).length }}</span>
                        <span class="sources-heading-toggle">{{ isSourcePanelExpanded(msg) ? t("chat.processCollapse") : t("chat.processExpand") }}</span>
                      </button>
                      <template v-if="isSourcePanelExpanded(msg)">
                        <div
                          v-for="source in getVisibleSources(msg)"
                          :key="source.source_id"
                          :ref="(el) => setSourceCardRef(String(msg.id), source.source_id, el)"
                          class="source-card"
                          :class="{ active: isSourceHighlighted(msg, source), clickable: getSourceCitationCount(msg, source) > 0 }"
                          @click="toggleSourceHighlight(msg, source)"
                        >
                          <div class="source-card-main">
                            <div v-if="isImageSource(source)" class="source-card-visual" @click.stop="showPreview(source)">
                              <img :src="getSourceImageSrc(source)" @error="onImgError" />
                            </div>
                            <div class="source-card-copy">
                              <div class="source-card-head">
                                <span class="source-card-title">{{ getSourceDisplayTitle(source) }}</span>
                                <div class="source-card-head-badges">
                                  <span v-if="getSourceCitationCount(msg, source) > 0" class="source-card-refcount">{{ getSourceCitationCount(msg, source) }}</span>
                                  <span v-if="getSourceAssetLabel(source)" class="source-card-badge">{{ getSourceAssetLabel(source) }}</span>
                                </div>
                              </div>
                              <div class="source-card-meta">
                                <span v-if="getSourcePageLabel(source)">{{ getSourcePageLabel(source) }}</span>
                                <span v-if="getSourceChunkLabel(source)">{{ getSourceChunkLabel(source) }}</span>
                                <span v-if="getSourceScoreLabel(source)">{{ getSourceScoreLabel(source) }}</span>
                              </div>
                              <p v-if="getSourceSummary(source)" class="source-card-summary">{{ getSourceSummary(source) }}</p>
                            </div>
                          </div>
                          <div class="source-card-actions-row">
                            <button
                              v-if="isImageSource(source)"
                              type="button"
                              class="message-action-btn compact"
                              @click.stop="showPreview(source)"
                            >
                              <i class="i-ep-zoom-in"></i>
                              <span>{{ t("chat.previewImage") }}</span>
                            </button>
                            <button
                              v-if="canOpenSourceDocument(source)"
                              type="button"
                              class="message-action-btn compact"
                              @click.stop="openSourceDocument(source)"
                            >
                              <i class="i-ep-document"></i>
                              <span>{{ t("chat.openSourceDoc") }}</span>
                            </button>
                          </div>
                        </div>
                      </template>
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
                      <template v-if="msg.role === 'assistant'">
                        <button
                          type="button"
                          class="message-action-btn"
                          :class="{ active: msg.feedback?.rating === 'up' }"
                          :disabled="feedbackSubmittingId === String(msg.id) || !hasPersistedAssistantMessageId(msg)"
                          @click="submitHelpfulFeedback(msg)"
                        >
                          <i class="i-ep-select"></i>
                          <span>{{ msg.feedback?.rating === "up" ? t("chat.feedbackSubmitted") : t("chat.feedbackHelpful") }}</span>
                        </button>
                        <el-popover
                          :visible="feedbackPopoverId === String(msg.id)"
                          placement="top"
                          :width="320"
                          trigger="manual"
                          popper-class="feedback-popover"
                        >
                          <template #reference>
                            <button
                              type="button"
                              class="message-action-btn"
                              :class="{ active: msg.feedback?.rating === 'down' }"
                              :disabled="feedbackSubmittingId === String(msg.id) || !hasPersistedAssistantMessageId(msg)"
                              @click="toggleFeedbackPopover(msg)"
                            >
                              <i class="i-ep-warning"></i>
                              <span>{{ msg.feedback?.rating === "down" ? t("chat.feedbackUpdate") : t("chat.feedbackIssue") }}</span>
                            </button>
                          </template>
                          <div class="feedback-panel">
                            <div class="feedback-title">{{ t("chat.feedbackPopoverTitle") }}</div>
                            <div class="feedback-label">{{ t("chat.feedbackIssueLabel") }}</div>
                            <el-checkbox-group v-model="getFeedbackForm(String(msg.id)).issue_types" class="feedback-checks">
                              <el-checkbox
                                v-for="option in feedbackIssueOptions"
                                :key="option.value"
                                :label="option.value"
                              >
                                {{ option.label }}
                              </el-checkbox>
                            </el-checkbox-group>
                            <div class="feedback-label">{{ t("chat.feedbackCommentLabel") }}</div>
                            <el-input
                              v-model="getFeedbackForm(String(msg.id)).comment"
                              type="textarea"
                              :rows="3"
                              :placeholder="t('chat.feedbackCommentPlaceholder')"
                            />
                            <div class="feedback-actions">
                              <el-button size="small" @click="feedbackPopoverId = null">{{ t("common.cancel") }}</el-button>
                              <el-button
                                size="small"
                                type="primary"
                                :loading="feedbackSubmittingId === String(msg.id)"
                                @click="submitIssueFeedback(msg)"
                              >
                                {{ t("chat.feedbackSubmit") }}
                              </el-button>
                            </div>
                          </div>
                        </el-popover>
                      </template>
                      <template v-if="canUseAssistantFollowup(msg)">
                        <button v-if="canRetryAssistantMessage(msg)" type="button" class="message-action-btn" @click="rerunAssistantMessage(msg, index)">
                          <i class="i-ep-refresh"></i>
                          <span>{{ t("chat.retryAnswer") }}</span>
                        </button>
                        <button type="button" class="message-action-btn" @click="expandAssistantMessage(msg)">
                          <i class="i-ep-plus"></i>
                          <span>{{ t("chat.expandAnswer") }}</span>
                        </button>
                        <button type="button" class="message-action-btn" @click="summarizeAssistantMessage(msg)">
                          <i class="i-ep-document"></i>
                          <span>{{ t("chat.summarizeAnswer") }}</span>
                        </button>
                      </template>
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
            <div v-if="composerWarnings.length > 0" class="composer-warning-stack">
              <div
                v-for="warning in composerWarnings"
                :key="warning"
                class="composer-warning"
              >
                <i class="i-ep-info-filled"></i>
                <span>{{ warning }}</span>
              </div>
            </div>
            <div v-if="showLargeTemplateCards" class="question-template-bar">
              <button
                v-for="template in questionTemplates"
                :key="template.id"
                type="button"
                class="question-template-chip"
                @click="applyQuestionTemplate(template)"
              >
                <span class="question-template-title">{{ template.title }}</span>
                <span class="question-template-desc">{{ template.description }}</span>
              </button>
            </div>
            <div class="composer-main">
              <div v-if="showCompactTemplateChips" class="compact-template-row">
                <button
                  v-for="template in questionTemplates"
                  :key="template.id"
                  type="button"
                  class="compact-template-chip"
                  @click="applyQuestionTemplate(template)"
                >
                  {{ template.title }}
                </button>
              </div>
              <div class="input-row">
                <div class="input-actions">
                  <el-upload :auto-upload="false" :show-file-list="false" :on-change="onImageChange">
                    <el-button text class="attach-btn primary-action"><i class="i-ep-plus"></i></el-button>
                  </el-upload>
                </div>
                <div class="chat-input-shell">
                  <div class="chat-input-card">
                    <el-input
                      ref="composerInputRef"
                      v-model="query"
                      :placeholder="dynamicInputPlaceholder"
                      class="chat-input"
                      :class="{ 'slash-active': isSlashMode, 'slash-invalid': hasInvalidSlashCommand }"
                      type="textarea"
                      :autosize="{ minRows: 1, maxRows: 5 }"
                      resize="none"
                      :disabled="isCurrentSessionPending"
                      @keydown="handleInputKeydown"
                    />
                    <div class="composer-toolbar">
                      <div class="composer-toolbar-group">
                        <el-dropdown trigger="click" @command="setChatMode">
                          <button type="button" class="composer-toolbar-chip primary">
                            <i class="i-ep-guide"></i>
                            <span>{{ composerModeLabel }}</span>
                            <i class="i-ep-arrow-down-bold"></i>
                          </button>
                          <template #dropdown>
                            <el-dropdown-menu>
                              <el-dropdown-item command="fast">{{ t("chat.chatModeFast") }}</el-dropdown-item>
                              <el-dropdown-item command="default">{{ t("chat.chatModeDefault") }}</el-dropdown-item>
                              <el-dropdown-item command="expert">{{ t("chat.chatModeExpert") }}</el-dropdown-item>
                            </el-dropdown-menu>
                          </template>
                        </el-dropdown>
                        <el-dropdown v-if="isDefaultChatMode" trigger="click" @command="setExecutionHint">
                          <button type="button" class="composer-toolbar-chip">
                            <i class="i-ep-switch"></i>
                            <span>{{ t("chat.executionMode") }}：{{ composerExecutionLabel }}</span>
                            <i class="i-ep-arrow-down-bold"></i>
                          </button>
                          <template #dropdown>
                            <el-dropdown-menu>
                              <el-dropdown-item command="auto">{{ t("chat.attachmentModeAuto") }}</el-dropdown-item>
                              <el-dropdown-item command="multimodal_rag">{{ t("chat.commandModeKb") }}</el-dropdown-item>
                              <el-dropdown-item command="direct_llm">{{ t("chat.commandModeDirect") }}</el-dropdown-item>
                              <el-dropdown-item command="image_similarity">{{ t("chat.commandModeImage") }}</el-dropdown-item>
                              <el-dropdown-item command="image_grounded_answer">{{ t("chat.modeImageGrounded") }}</el-dropdown-item>
                              <el-dropdown-item command="uploaded_image_qa">{{ t("chat.attachmentModeAskImage") }}</el-dropdown-item>
                              <el-dropdown-item command="save_uploaded_image">{{ t("chat.attachmentModeSave") }}</el-dropdown-item>
                            </el-dropdown-menu>
                          </template>
                        </el-dropdown>
                      </div>
                      <div class="composer-toolbar-group align-right">
                        <button type="button" class="composer-toolbar-chip" @click="openSourcePanel">
                          <i class="i-ep-collection-tag"></i>
                          <span>{{ composerSourceLabel }}</span>
                        </button>
                        <button
                          type="button"
                          class="composer-toolbar-chip subtle"
                          :class="{ active: settingsPanelOpen }"
                          @click="settingsPanelOpen = !settingsPanelOpen"
                        >
                          <i :class="settingsPanelOpen ? 'i-ep-arrow-up-bold' : 'i-ep-arrow-down-bold'"></i>
                          <span>{{ t("chat.retrievalSettings") }}：{{ settingsSummary }}</span>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                <el-button type="primary" class="send-btn" :loading="isCurrentSessionPending" @click="doChat">
                  <el-icon v-if="!isCurrentSessionPending"><Promotion /></el-icon>
                </el-button>
              </div>
            </div>
            <el-popover v-model:visible="sourcePanelOpen" placement="top-start" width="360" trigger="manual" popper-class="source-popover">
              <template #reference>
                <span class="source-popover-anchor" aria-hidden="true"></span>
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
            <div v-if="selectedSources.length > 0 || visibleSlashCommands.length > 0 || isSlashMode" class="composer-tools">
              <div v-if="selectedSources.length > 0" class="input-context-row">
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
                <div v-if="!isDefaultChatMode" class="settings-mode-note">
                  {{ t("chat.modeLegacyControlsDisabled") }}
                </div>
              </div>
            </el-collapse-transition>
            <div v-if="attachedImage" class="attached-preview">
              <img :src="attachedImagePreview" />
              <div class="attached-copy">
                <span class="attached-title">{{ t("chat.attachedImage") }}</span>
                <span class="attached-desc">{{ attachedImage?.name }}</span>
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
// ---- 导入 ----
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { Promotion } from "@element-plus/icons-vue";
import type { InputInstance, UploadFile } from "element-plus";
import { useRouter } from "vue-router";
import { getSessions, createSession, renameSession, deleteSession, getSessionMessages, ragChatStream, submitMessageFeedback, type ChatSession } from "@/api/chat";
import { listDocuments } from "@/api/docs";
import { listImages } from "@/api/kb";
import { getSystemConfig } from "@/api/settings";
import { imgSrc } from "@/utils/image";
import SessionList from "@/components/SessionList.vue";
import ImagePreviewModal from "@/components/ImagePreviewModal.vue";
import QaProcessCard from "@/components/QaProcessCard.vue";
import ChatMarkdown from "@/components/ChatMarkdown.vue";
import type { AnswerFeedbackResponse, ChatCitationChunkRef, ChatCitationItem, ChatMessage, ChatMode, ChatProgressEvent, ChatSourceItem, DocumentRecord, ImageRecord } from "@/types";

const { t } = useI18n();
const router = useRouter();

// ---- 类型定义 ----
/** 检索源条目（图片或文档片段） */
type SourceItem = ChatSourceItem;
/** 聊天消息 */
type Message = ChatMessage;
/** 引用条目（段落-来源映射） */
type CitationItem = ChatCitationItem;
/** 流式进度事件 */
type ProgressEvent = ChatProgressEvent;
/** 执行模式提示：控制后端走哪种检索/生成路径 */
type ExecutionHint =
  | "direct_llm"
  | "multimodal_rag"
  | "image_similarity"
  | "image_grounded_answer"
  | "uploaded_image_qa"
  | "save_uploaded_image";
/** 用户 @ 引用的来源标签（文档或图片） */
type SourceScopeChip = {
  type: "doc" | "image";
  id: string;
  title: string;
};
/** 斜杠命令定义 */
type SlashCommand = {
  command: string;
  label: string;
  description: string;
  apply: () => void;
};
/** 问题模板（快捷提问） */
type QuestionTemplate = {
  id: string;
  title: string;
  description: string;
  prompt: string;
  executionHint?: ExecutionHint | "auto";
};
/** 实时推理过程中的元数据条目 */
type LiveProcessDetailItem = {
  key: string;
  label: string;
  value: string;
};
/** 实时推理过程中已完成的步骤 */
type LiveProcessCompletedItem = {
  key: string;
  label: string;
  summary: string;
  elapsed: string;
};

// ---- 响应式状态 ----

// 会话管理状态
const sessions = ref<ChatSession[]>([]);
const currentSessionId = ref<string | undefined>();
const currentSessionTitle = ref("");
const messages = ref<Message[]>([]);
const query = ref("");
const pendingSessions = ref<Record<string, boolean>>({});

// 附件与图片上传状态
const attachedImage = ref<File | null>(null);
const attachedImagePreview = ref("");

// 聊天模式与执行模式状态
const selectedChatMode = ref<ChatMode>("default");
const selectedExecutionHint = ref<ExecutionHint | "auto">("auto");

// 来源引用面板状态（@ 搜索选择的文档/图片）
const selectedSources = ref<SourceScopeChip[]>([]);
const sourceQuery = ref("");
const sourcePanelOpen = ref(false);
const sourceLoading = ref(false);
const sourceDocLimit = ref(8);
const sourceImageLimit = ref(8);
const documentCandidates = ref<DocumentRecord[]>([]);
const imageCandidates = ref<ImageRecord[]>([]);

// 流式响应标识
const streamingId = ref("");

// 检索参数设置（TopK、分数过滤等）
const chatTopK = ref(5);
const chatEnableScoreFilter = ref(false);
const chatMinRelevanceScore = ref(0);
const chatDefaultTopK = ref(5);
const chatDefaultEnableScoreFilter = ref(false);
const chatDefaultMinRelevanceScore = ref(0);
const settingsPanelOpen = ref(false);

// UI 面板状态
const historyDrawerOpen = ref(false);
const isMobile = ref(false);

// 组件引用
const sessionListRef = ref<InstanceType<typeof SessionList>>();
const composerInputRef = ref<InputInstance>();
const messagesEndRef = ref<HTMLElement>();

// 会话草稿（切换会话时缓存未提交的消息）
const sessionDrafts = ref<Record<string, { messages: Message[]; title: string }>>({});

// 对象 URL 追踪（用于释放 createObjectURL 创建的临时 URL）
const objectUrls = new Set<string>();

// 图片预览弹窗状态
const previewVisible = ref(false);
const previewSrc = ref("");
const previewTitle = ref("");
const previewDescription = ref("");

// 引用高亮与来源卡片 DOM 引用
const sourceCardRefs = new Map<string, HTMLElement>();
const activeCitationMessageId = ref<string | null>(null);
const activeCitationSourceIds = ref<string[]>([]);
const activeCitationParagraphKeys = ref<string[]>([]);
const expandedSourcePanels = ref<Record<string, boolean>>({});

// 用户反馈弹窗状态
const feedbackPopoverId = ref<string | null>(null);
const feedbackSubmittingId = ref<string | null>(null);
const feedbackForms = ref<Record<string, { issue_types: string[]; comment: string }>>({});

// 实时推理过程展开状态与计时器
const liveProcessExpanded = ref<Record<string, boolean>>({});
const liveProcessNow = ref(Date.now());

// 防抖与竞态控制令牌
let loadSessionToken = 0;
let scrollToBottomRaf = 0;
let liveProcessTimer = 0;

// ---- 计算属性 ----

/** 是否存在正在等待响应的会话 */
const hasPendingSessions = computed(() => Object.keys(pendingSessions.value).length > 0);
/** 当前会话是否正在等待响应（阻止重复发送） */
const isCurrentSessionPending = computed(() => {
  if (!currentSessionId.value) return false;
  return Boolean(pendingSessions.value[currentSessionId.value]);
});

/** 是否为默认聊天模式（非 fast/expert） */
const isDefaultChatMode = computed(() => selectedChatMode.value === "default");

/** 综合计算后的执行模式：考虑附件模式和用户手动选择 */
const effectiveExecutionHint = computed<ExecutionHint | undefined>(() => {
  if (!isDefaultChatMode.value) {
    return undefined;
  }
  if (selectedExecutionHint.value !== "auto") {
    return selectedExecutionHint.value;
  }
  return undefined;
});

/** 用户选择的来源范围（限定检索的文档/图片 ID 集合） */
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

/** 反馈问题类型选项（检索错误/幻觉/缺少引用/无帮助） */
const feedbackIssueOptions = computed(() => [
  { value: "wrong_retrieval", label: t("chat.feedbackIssueWrongRetrieval") },
  { value: "hallucination", label: t("chat.feedbackIssueHallucination") },
  { value: "missing_citation", label: t("chat.feedbackIssueMissingCitation") },
  { value: "not_helpful", label: t("chat.feedbackIssueNotHelpful") },
]);

/** 斜杠命令列表：支持 /mode、/topk、/score、/trace、/clear_scope、/reset */
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

/** 根据当前聊天模式过滤可用的斜杠命令（非 default 模式隐藏 /mode 命令） */
const modeAwareSlashCommands = computed(() => {
  if (isDefaultChatMode.value) {
    return slashCommands.value;
  }
  return slashCommands.value.filter((item) => !item.command.startsWith("/mode "));
});

/** 斜杠命令解析结果 */
type ParsedSlashResult = {
  applied: boolean;
  valid: boolean;
  remainder: string;
  previewCommand: string | null;
};

/**
 * 解析输入字符串开头的斜杠命令
 * @param input - 用户输入文本
 * @param apply - 是否实际执行命令（为 false 时仅验证）
 * @returns 解析结果，包含是否成功、剩余文本和命中的命令
 */
function parseLeadingSlashCommands(input: string, apply = false): ParsedSlashResult {
  let rest = input.trim();
  let applied = false;
  let previewCommand: string | null = null;

  while (rest.startsWith("/")) {
    if (rest.startsWith("/mode ")) {
      if (!isDefaultChatMode.value) {
        return { applied, valid: false, remainder: rest, previewCommand: "/mode" };
      }
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

/** 根据当前输入过滤出匹配的斜杠命令候选项 */
const visibleSlashCommands = computed(() => {
  const normalized = query.value.trim().toLowerCase();
  if (!normalized.startsWith("/")) return [];
  const firstToken = normalized.split(/\s+/).slice(0, 2).join(" ");
  return modeAwareSlashCommands.value.filter((item) => item.command.startsWith(firstToken) || item.command.startsWith(normalized) || item.label.toLowerCase().includes(normalized.slice(1)));
});

/** 当前输入是否以斜杠开头（触发命令模式） */
const isSlashMode = computed(() => query.value.trim().startsWith("/"));
/** 当前输入的斜杠命令解析结果（只读预览模式） */
const slashParseResult = computed(() => parseLeadingSlashCommands(query.value, false));
/** 当前激活的斜杠命令（用于面板高亮） */
const activeSlashCommand = computed(() => {
  if (visibleSlashCommands.value.length > 0) return visibleSlashCommands.value[0];
  if (slashParseResult.value.previewCommand) {
    return modeAwareSlashCommands.value.find((item) => item.command.startsWith(slashParseResult.value.previewCommand || ""));
  }
  return null;
});
/** 输入中是否存在无效的斜杠命令 */
const hasInvalidSlashCommand = computed(() => isSlashMode.value && !slashParseResult.value.valid);

/** 检索设置摘要文本（显示在工具栏按钮上） */
const settingsSummary = computed(() => {
  const parts: string[] = [];
  if (!isDefaultChatMode.value) {
    parts.push(t("chat.modeAdvancedDisabled"));
  }
  if (chatTopK.value !== chatDefaultTopK.value) {
    parts.push(`TopK ${chatTopK.value}`);
  }
  if (chatEnableScoreFilter.value && (chatEnableScoreFilter.value !== chatDefaultEnableScoreFilter.value || chatMinRelevanceScore.value !== chatDefaultMinRelevanceScore.value)) {
    parts.push(`${t("chat.minRelevanceScore")} ≥ ${formatNumeric(chatMinRelevanceScore.value)}`);
  }
  return parts.length > 0 ? parts.join(" / ") : t("chat.defaultSettings");
});

/** 输入框模式下拉按钮标签（快速/默认/专家） */
const composerModeLabel = computed(() => {
  const modeMap: Record<ChatMode, string> = {
    fast: t("chat.chatModeFast"),
    default: t("chat.chatModeDefault"),
    expert: t("chat.chatModeExpert"),
  };
  return modeMap[selectedChatMode.value] || t("chat.chatModeDefault");
});

/** 执行模式下拉按钮标签 */
const composerExecutionLabel = computed(() => {
  const mode = effectiveExecutionHint.value;
  if (!mode) {
    return t("chat.attachmentModeAuto");
  }
  const modeMap: Record<ExecutionHint, string> = {
    direct_llm: t("chat.commandModeDirect"),
    multimodal_rag: t("chat.commandModeKb"),
    image_similarity: t("chat.commandModeImage"),
    image_grounded_answer: t("chat.modeImageGrounded"),
    uploaded_image_qa: t("chat.attachmentModeAskImage"),
    save_uploaded_image: t("chat.attachmentModeSave"),
  };
  return modeMap[mode];
});

/** 来源引用按钮标签（全部来源 或 N 篇文档 + M 张图片） */
const composerSourceLabel = computed(() => {
  const docCount = selectedSources.value.filter((item) => item.type === "doc").length;
  const imageCount = selectedSources.value.filter((item) => item.type === "image").length;
  if (docCount === 0 && imageCount === 0) {
    return t("chat.contextAllSources");
  }
  return t("chat.contextScopedSources", { docs: docCount, images: imageCount });
});

/** 输入框上方的警告提示列表（模式冲突、配置矛盾等） */
const composerWarnings = computed(() => {
  const warnings: string[] = [];
  if (selectedChatMode.value !== "default") {
    warnings.push(t("chat.modeLegacyControlsDisabled"));
  }
  if (effectiveExecutionHint.value === "direct_llm" && selectedSources.value.length > 0) {
    warnings.push(t("chat.warningDirectIgnoresSources"));
  }
  if (isDefaultChatMode.value && !attachedImage.value && (selectedExecutionHint.value === "uploaded_image_qa" || selectedExecutionHint.value === "save_uploaded_image")) {
    warnings.push(t("chat.warningAttachmentModeWithoutImage"));
  }
  if (isDefaultChatMode.value && attachedImage.value && selectedExecutionHint.value === "direct_llm") {
    warnings.push(t("chat.warningDirectWithAttachment"));
  }
  return warnings;
});

/** 根据当前模式动态切换输入框占位文本 */
const dynamicInputPlaceholder = computed(() => {
  if (selectedChatMode.value === "fast") return t("chat.inputPlaceholderFast");
  if (selectedChatMode.value === "expert") return t("chat.inputPlaceholderExpert");
  if (effectiveExecutionHint.value === "direct_llm") return t("chat.inputPlaceholderDirect");
  if (sourceScope.value) return t("chat.inputPlaceholderScoped");
  if (attachedImage.value && isDefaultChatMode.value && selectedExecutionHint.value === "uploaded_image_qa") return t("chat.inputPlaceholderAskImage");
  if (attachedImage.value && isDefaultChatMode.value && selectedExecutionHint.value === "image_similarity") return t("chat.inputPlaceholderFindSimilar");
  if (attachedImage.value && isDefaultChatMode.value && selectedExecutionHint.value === "save_uploaded_image") return t("chat.inputPlaceholderSaveImage");
  return "Enter 发送，Shift + Enter 换行";
});

/** 快捷问题模板列表（知识库摘要、图片问答、图片搜索等） */
const questionTemplates = computed<QuestionTemplate[]>(() => [
  {
    id: "kb-summary",
    title: t("chat.templateKbTitle"),
    description: t("chat.templateKbDesc"),
    prompt: t("chat.templateKbPrompt"),
    executionHint: "multimodal_rag",
  },
  {
    id: "image-qa",
    title: t("chat.templateImageQaTitle"),
    description: t("chat.templateImageQaDesc"),
    prompt: t("chat.templateImageQaPrompt"),
    executionHint: "uploaded_image_qa",
  },
  {
    id: "image-search",
    title: t("chat.templateImageSearchTitle"),
    description: t("chat.templateImageSearchDesc"),
    prompt: t("chat.templateImageSearchPrompt"),
    executionHint: "image_similarity",
  },
  {
    id: "doc-locate",
    title: t("chat.templateDocLocateTitle"),
    description: t("chat.templateDocLocateDesc"),
    prompt: t("chat.templateDocLocatePrompt"),
    executionHint: "multimodal_rag",
  },
  {
    id: "save-image",
    title: t("chat.templateSaveImageTitle"),
    description: t("chat.templateSaveImageDesc"),
    prompt: t("chat.templateSaveImagePrompt"),
    executionHint: "save_uploaded_image",
  },
]);

/** 是否显示大尺寸模板卡片（空会话时显示） */
const showLargeTemplateCards = computed(() => questionTemplates.value.length > 0 && messages.value.length === 0);
/** 是否显示紧凑模板标签（有消息且输入框为空时显示） */
const showCompactTemplateChips = computed(() =>
  questionTemplates.value.length > 0
  && messages.value.length > 0
  && query.value.trim().length === 0,
);

// ---- 侦听器 ----

/** 检索参数变化时自动打开/关闭设置面板 */
watch([chatTopK, chatEnableScoreFilter, chatMinRelevanceScore], () => {
  settingsPanelOpen.value =
    chatTopK.value !== chatDefaultTopK.value ||
    chatEnableScoreFilter.value !== chatDefaultEnableScoreFilter.value ||
    (chatEnableScoreFilter.value && chatMinRelevanceScore.value !== chatDefaultMinRelevanceScore.value);
});

/** 输入框内容变化时：@ 触发来源面板、斜杠模式下关闭来源面板 */
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

// ---- 工具函数 ----

/** 更新视口状态（检测移动端） */
function updateViewportState() {
  isMobile.value = window.innerWidth < 1100;
}

// ---- 来源引用面板 ----

/** 加载可引用的文档和图片候选列表 */
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

/** 打开来源引用面板并加载候选 */
function openSourcePanel() {
  sourcePanelOpen.value = true;
  loadSourceCandidates(sourceQuery.value);
}

/** 加载更多来源候选（分页加载） */
function loadMoreSources(type: "doc" | "image") {
  if (type === "doc") {
    sourceDocLimit.value += 8;
  } else {
    sourceImageLimit.value += 8;
  }
  loadSourceCandidates(sourceQuery.value);
}

/** 添加一个来源标签到选中列表 */
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

/** 移除指定索引的来源标签 */
function removeSourceChip(index: number) {
  selectedSources.value.splice(index, 1);
}

// ---- 斜杠命令与输入处理 ----

/** 执行选中的斜杠命令并显示成功提示 */
function applySlashCommand(command: SlashCommand) {
  command.apply();
  ElMessage.success(t("chat.commandApplied", { command: command.command }));
}

/**
 * 处理输入框键盘事件
 * - Enter：斜杠命令模式下执行命令，普通模式下发送消息
 * - Shift+Enter：换行
 */
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

// ---- 消息操作（复制/引用/重发） ----

/** 获取消息作者显示名称 */
function getMessageAuthor(msg: Message): string {
  return msg.role === "assistant" ? t("chat.assistantName") : t("chat.userName");
}

/** 获取用户消息中的上传图预览地址，优先使用本地 Object URL，历史消息回退到后端静态路径 */
function getUserAttachmentPreviewSrc(msg: Message): string {
  if (msg.local_image_url) {
    return msg.local_image_url;
  }
  const path = msg.uploaded_image_path || (typeof msg.retrieval_params?.uploaded_image_path === "string" ? msg.retrieval_params.uploaded_image_path : "");
  return path ? imgSrc(path) : "";
}

/** 获取用户上传图文件名 */
function getUserAttachmentName(msg: Message): string {
  const name = msg.uploaded_image_name || (typeof msg.retrieval_params?.uploaded_image_name === "string" ? msg.retrieval_params.uploaded_image_name : "");
  return String(name || "").trim();
}

/** 判断用户消息是否包含附件 */
function hasUserAttachment(msg: Message): boolean {
  return msg.role === "user" && (Boolean(msg.has_image) || Boolean(getUserAttachmentPreviewSrc(msg)));
}

/** 打开用户上传图预览弹窗 */
function showUserAttachmentPreview(msg: Message) {
  const src = getUserAttachmentPreviewSrc(msg);
  if (!src) return;
  previewSrc.value = src;
  previewTitle.value = getUserAttachmentName(msg) || t("chat.attachedImage");
  previewDescription.value = String(msg.content || "");
  previewVisible.value = true;
}

/** 获取消息的可复制纯文本 */
function getCopyableMessageText(msg: Message): string {
  return String(msg.content || "").trim();
}

/** 复制消息内容到剪贴板（兼容不支持 Clipboard API 的环境） */
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

/** 将文本转为 Markdown 引用格式（每行前加 > ） */
function buildQuotedMessage(text: string): string {
  return text
    .split("\n")
    .map((line) => `> ${line}`)
    .join("\n");
}

/** 聚焦到输入框 */
function focusComposer() {
  nextTick(() => {
    composerInputRef.value?.focus?.();
  });
}

/** 引用消息内容到输入框（以 Markdown 引用格式插入） */
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

/** 从指定位置向前查找最近的用户消息（用于助手消息的重发） */
function getRelatedUserMessage(index: number): Message | undefined {
  for (let current = index; current >= 0; current -= 1) {
    const candidate = messages.value[current];
    if (candidate?.role === "user" && String(candidate.content || "").trim()) {
      return candidate;
    }
  }
  return undefined;
}

/** 重发消息：将原问题填入输入框并立即发送 */
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

// ---- 会话管理 ----

/** 从后端加载会话列表 */
async function loadSessions() {
  try {
    sessions.value = await getSessions();
  } catch (e) {
    console.error("加载会话列表失败:", e);
  }
}

/** 加载指定会话的消息列表（支持草稿缓存和竞态保护） */
async function loadSession(id: string) {
  const token = ++loadSessionToken;
  const draft = sessionDrafts.value[id];
  messages.value = draft?.messages ? draft.messages.map(cloneMessage) : [];
  syncFeedbackFormsForMessages(messages.value);
  currentSessionTitle.value = draft?.title || sessions.value.find((s) => s.id === id)?.title || "";
  try {
    const msgs = await getSessionMessages(id);
    if (token !== loadSessionToken || currentSessionId.value !== id) {
      return;
    }
    if (msgs.length > 0 || !draft?.messages?.length) {
      messages.value = msgs.map(cloneMessage);
      syncFeedbackFormsForMessages(messages.value);
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

/** 切换到指定会话 */
function selectSession(id: string) {
  currentSessionId.value = id;
}

/** 从抽屉面板选择会话（同时关闭抽屉） */
function selectSessionFromDrawer(id: string) {
  historyDrawerOpen.value = false;
  selectSession(id);
}

/** 会话切换时保存旧会话草稿、加载新会话消息 */
watch(currentSessionId, (newId, oldId) => {
  clearCitationHighlight();
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

/** 创建新会话并自动切换 */
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

/** 打开会话重命名对话框 */
function handleRenameSession(id: string) {
  const session = sessions.value.find((s) => s.id === id);
  if (session) {
    sessionListRef.value?.openRenameDialog(id, session.title || "");
  }
}

/** 更新会话标题（调用后端接口并同步本地状态） */
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

/** 删除会话（后端删除 + 本地清理） */
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

// ---- 图片附件处理 ----

/** 用户选择图片文件时的回调 */
function onImageChange(file: UploadFile) {
  revokeAttachedPreview();
  attachedImage.value = file.raw || null;
  if (file.raw) {
    attachedImagePreview.value = URL.createObjectURL(file.raw);
  }
}

/** 释放附件预览的 Object URL */
function revokeAttachedPreview() {
  if (attachedImagePreview.value) {
    URL.revokeObjectURL(attachedImagePreview.value);
    attachedImagePreview.value = "";
  }
}

/** 移除已附加的图片 */
function removeAttached() {
  attachedImage.value = null;
  revokeAttachedPreview();
}

/** 追踪 Object URL 以便组件销毁时统一释放 */
function trackObjectUrl(url: string) {
  objectUrls.add(url);
  return url;
}

// ---- 消息深拷贝与进度追踪 ----

/** 深拷贝消息对象（避免引用共享导致的状态污染） */
function cloneMessage(message: Message): Message {
  const normalizedCitations = message.citations
    ? message.citations.map((citation) => ({
      ...citation,
      source_ids: [...citation.source_ids],
      doc_chunk_refs: citation.doc_chunk_refs ? citation.doc_chunk_refs.map((ref) => ({ ...ref })) : [],
    }))
    : (Array.isArray(message.retrieval_params?.citations)
      ? (message.retrieval_params.citations as CitationItem[]).map((citation) => ({
        ...citation,
        source_ids: [...citation.source_ids],
        doc_chunk_refs: citation.doc_chunk_refs ? citation.doc_chunk_refs.map((ref) => ({ ...ref })) : [],
      }))
      : []);
  return {
    ...message,
    sources: message.sources ? [...message.sources] : [],
    citations: normalizedCitations,
    retrieval_steps: message.retrieval_steps ? [...message.retrieval_steps] : [],
    retrieval_params: message.retrieval_params ? { ...message.retrieval_params, citations: normalizedCitations } : null,
    feedback: message.feedback ? { ...message.feedback, issue_types: [...message.feedback.issue_types] } : null,
    timings: message.timings ? { ...message.timings, stages: [...message.timings.stages] } : null,
    live_progress: message.live_progress ? { ...message.live_progress, meta: message.live_progress.meta ? { ...message.live_progress.meta } : undefined } : null,
    live_progress_steps: message.live_progress_steps ? message.live_progress_steps.map((step) => ({ ...step, meta: step.meta ? { ...step.meta } : undefined })) : [],
    live_progress_started_at: message.live_progress_started_at || null,
    live_progress_active_phase: message.live_progress_active_phase || null,
    live_progress_done: Boolean(message.live_progress_done),
  };
}

/** 合并进度事件到步骤列表（同 phase 更新，不同 phase 追加） */
function mergeProgressSteps(existing: ProgressEvent[], incoming: ProgressEvent): ProgressEvent[] {
  const key = incoming.step_key || incoming.phase;
  const nextSteps = [...existing];
  const index = nextSteps.findIndex((step) => (step.step_key || step.phase) === key);
  if (index >= 0) {
    nextSteps[index] = {
      ...nextSteps[index],
      ...incoming,
      meta: {
        ...(nextSteps[index].meta || {}),
        ...(incoming.meta || {}),
      },
    };
    return nextSteps;
  }
  nextSteps.push(incoming);
  return nextSteps;
}

/** 更新助手消息的实时推理进度（支持跨会话草稿更新） */
function updateLiveAssistantProgress(targetSessionId: string, assistantId: string, event: ProgressEvent) {
  const applyProgress = (message: Message) => {
    const nextEvent: ProgressEvent = {
      ...event,
      meta: event.meta ? { ...event.meta } : undefined,
    };
    message.live_progress_started_at = message.live_progress_started_at || new Date().toISOString();
    message.live_progress = nextEvent;
    message.live_progress_steps = mergeProgressSteps(message.live_progress_steps || [], nextEvent);
    message.live_progress_active_phase = event.status === "completed" ? null : event.phase;
    message.live_progress_done = event.phase === "complete" || event.status === "failed";
  };

  if (currentSessionId.value === targetSessionId) {
    const target = messages.value.find((message) => String(message.id) === assistantId);
    if (target) {
      applyProgress(target);
      saveSessionDraft(targetSessionId);
    }
  } else {
    updateDraftMessage(targetSessionId, assistantId, applyProgress);
  }
}

/** 释放消息列表中所有已追踪的 Object URL */
function revokeMessageUrls(list: Message[]) {
  list.forEach((message) => {
    if (message.local_image_url && objectUrls.has(message.local_image_url)) {
      URL.revokeObjectURL(message.local_image_url);
      objectUrls.delete(message.local_image_url);
    }
  });
}

// ---- 草稿管理 ----

/** 保存当前会话消息到草稿缓存 */
function saveSessionDraft(sessionId: string) {
  if (!sessionId) return;
  sessionDrafts.value[sessionId] = {
    messages: messages.value.map(cloneMessage),
    title: currentSessionTitle.value || sessions.value.find((session) => session.id === sessionId)?.title || "",
  };
}

// ---- 反馈表单管理 ----

/** 获取或初始化指定消息的反馈表单 */
function getFeedbackForm(messageId: string) {
  if (!feedbackForms.value[messageId]) {
    feedbackForms.value[messageId] = {
      issue_types: [],
      comment: "",
    };
  }
  return feedbackForms.value[messageId];
}

/** 将消息已有的反馈数据同步到表单 */
function syncFeedbackForm(message: Message) {
  if (message.role !== "assistant") return;
  const form = getFeedbackForm(String(message.id));
  form.issue_types = message.feedback?.issue_types ? [...message.feedback.issue_types] : [];
  form.comment = message.feedback?.comment || "";
}

/** 将后端返回的反馈结果应用到消息和草稿 */
function applyMessageFeedback(messageId: string | number, sessionId: string, feedback: AnswerFeedbackResponse) {
  const normalizedId = String(messageId);
  const target = messages.value.find((message) => String(message.id) === normalizedId);
  if (target) {
    target.feedback = {
      ...feedback,
      issue_types: [...feedback.issue_types],
    };
    syncFeedbackForm(target);
  }
  updateDraftMessage(sessionId, normalizedId, (message) => {
    message.feedback = {
      ...feedback,
      issue_types: [...feedback.issue_types],
    };
  });
  if (currentSessionId.value === sessionId) {
    saveSessionDraft(sessionId);
  }
}

/** 批量同步反馈表单 */
function syncFeedbackFormsForMessages(list: Message[]) {
  list.forEach((message) => syncFeedbackForm(message));
}

/** 判断助手消息是否已持久化（ID 为整数表示已入库） */
function hasPersistedAssistantMessageId(message: Message): boolean {
  return message.role === "assistant" && Number.isInteger(Number(message.id));
}

/** 清除指定会话的草稿缓存并释放 Object URL */
function clearSessionDraft(sessionId: string) {
  const draft = sessionDrafts.value[sessionId];
  if (draft?.messages?.length) {
    revokeMessageUrls(draft.messages);
  }
  delete sessionDrafts.value[sessionId];
}

/** 向指定会话的草稿追加一条消息 */
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

/** 更新草稿中指定消息的内容（通过 updater 回调修改） */
function updateDraftMessage(sessionId: string, messageId: string | number, updater: (message: Message) => void) {
  if (!sessionId) return;
  const existing = sessionDrafts.value[sessionId];
  if (!existing?.messages?.length) return;
  const draftMessages = existing.messages.map(cloneMessage);
  const target = draftMessages.find((message) => String(message.id) === String(messageId));
  if (!target) return;
  updater(target);
  sessionDrafts.value[sessionId] = {
    messages: draftMessages,
    title: existing.title,
  };
}

/** 从草稿中移除指定消息 */
function removeDraftMessage(sessionId: string, messageId: string | number) {
  if (!sessionId) return;
  const existing = sessionDrafts.value[sessionId];
  if (!existing?.messages?.length) return;
  sessionDrafts.value[sessionId] = {
    messages: existing.messages.filter((message) => String(message.id) !== String(messageId)).map(cloneMessage),
    title: existing.title,
  };
}

/** 重命名 pending 会话的 key（后端返回真实 ID 时迁移） */
function renamePendingSessionKey(fromId: string, toId: string) {
  if (!fromId || !toId || fromId === toId || !pendingSessions.value[fromId]) return;
  const { [fromId]: pendingValue, ...restPending } = pendingSessions.value;
  pendingSessions.value = {
    ...restPending,
    [toId]: pendingValue,
  };
}

/** 将草稿从旧会话 ID 迁移到新会话 ID */
function moveSessionDraft(fromId: string, toId: string) {
  if (!fromId || !toId || fromId === toId || !sessionDrafts.value[fromId]) return;
  sessionDrafts.value[toId] = sessionDrafts.value[fromId];
  delete sessionDrafts.value[fromId];
}

/** 获取会话显示标题（优先取草稿标题） */
function getSessionDisplayTitle(sessionId: string, fallback?: string) {
  return sessionDrafts.value[sessionId]?.title || fallback || t("chat.newSession");
}

/** 根据用户提问自动生成会话标题（截取首句，最多 18 字符） */
function generateSessionTitle(rawQuery: string): string {
  const normalized = rawQuery.replace(/\s+/g, " ").trim();
  if (!normalized) return t("chat.newSession");
  const sentence = normalized.split(/[。！？!?；;\n]/)[0] || normalized;
  const compact = sentence.replace(/^[,，。！？!?、\s]+/, "").trim();
  if (compact.length <= 18) return compact;
  return `${compact.slice(0, 18)}…`;
}

// ---- 消息展示模式与来源渲染 ----

/** 获取消息的展示模式（rag_answer / direct_answer / image_only / image_plus_answer） */
function getPresentationMode(msg: Message): string {
  return msg.presentation_mode || msg.retrieval_params?.presentation_mode || "rag_answer";
}

/** 获取消息中的图片类型来源 */
function getImageSources(msg: Message): SourceItem[] {
  return (msg.sources || []).filter((source) => source.source_type === "image");
}

/** 获取消息中所有可见的来源列表 */
function getVisibleSources(msg: Message): SourceItem[] {
  return msg.sources || [];
}

/** 获取消息的引用列表（段落-来源映射） */
function getMessageCitations(msg: Message): CitationItem[] {
  return msg.citations || (Array.isArray(msg.retrieval_params?.citations) ? msg.retrieval_params.citations as CitationItem[] : []);
}

/** 生成来源 ID 到显示标签（S1、S2...）的映射 */
function getSourceLabelMap(msg: Message): Record<string, string> {
  return getVisibleSources(msg).reduce<Record<string, string>>((acc, source, index) => {
    acc[source.source_id] = `S${index + 1}`;
    return acc;
  }, {});
}

/** 获取指定来源被引用的次数 */
function getSourceCitationCount(msg: Message, source: SourceItem): number {
  return getMessageCitations(msg).filter((citation) => citation.source_ids.includes(source.source_id)).length;
}

/** 获取当前高亮的段落 key 列表 */
function getActiveParagraphKeys(msg: Message): string[] {
  return activeCitationMessageId.value === String(msg.id) ? activeCitationParagraphKeys.value : [];
}

/** 获取当前高亮的来源 ID 列表 */
function getActiveSourceIds(msg: Message): string[] {
  return activeCitationMessageId.value === String(msg.id) ? activeCitationSourceIds.value : [];
}

// ---- 来源面板展开/折叠 ----

/** 检查消息的来源面板是否展开 */
function isSourcePanelExpanded(msg: Message): boolean {
  return Boolean(expandedSourcePanels.value[String(msg.id)]);
}

/** 切换来源面板的展开/折叠状态 */
function toggleSourcePanel(msg: Message): void {
  const key = String(msg.id);
  expandedSourcePanels.value = {
    ...expandedSourcePanels.value,
    [key]: !expandedSourcePanels.value[key],
  };
}

/** 展开来源面板（如果尚未展开） */
function expandSourcePanel(msg: Message): void {
  const key = String(msg.id);
  if (expandedSourcePanels.value[key]) {
    return;
  }
  expandedSourcePanels.value = {
    ...expandedSourcePanels.value,
    [key]: true,
  };
}

/** 注册来源卡片的 DOM 引用（用于滚动定位） */
function setSourceCardRef(messageId: string, sourceId: string, element: Element | { $el?: Element } | null) {
  const key = `${messageId}::${sourceId}`;
  const actualElement = element instanceof HTMLElement
    ? element
    : element && "$el" in element && element.$el instanceof HTMLElement
      ? element.$el
      : null;
  if (actualElement) {
    sourceCardRefs.set(key, actualElement);
    return;
  }
  sourceCardRefs.delete(key);
}

/** 清除所有引用高亮状态 */
function clearCitationHighlight() {
  activeCitationMessageId.value = null;
  activeCitationSourceIds.value = [];
  activeCitationParagraphKeys.value = [];
}

function scrollToHighlightedSource(messageId: string, sourceId: string) {
  const target = sourceCardRefs.get(`${messageId}::${sourceId}`);
  target?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function isSourceHighlighted(msg: Message, source: SourceItem): boolean {
  return getActiveSourceIds(msg).includes(source.source_id);
}

function handleParagraphSelect(msg: Message, citation: CitationItem) {
  const messageId = String(msg.id);
  const sameSelection = activeCitationMessageId.value === messageId
    && activeCitationParagraphKeys.value.length === 1
    && activeCitationParagraphKeys.value[0] === citation.paragraph_key;
  if (sameSelection) {
    clearCitationHighlight();
    return;
  }
  activeCitationMessageId.value = messageId;
  activeCitationParagraphKeys.value = [citation.paragraph_key];
  activeCitationSourceIds.value = [...citation.source_ids];
  if (citation.source_ids.length > 0) {
    expandSourcePanel(msg);
    nextTick(() => scrollToHighlightedSource(messageId, citation.source_ids[0]));
  }
}

function toggleSourceHighlight(msg: Message, source: SourceItem) {
  const citations = getMessageCitations(msg);
  if (!citations.length) {
    return;
  }
  const relatedParagraphKeys = citations
    .filter((citation) => citation.source_ids.includes(source.source_id))
    .map((citation) => citation.paragraph_key);
  if (!relatedParagraphKeys.length) {
    return;
  }
  const messageId = String(msg.id);
  const sameSelection = activeCitationMessageId.value === messageId
    && activeCitationSourceIds.value.length === 1
    && activeCitationSourceIds.value[0] === source.source_id;
  if (sameSelection) {
    clearCitationHighlight();
    return;
  }
  activeCitationMessageId.value = messageId;
  activeCitationSourceIds.value = [source.source_id];
  activeCitationParagraphKeys.value = relatedParagraphKeys;
  expandSourcePanel(msg);
  nextTick(() => scrollToHighlightedSource(messageId, source.source_id));
}

function isImageSource(source: SourceItem): boolean {
  return source.source_type === "image";
}

function isDocumentSource(source: SourceItem): boolean {
  return source.source_type === "document_chunk";
}

function isImageFocusedMode(msg: Message): boolean {
  const mode = getPresentationMode(msg);
  return mode === "image_only" || mode === "image_plus_answer";
}

function shouldShowSourcesFirst(msg: Message): boolean {
  return msg.role === "assistant" && isImageFocusedMode(msg) && getVisibleSources(msg).length > 0;
}

function shouldShowSourcesAfterText(msg: Message): boolean {
  return msg.role === "assistant" && !isImageFocusedMode(msg) && getVisibleSources(msg).length > 0;
}

function getMessageChatMode(msg: Message): ChatMode {
  const mode = msg.chat_mode || msg.retrieval_params?.chat_mode;
  if (mode === "fast" || mode === "expert") {
    return mode;
  }
  return "default";
}

function getModeLabel(msg: Message): string {
  const modeMap: Record<ChatMode, string> = {
    fast: t("chat.chatModeFast"),
    default: t("chat.chatModeDefault"),
    expert: t("chat.chatModeExpert"),
  };
  const chatModeLabel = modeMap[getMessageChatMode(msg)];
  if (msg.execution_mode === "save_uploaded_image") {
    return `${chatModeLabel} · ${t("chat.modeSavedToKb")}`;
  }
  switch (getPresentationMode(msg)) {
    case "direct_answer":
      return `${chatModeLabel} · ${t("chat.modeDirectAnswer")}`;
    case "image_only":
      return `${chatModeLabel} · ${t("chat.modeImageOnly")}`;
    case "image_plus_answer":
      return `${chatModeLabel} · ${t("chat.modeImageGrounded")}`;
    default:
      return `${chatModeLabel} · ${t("chat.modeKnowledgeAnswer")}`;
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

function getSourceChunkLabel(source: SourceItem): string {
  const chunkIndex = source.metadata?.chunk_index;
  if (typeof chunkIndex === "number") {
    return t("chat.chunkLabel", { index: chunkIndex + 1 });
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
  const rerankScore = Number(source.rerank_score);
  if (!Number.isNaN(rerankScore)) {
    return `RERANK ${formatNumeric(rerankScore)}`;
  }
  const score = Number(source.score);
  if (!Number.isNaN(score)) {
    return `SCORE ${formatNumeric(score)}`;
  }
  return "";
}

function getSourceDisplayTitle(source: SourceItem): string {
  return source.title
    || String(source.metadata?.file_name || source.metadata?.filename || source.metadata?.doc_id || source.source_id);
}

function getSourceSummary(source: SourceItem): string {
  const raw = String(source.content || "").replace(/\s+/g, " ").trim();
  if (!raw) return "";
  return raw.length > 140 ? `${raw.slice(0, 140)}…` : raw;
}

function canOpenSourceDocument(source: SourceItem): boolean {
  return Boolean(source.metadata?.doc_id);
}

function openSourceDocument(source: SourceItem) {
  const docId = String(source.metadata?.doc_id || "").trim();
  if (!docId) return;
  const queryParams: Record<string, string> = {
    docId,
    tab: isDocumentSource(source) ? "chunks" : "images",
  };
  if (typeof source.metadata?.chunk_index === "number") {
    queryParams.chunk = String(source.metadata.chunk_index);
  }
  if (typeof source.metadata?.page_number === "number") {
    queryParams.page = String(source.metadata.page_number);
  }
  router.push({ path: "/docs", query: queryParams });
}

function openCitationDocRef(ref: ChatCitationChunkRef) {
  const docId = String(ref.doc_id || "").trim();
  if (!docId) return;
  const queryParams: Record<string, string> = {
    docId,
    tab: "chunks",
    chunk: String(ref.chunk_index),
  };
  if (typeof ref.page_number === "number") {
    queryParams.page = String(ref.page_number);
  }
  router.push({ path: "/docs", query: queryParams });
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
  return Boolean(
    (!msg.live_progress_steps || msg.live_progress_steps.length === 0)
    && ((msg.retrieval_steps && msg.retrieval_steps.length > 0)
    || msg.timings
    || msg.retrieval_params?.timings),
  );
}

function shouldShowLiveProcessText(msg: Message): boolean {
  return msg.role === "assistant" && Boolean(msg.live_progress_steps && msg.live_progress_steps.length > 0);
}

function getLiveProcessMessageKey(msg: Message): string {
  return String(msg.id);
}

function isLiveProcessDetailsOpen(msg: Message): boolean {
  return Boolean(liveProcessExpanded.value[getLiveProcessMessageKey(msg)]);
}

function toggleLiveProcessDetails(msg: Message): void {
  const key = getLiveProcessMessageKey(msg);
  liveProcessExpanded.value = {
    ...liveProcessExpanded.value,
    [key]: !liveProcessExpanded.value[key],
  };
}

function shouldShowLiveProcessDetails(msg: Message): boolean {
  return shouldShowLiveProcessText(msg) && isLiveProcessDetailsOpen(msg);
}

function getLatestLiveProgress(msg: Message): ProgressEvent | null {
  return msg.live_progress || msg.live_progress_steps?.[msg.live_progress_steps.length - 1] || null;
}

function getLiveProcessText(msg: Message): string {
  const latest = getLatestLiveProgress(msg);
  if (!latest) {
    return t("chat.thinking");
  }
  if (latest.phase === "routing") return t("chat.thinkingRouting");
  if (latest.phase === "rewrite") return t("chat.thinkingRewrite");
  if (latest.phase === "retrieve") return t("chat.thinkingRetrieve");
  if (latest.phase === "rerank") return t("chat.thinkingRerank");
  if (latest.phase === "compress") return t("chat.thinkingCompress");
  if (latest.phase === "agentic") return t("chat.thinkingAgentic");
  if (latest.phase === "generate") return t("chat.thinkingGenerate");
  return t("chat.thinking");
}

function getLiveProcessSubtext(msg: Message): string {
  const latest = getLatestLiveProgress(msg);
  if (!latest) {
    return "";
  }
  const detail = String(latest.detail || "").trim();
  if (detail) {
    return detail;
  }
  let elapsed = typeof latest.elapsed_ms === "number" ? latest.elapsed_ms : null;
  if (elapsed === null && msg.live_progress_started_at) {
    elapsed = Math.max(0, liveProcessNow.value - new Date(msg.live_progress_started_at).getTime());
  }
  if (elapsed === null) {
    return "";
  }
  if (elapsed >= 1000) {
    return `${(elapsed / 1000).toFixed(1)} s`;
  }
  return `${Math.round(elapsed)} ms`;
}

function getLiveProcessCurrentStepLabel(msg: Message): string {
  const latest = getLatestLiveProgress(msg);
  if (!latest) {
    return t("chat.thinking");
  }
  if (latest.phase === "routing") return t("chat.processIntent");
  if (latest.phase === "rewrite") return t("chat.processRewrite");
  if (latest.phase === "retrieve") return t("chat.processRetrieve");
  if (latest.phase === "rerank") return t("chat.processRerank");
  if (latest.phase === "compress") return t("chat.processCompression");
  if (latest.phase === "agentic") return t("chat.processAgentic");
  if (latest.phase === "generate") return t("chat.processGenerate");
  return t("chat.processComplete");
}

function getLiveProcessCurrentStepStatus(msg: Message): string {
  const latest = getLatestLiveProgress(msg);
  if (!latest) {
    return t("chat.processStatusRunning");
  }
  if (latest.status === "completed") return t("chat.processStatusCompleted");
  if (latest.status === "skipped") return t("chat.processStatusSkipped");
  if (latest.status === "failed") return t("chat.processStatusFailed");
  return t("chat.processStatusRunning");
}

function getLiveProcessCurrentStepSummary(msg: Message): string {
  const latest = getLatestLiveProgress(msg);
  if (!latest) {
    return "";
  }
  const detail = String(latest.detail || "").trim();
  if (detail) {
    return detail;
  }
  if (typeof latest.elapsed_ms === "number") {
    return `${t("chat.processTotal")} ${formatLiveProcessElapsed(latest.elapsed_ms)}`;
  }
  return "";
}

function getLiveProcessCurrentStepDetailItems(msg: Message): LiveProcessDetailItem[] {
  const latest = getLatestLiveProgress(msg);
  if (!latest) {
    return [];
  }
  const detailItems: LiveProcessDetailItem[] = [];
  const pushItem = (key: string, label: string, value: string | null | undefined) => {
    const normalized = String(value ?? "").trim();
    if (!normalized) {
      return;
    }
    detailItems.push({ key, label, value: normalized });
  };
  const boolState = (value: unknown, enabledDisabled = true): string => {
    if (value === true) {
      return enabledDisabled ? t("chat.processEnabled") : t("chat.processYes");
    }
    if (value === false) {
      return enabledDisabled ? t("chat.processSkipped") : t("chat.processNo");
    }
    return "";
  };
  const meta = (latest.meta || {}) as Record<string, unknown>;
  pushItem("chat_mode", t("chat.processChatMode"), formatChatModeLabel(latest.chat_mode));
  pushItem("execution_mode", t("chat.processExecutionMode"), latest.execution_mode || "");
  pushItem("knowledge_route", t("chat.processKnowledgeRoute"), typeof latest.use_rag === "boolean" ? (latest.use_rag ? t("chat.processEnabled") : t("chat.processDisabled")) : "");
  pushItem("source_scope_enabled", t("chat.processSourceScope"), boolState(meta.source_scope_enabled));
  pushItem("query_rewrite_enabled", t("chat.processQueryRewrite"), boolState(meta.query_rewrite_enabled));
  pushItem("retrieved_candidates", t("chat.processCandidateCount"), formatScalarValue(meta.retrieved_candidates));
  pushItem("top_k", t("chat.processTopK"), formatScalarValue(meta.top_k));
  pushItem("rerank_enabled", t("chat.processRerank"), boolState(meta.rerank_enabled));
  pushItem("compression_enabled", t("chat.processCompression"), boolState(meta.compression_enabled));
  pushItem("agentic_enabled", t("chat.processAgentic"), boolState(meta.agentic_enabled));
  pushItem("retry_used", t("chat.processRetryUsed"), boolState(meta.retry_used, false));
  pushItem("generation_started", t("chat.processGenerationStatus"), boolState(meta.generation_started, false));
  pushItem("classifier", t("chat.processClassifier"), formatScalarValue(meta.classifier));
  pushItem("has_uploaded_image", t("chat.processUploadedImage"), boolState(meta.has_uploaded_image, false));
  return detailItems;
}

function getLiveProcessCompletedSteps(msg: Message): LiveProcessCompletedItem[] {
  if (!msg.live_progress_steps || msg.live_progress_steps.length <= 1) {
    return [];
  }
  return msg.live_progress_steps
    .slice(0, -1)
    .filter((step) => step.status === "completed" || step.status === "skipped" || step.status === "failed")
    .map((step, index) => ({
      key: `${step.phase}-${index}`,
      label: getLiveProcessLabelByPhase(step.phase),
      summary: String(step.detail || getLiveProcessStatusText(step.status)).trim(),
      elapsed: typeof step.elapsed_ms === "number" ? formatLiveProcessElapsed(step.elapsed_ms) : "",
    }));
}

function getLiveProcessLabelByPhase(phase: ProgressEvent["phase"]): string {
  if (phase === "routing") return t("chat.processIntent");
  if (phase === "rewrite") return t("chat.processRewrite");
  if (phase === "retrieve") return t("chat.processRetrieve");
  if (phase === "rerank") return t("chat.processRerank");
  if (phase === "compress") return t("chat.processCompression");
  if (phase === "agentic") return t("chat.processAgentic");
  if (phase === "generate") return t("chat.processGenerate");
  return t("chat.processComplete");
}

function getLiveProcessStatusText(status: ProgressEvent["status"]): string {
  if (status === "completed") return t("chat.processStepCompleted");
  if (status === "skipped") return t("chat.processStepSkipped");
  if (status === "failed") return t("chat.processStepFailed");
  return t("chat.processStepRunning");
}

function formatLiveProcessElapsed(elapsedMs: number): string {
  if (elapsedMs >= 1000) {
    return `${(elapsedMs / 1000).toFixed(1)} s`;
  }
  return `${Math.round(elapsedMs)} ms`;
}

function formatChatModeLabel(mode?: ChatMode): string {
  if (mode === "fast") return t("chat.chatModeFast");
  if (mode === "expert") return t("chat.chatModeExpert");
  if (mode === "default") return t("chat.chatModeDefault");
  return "";
}

function formatScalarValue(value: unknown): string {
  if (value === undefined || value === null) {
    return "";
  }
  if (typeof value === "string") {
    return value.trim();
  }
  return String(value);
}

function setChatMode(mode: string | number | object) {
  if (mode === "fast" || mode === "default" || mode === "expert") {
    selectedChatMode.value = mode;
  }
}

function applyExecutionHint(mode: ExecutionHint | "auto") {
  selectedExecutionHint.value = mode;
}

function setExecutionHint(mode: string | number | object) {
  if (
    mode === "auto"
    || mode === "multimodal_rag"
    || mode === "direct_llm"
    || mode === "image_similarity"
    || mode === "image_grounded_answer"
    || mode === "uploaded_image_qa"
    || mode === "save_uploaded_image"
  ) {
    applyExecutionHint(mode);
  }
}

function applyQuestionTemplate(template: QuestionTemplate) {
  query.value = template.prompt;
  if (isDefaultChatMode.value) {
    selectedExecutionHint.value = template.executionHint ?? "auto";
  }
  focusComposer();
}

type SendChatOptions = {
  userQuery: string;
  requestImage: File | null;
  requestChatMode: ChatMode;
  requestExecutionHint?: ExecutionHint;
  requestSourceScope?: { doc_ids?: string[]; image_ids?: string[] } | null;
  assistantPromptLabel?: string;
};

async function sendChat(options: SendChatOptions) {
  const normalizedQuery = options.userQuery.trim();
  if (!normalizedQuery && !options.requestImage) {
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

  const sentImageUrl = options.requestImage ? trackObjectUrl(URL.createObjectURL(options.requestImage)) : "";
  clearCitationHighlight();
  const userMessage: Message = {
    id: Date.now().toString(),
    session_id: sessionId,
    role: "user",
    content: normalizedQuery,
    chat_mode: options.requestChatMode,
    created_at: new Date().toISOString(),
    has_image: Boolean(options.requestImage),
    local_image_url: sentImageUrl || undefined,
    sources: [],
    citations: [],
    retrieval_params: null,
  };

  messages.value.push(userMessage);
  currentSessionTitle.value = getSessionDisplayTitle(sessionId, currentSessionTitle.value);
  saveSessionDraft(sessionId);
  const assistantMessageId = (Date.now() + 1).toString();
  const assistantMessage: Message = {
    id: assistantMessageId,
    session_id: sessionId,
    role: "assistant",
    content: "",
    chat_mode: options.requestChatMode,
    created_at: new Date().toISOString(),
    has_image: false,
    sources: [],
    citations: [],
    retrieval_steps: [],
    retrieval_params: null,
    timings: null,
    live_progress: null,
    live_progress_steps: [],
    live_progress_started_at: null,
    live_progress_active_phase: null,
    live_progress_done: false,
  };
  let effectiveSessionId = sessionId;
  let streamCompleted = false;
  query.value = "";

  await nextTick();
  scrollToBottom();

  try {
    pendingSessions.value = {
      ...pendingSessions.value,
      [sessionId]: true,
    };
    messages.value.push(assistantMessage);
    syncFeedbackForm(assistantMessage);
    saveSessionDraft(sessionId);
    streamingId.value = assistantMessageId;

    const appendAssistantContent = (targetSessionId: string, chunk: string) => {
      if (!chunk) return;
      if (currentSessionId.value === targetSessionId) {
        const target = messages.value.find((message) => String(message.id) === assistantMessageId);
        if (target) {
          target.content += chunk;
        }
      } else {
        updateDraftMessage(targetSessionId, assistantMessageId, (message) => {
          message.content += chunk;
        });
      }
      scheduleScrollToBottom();
    };

    const finalizeAssistantMessage = (targetSessionId: string, payload: {
      assistant_message_id?: number;
      sources: Message["sources"];
      citations?: Message["citations"];
      presentation_mode?: Message["presentation_mode"];
      execution_mode?: Message["execution_mode"];
      use_rag?: Message["use_rag"];
      retrieval_steps?: Message["retrieval_steps"];
      timings?: Message["timings"];
      chat_mode?: Message["chat_mode"];
    }) => {
      const assignPayload = (message: Message) => {
        if (payload.assistant_message_id) {
          message.id = payload.assistant_message_id;
        }
        message.session_id = targetSessionId;
        message.chat_mode = payload.chat_mode;
        message.sources = payload.sources || [];
        message.citations = payload.citations || [];
        message.presentation_mode = payload.presentation_mode;
        message.execution_mode = payload.execution_mode;
        message.use_rag = payload.use_rag;
        message.retrieval_steps = payload.retrieval_steps || [];
        message.retrieval_params = {
          presentation_mode: payload.presentation_mode,
          execution_mode: payload.execution_mode,
          use_rag: payload.use_rag,
          top_k: chatTopK.value,
          enable_score_filter: chatEnableScoreFilter.value,
          min_relevance_score: chatMinRelevanceScore.value,
          chat_mode: payload.chat_mode || options.requestChatMode,
          execution_hint: options.requestExecutionHint,
          source_scope: options.requestSourceScope,
          citations: payload.citations || [],
          timings: payload.timings || null,
        };
        message.timings = payload.timings || null;
        message.live_progress = null;
        message.live_progress_steps = [];
        message.live_progress_started_at = null;
        message.live_progress_active_phase = null;
        message.live_progress_done = true;
      };

      if (currentSessionId.value === targetSessionId) {
        const target = messages.value.find((message) => String(message.id) === assistantMessageId);
        if (target) {
          assignPayload(target);
          saveSessionDraft(targetSessionId);
        }
      } else {
        updateDraftMessage(targetSessionId, assistantMessageId, assignPayload);
      }
    };

    await ragChatStream(
      {
        query: normalizedQuery,
        sessionId,
        chatMode: options.requestChatMode,
        topK: chatTopK.value,
        enableScoreFilter: chatEnableScoreFilter.value,
        minRelevanceScore: chatMinRelevanceScore.value,
        executionHint: options.requestExecutionHint,
        sourceScope: options.requestSourceScope,
        image: options.requestImage,
      },
      {
        onSession: (event) => {
          effectiveSessionId = event.session_id || sessionId;
          if (effectiveSessionId !== sessionId) {
            renamePendingSessionKey(sessionId, effectiveSessionId);
            moveSessionDraft(sessionId, effectiveSessionId);
          }
          assistantMessage.session_id = effectiveSessionId;
          if (currentSessionId.value === sessionId || !currentSessionId.value) {
            currentSessionId.value = effectiveSessionId;
          }
          saveSessionDraft(effectiveSessionId);
        },
        onProgress: (event) => {
          updateLiveAssistantProgress(effectiveSessionId, assistantMessageId, event);
        },
        onContent: (event) => {
          appendAssistantContent(effectiveSessionId, event.content);
        },
        onResults: (event) => {
          finalizeAssistantMessage(effectiveSessionId, {
            assistant_message_id: event.assistant_message_id,
            sources: event.sources || [],
            citations: event.citations || [],
            chat_mode: event.chat_mode,
            presentation_mode: event.presentation_mode,
            execution_mode: event.execution_mode,
            use_rag: event.use_rag,
            retrieval_steps: event.retrieval_steps || [],
            timings: event.timings || null,
          });
        },
        onDone: () => {
          streamCompleted = true;
        },
        onError: (event) => {
          console.error("RAG 流式响应错误事件:", event);
          throw new Error(event.detail || "流式响应失败");
        },
      },
    );

    const userMsgCount = messages.value.filter((m) => m.role === "user").length;
    if (userMsgCount === 1) {
      const title = generateSessionTitle(normalizedQuery || options.assistantPromptLabel || t("chat.newSession"));
      await updateSessionTitle(effectiveSessionId, title);
      currentSessionTitle.value = title;
      saveSessionDraft(effectiveSessionId);
    }

    await nextTick();
    scrollToBottom();
  } catch (e) {
    console.error("RAG 问答失败:", e);
    const activeAssistant = messages.value.find((message) => String(message.id) === assistantMessageId);
    const hasPartialContent = Boolean(activeAssistant && String(activeAssistant.content || "").trim());
    if (activeAssistant && !hasPartialContent) {
      messages.value = messages.value.filter((message) => String(message.id) !== assistantMessageId);
      removeDraftMessage(effectiveSessionId, assistantMessageId);
    } else if (effectiveSessionId && currentSessionId.value === effectiveSessionId) {
      saveSessionDraft(effectiveSessionId);
    }
    ElMessage.error(t("chat.chatFailed"));
  } finally {
    const pendingKey = effectiveSessionId || sessionId;
    const { [pendingKey]: _completed, [sessionId]: _legacyCompleted, ...restPending } = pendingSessions.value;
    pendingSessions.value = restPending;
    if (streamCompleted || streamingId.value === assistantMessageId) {
      streamingId.value = "";
    }
    if (options.requestImage === attachedImage.value) {
      removeAttached();
    }
  }
}

async function doChat() {
  await sendChat({
    userQuery: query.value,
    requestImage: attachedImage.value,
    requestChatMode: selectedChatMode.value,
    requestExecutionHint: effectiveExecutionHint.value,
    requestSourceScope: sourceScope.value,
  });
}

function toggleFeedbackPopover(message: Message) {
  const targetId = String(message.id);
  if (feedbackPopoverId.value === targetId) {
    feedbackPopoverId.value = null;
    return;
  }
  syncFeedbackForm(message);
  feedbackPopoverId.value = targetId;
}

async function submitHelpfulFeedback(message: Message) {
  const messageId = String(message.id);
  try {
    feedbackSubmittingId.value = messageId;
    const response = await submitMessageFeedback(message.id, {
      rating: "up",
      issue_types: [],
      comment: null,
    });
    applyMessageFeedback(message.id, message.session_id, response);
    feedbackPopoverId.value = null;
    ElMessage.success(t("chat.feedbackSuccess"));
  } catch (error) {
    console.error("提交正向反馈失败:", error);
    ElMessage.error(t("chat.feedbackFailed"));
  } finally {
    feedbackSubmittingId.value = null;
  }
}

async function submitIssueFeedback(message: Message) {
  const messageId = String(message.id);
  const form = getFeedbackForm(messageId);
  try {
    feedbackSubmittingId.value = messageId;
    const response = await submitMessageFeedback(message.id, {
      rating: "down",
      issue_types: [...form.issue_types],
      comment: form.comment || null,
    });
    applyMessageFeedback(message.id, message.session_id, response);
    feedbackPopoverId.value = null;
    ElMessage.success(t("chat.feedbackSuccess"));
  } catch (error) {
    console.error("提交问题反馈失败:", error);
    ElMessage.error(t("chat.feedbackFailed"));
  } finally {
    feedbackSubmittingId.value = null;
  }
}

function scrollToBottom() {
  messagesEndRef.value?.scrollIntoView({ block: "end" });
}

function scheduleScrollToBottom() {
  if (scrollToBottomRaf) return;
  scrollToBottomRaf = window.requestAnimationFrame(() => {
    scrollToBottomRaf = 0;
    scrollToBottom();
  });
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

function canUseAssistantFollowup(msg: Message): boolean {
  return msg.role === "assistant" && msg.execution_mode !== "save_uploaded_image" && !isCurrentSessionPending.value;
}

function canRetryAssistantMessage(msg: Message): boolean {
  return canUseAssistantFollowup(msg) && !Boolean(msg.retrieval_params?.has_image);
}

function getAssistantSourceScope(msg: Message) {
  return (msg.retrieval_params?.source_scope as { doc_ids?: string[]; image_ids?: string[] } | null) || null;
}

function getAssistantExecutionHint(msg: Message): ExecutionHint | undefined {
  const hint = msg.retrieval_params?.execution_hint as ExecutionHint | undefined;
  if (hint) return hint;
  if (msg.execution_mode && msg.execution_mode !== "save_uploaded_image") {
    return msg.execution_mode;
  }
  return undefined;
}

function getAssistantChatMode(msg: Message): ChatMode {
  const mode = msg.chat_mode || msg.retrieval_params?.chat_mode;
  if (mode === "fast" || mode === "expert") {
    return mode;
  }
  return "default";
}

async function rerunAssistantMessage(msg: Message, index: number) {
  const sourceMessage = getRelatedUserMessage(index);
  const text = String(sourceMessage?.content || "").trim();
  if (!text) {
    ElMessage.warning(t("chat.resendUnavailable"));
    return;
  }
  await sendChat({
    userQuery: text,
    requestImage: null,
    requestChatMode: getAssistantChatMode(msg),
    requestExecutionHint: getAssistantExecutionHint(msg),
    requestSourceScope: getAssistantSourceScope(msg),
    assistantPromptLabel: t("chat.retryAnswer"),
  });
}

async function expandAssistantMessage(msg: Message) {
  await sendChat({
    userQuery: `${t("chat.expandPromptPrefix")}\n\n${msg.content}`,
    requestImage: null,
    requestChatMode: getAssistantChatMode(msg),
    requestExecutionHint: getAssistantExecutionHint(msg),
    requestSourceScope: getAssistantSourceScope(msg),
    assistantPromptLabel: t("chat.expandAnswer"),
  });
}

async function summarizeAssistantMessage(msg: Message) {
  await sendChat({
    userQuery: `${t("chat.summarizePromptPrefix")}\n\n${msg.content}`,
    requestImage: null,
    requestChatMode: getAssistantChatMode(msg),
    requestExecutionHint: getAssistantExecutionHint(msg),
    requestSourceScope: getAssistantSourceScope(msg),
    assistantPromptLabel: t("chat.summarizeAnswer"),
  });
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
  liveProcessTimer = window.setInterval(() => {
    liveProcessNow.value = Date.now();
  }, 250);
  await loadChatDefaults();
  await loadSessions();
  if (!currentSessionId.value && sessions.value.length > 0) {
    currentSessionId.value = sessions.value[0].id;
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updateViewportState);
  if (liveProcessTimer) {
    window.clearInterval(liveProcessTimer);
    liveProcessTimer = 0;
  }
  if (scrollToBottomRaf) {
    window.cancelAnimationFrame(scrollToBottomRaf);
    scrollToBottomRaf = 0;
  }
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
  background: var(--chat-canvas);
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
  background: var(--chat-user-bubble);
  color: var(--text-primary);
  border-color: rgba(37, 99, 235, 0.14);
  border-bottom-right-radius: 6px;
}

.message-item.assistant .message-bubble {
  background: var(--chat-assistant-bubble);
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

.assistant-markdown {
  margin: 0;
}

.message-notice {
  margin-top: 12px;
}

.live-process-wrap {
  margin: 2px 0 10px;
}

.live-process-text {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  color: rgba(15, 23, 42, 0.36);
  font-size: 12px;
  line-height: 1.45;
  text-align: left;
}

.live-process-text.expanded {
  margin-bottom: 8px;
}

.live-process-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.68);
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.08);
  animation: live-process-pulse 1.25s ease-in-out infinite;
}

.live-process-text-main {
  color: rgba(15, 23, 42, 0.46);
  font-weight: 500;
}

.live-process-ellipsis {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  min-width: 18px;
}

.live-process-ellipsis span {
  width: 3px;
  height: 3px;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.68);
  animation: live-process-dot-wave 1.2s ease-in-out infinite;
}

.live-process-ellipsis span:nth-child(2) {
  animation-delay: 0.15s;
}

.live-process-ellipsis span:nth-child(3) {
  animation-delay: 0.3s;
}

.live-process-text-sub {
  color: rgba(100, 116, 139, 0.74);
}

.live-process-toggle {
  color: rgba(100, 116, 139, 0.58);
  transition: color 0.18s ease;
}

.live-process-text:hover .live-process-toggle,
.live-process-text:hover .live-process-text-main {
  color: rgba(15, 23, 42, 0.56);
}

.live-process-details {
  padding-left: 15px;
  border-left: 1px solid rgba(148, 163, 184, 0.18);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.live-process-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.live-process-section-title {
  color: rgba(100, 116, 139, 0.72);
  font-size: 11px;
  line-height: 1.4;
}

.live-process-current-line,
.live-process-completed-item,
.live-process-meta-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.live-process-current-name,
.live-process-completed-name,
.live-process-meta-label {
  color: rgba(15, 23, 42, 0.48);
  font-size: 12px;
  line-height: 1.5;
}

.live-process-current-status,
.live-process-completed-time,
.live-process-meta-value {
  color: rgba(100, 116, 139, 0.78);
  font-size: 12px;
  line-height: 1.5;
}

.live-process-current-summary,
.live-process-completed-summary,
.live-process-empty {
  color: rgba(71, 85, 105, 0.72);
  font-size: 12px;
  line-height: 1.55;
}

.live-process-completed-list,
.live-process-meta-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

@keyframes live-process-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.12);
    opacity: 0.7;
  }
}

@keyframes live-process-dot-wave {
  0%, 100% {
    transform: translateY(0);
    opacity: 0.5;
  }
  50% {
    transform: translateY(-1px);
    opacity: 1;
  }
}

.user-attachment-card {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 10px;
  border-radius: 14px;
  background: var(--surface-panel-muted);
  border: 1px solid rgba(37, 99, 235, 0.1);
  max-width: min(100%, 280px);
}

.user-attachment-card.has-preview {
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 8px;
  background: var(--surface-panel-muted);
}

.user-attachment-preview {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  max-height: 220px;
  padding: 0;
  overflow: hidden;
  border: 1px solid rgba(37, 99, 235, 0.14);
  border-radius: 14px;
  background: var(--surface-panel-muted);
  cursor: zoom-in;
}

.user-attachment-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.user-attachment-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding: 0 2px 2px;
}

.user-attachment-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.user-attachment-hint {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.sources-heading-button {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.sources-heading-meta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: rgba(37, 99, 235, 0.8);
  font-size: 11px;
  line-height: 1;
}

.sources-heading-toggle {
  margin-left: auto;
  color: rgba(100, 116, 139, 0.72);
  font-size: 12px;
}

.source-card-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.source-card-list.collapsed {
  gap: 0;
}

.source-card-list.prominent {
  gap: 12px;
}

.source-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: var(--surface-card-muted);
}

.source-card.clickable {
  cursor: pointer;
}

.source-card.active {
  border-color: rgba(14, 165, 233, 0.34);
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.16);
  background: var(--surface-active);
}

.source-card-main {
  display: flex;
  gap: 12px;
  min-width: 0;
}

.source-card-visual {
  width: 96px;
  min-width: 96px;
  height: 96px;
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: var(--surface-panel-muted);
  cursor: pointer;
}

.source-card-visual img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.source-card-copy {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.source-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.source-card-head-badges {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.source-card-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.45;
  word-break: break-word;
}

.source-card-badge {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-primary);
  background: rgba(37, 99, 235, 0.1);
  white-space: nowrap;
}

.source-card-refcount {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #075985;
  background: rgba(14, 165, 233, 0.12);
}

.source-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  font-size: 11px;
  color: var(--text-secondary);
}

.source-card-summary {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-secondary);
  word-break: break-word;
}

.source-card-actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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

.composer-warning-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.composer-warning {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--surface-panel-muted);
  border: 1px solid rgba(148, 163, 184, 0.16);
  color: var(--text-secondary);
  font-size: 12px;
}

.question-template-bar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
}

.question-template-chip {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
  padding: 10px 14px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: var(--surface-card-muted);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.question-template-chip:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.24);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.question-template-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.question-template-desc {
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-secondary);
}

.composer-main {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.compact-template-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.compact-template-chip {
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: var(--surface-control);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.input-actions {
  display: flex;
  align-items: flex-start;
  flex: 0 0 auto;
}

.input-actions :deep(.el-upload) {
  display: flex;
}

.composer-tools {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 0;
  padding: 8px 10px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: var(--surface-panel-muted);
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
  background: var(--surface-card);
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
  width: 34px;
  height: 34px;
  border-radius: 12px;
  background: var(--surface-control);
  border: 1px solid var(--border-color);
}

.attach-btn:hover {
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
}

.source-popover-anchor {
  display: inline-block;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.chat-input-shell {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.chat-input-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 12px 12px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: var(--surface-card);
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
}

.chat-input {
  flex: 1;
}

.chat-input :deep(.el-input__wrapper) {
  min-height: 42px;
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 0;
  border-radius: 0;
}

.chat-input :deep(.el-input__wrapper:focus-within) {
  border-color: transparent;
  box-shadow: none;
}

.chat-input.slash-active :deep(.el-input__wrapper) {
  background: transparent;
}

.chat-input.slash-invalid :deep(.el-input__wrapper) {
  background: transparent;
}

.chat-input :deep(textarea.el-textarea__inner) {
  min-height: 28px;
  line-height: 1.68;
  color: var(--text-primary);
  padding: 0;
}

.composer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 2px;
}

.composer-toolbar-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.composer-toolbar-group.align-right {
  margin-left: auto;
}

.composer-toolbar-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: var(--surface-control);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.18s ease, color 0.18s ease, background-color 0.18s ease, box-shadow 0.18s ease;
}

.composer-toolbar-chip:hover {
  border-color: rgba(37, 99, 235, 0.24);
  color: var(--accent-primary);
  background: rgba(239, 246, 255, 0.94);
}

.composer-toolbar-chip.primary {
  background: rgba(37, 99, 235, 0.08);
  color: var(--accent-primary);
  border-color: rgba(37, 99, 235, 0.18);
}

.composer-toolbar-chip.subtle {
  color: var(--text-tertiary);
}

.composer-toolbar-chip.subtle.active,
.composer-toolbar-chip.subtle:hover {
  color: var(--accent-primary);
  background: rgba(239, 246, 255, 0.9);
}

.composer-toolbar-chip :deep(.el-icon),
.composer-toolbar-chip i {
  font-size: 13px;
}

.send-btn {
  width: 34px;
  min-width: 34px;
  height: 34px;
  min-height: 34px;
  padding: 0;
  border-radius: 12px;
  background: var(--accent-gradient);
  border: none;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.16);
}

.send-btn:hover {
  opacity: 0.95;
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
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
  padding: 8px 10px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: var(--surface-panel-muted);
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

.message-action-btn.active {
  color: var(--accent-primary);
  background: rgba(37, 99, 235, 0.12);
  border-color: rgba(37, 99, 235, 0.18);
}

.message-action-btn.compact {
  padding: 4px 10px;
  background: var(--surface-control);
  border-color: rgba(148, 163, 184, 0.18);
  font-size: 12px;
}

.feedback-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.feedback-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.feedback-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.feedback-checks {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.feedback-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
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

  .source-card-main {
    flex-direction: column;
  }

  .source-card-visual {
    width: 100%;
    min-width: 0;
    height: 180px;
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
    flex-wrap: wrap;
  }

  .input-actions {
    width: 100%;
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

  .user-attachment-card {
    max-width: 100%;
  }

  .message-footer {
    flex-direction: column;
    align-items: flex-start;
  }

  .composer-status-bar,
  .source-card-actions-row {
    width: 100%;
  }

  .composer-toolbar,
  .composer-toolbar-group,
  .composer-toolbar-group.align-right {
    width: 100%;
    margin-left: 0;
  }

  .composer-toolbar-group.align-right {
    justify-content: flex-start;
  }

  .compact-template-row {
    width: 100%;
    flex-wrap: wrap;
  }

  .composer-toolbar-chip,
  .question-template-chip,
  .chat-input-shell {
    width: 100%;
  }

  .question-template-bar {
    grid-template-columns: 1fr;
  }

  .page-subtitle {
    display: none;
  }
}
</style>
