<template>
  <div
    class="chat-markdown"
    :class="{ typing: streaming }"
    v-html="renderedHtml"
    @click="handleMarkdownClick"
  ></div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import "highlight.js/styles/github-dark.css";

import { decodeCopiedCode, renderChatMarkdown } from "@/utils/chatMarkdown";

const props = defineProps<{
  content: string;
  streaming?: boolean;
}>();

const { t } = useI18n();

const renderedHtml = computed(() => renderChatMarkdown(props.content, {
  copyCodeLabel: t("chat.copyCode"),
}));

async function copyCode(text: string) {
  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

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

async function handleMarkdownClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null;
  const copyButton = target?.closest(".chat-code-copy") as HTMLElement | null;
  if (!copyButton) {
    return;
  }

  const encoded = copyButton.getAttribute("data-copy-content") || "";
  if (!encoded) {
    return;
  }

  try {
    await copyCode(decodeCopiedCode(encoded));
    ElMessage.success(t("chat.copyCodeSuccess"));
  } catch (error) {
    console.error("复制代码块失败:", error);
    ElMessage.error(t("chat.copyCodeFailed"));
  }
}
</script>

<style scoped>
.chat-markdown {
  color: rgba(15, 23, 42, 0.92);
  font-size: 14px;
  line-height: 1.8;
  letter-spacing: 0.01em;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.chat-markdown :deep(p),
.chat-markdown :deep(ul),
.chat-markdown :deep(ol),
.chat-markdown :deep(blockquote),
.chat-markdown :deep(pre),
.chat-markdown :deep(.chat-code-block),
.chat-markdown :deep(.chat-table-wrap),
.chat-markdown :deep(hr) {
  margin: 0 0 12px;
}

.chat-markdown :deep(*:last-child) {
  margin-bottom: 0;
}

.chat-markdown :deep(h1),
.chat-markdown :deep(h2),
.chat-markdown :deep(h3),
.chat-markdown :deep(h4) {
  margin: 18px 0 10px;
  color: #0f172a;
  font-weight: 700;
  line-height: 1.35;
}

.chat-markdown :deep(h1) {
  font-size: 1.3rem;
}

.chat-markdown :deep(h2) {
  font-size: 1.18rem;
}

.chat-markdown :deep(h3) {
  font-size: 1.06rem;
}

.chat-markdown :deep(h4) {
  font-size: 0.98rem;
}

.chat-markdown :deep(ul),
.chat-markdown :deep(ol) {
  padding-left: 1.35rem;
}

.chat-markdown :deep(li + li) {
  margin-top: 6px;
}

.chat-markdown :deep(blockquote) {
  padding: 10px 14px;
  border-left: 3px solid rgba(14, 116, 144, 0.35);
  background: rgba(240, 249, 255, 0.9);
  color: rgba(15, 23, 42, 0.86);
  border-radius: 10px;
}

.chat-markdown :deep(code:not(.hljs)) {
  padding: 0.14rem 0.36rem;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.08);
  color: #0f172a;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 0.92em;
}

.chat-markdown :deep(.chat-code-block) {
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.26);
  border-radius: 14px;
  background: #0f172a;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.chat-markdown :deep(.chat-code-toolbar) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: linear-gradient(180deg, rgba(30, 41, 59, 0.98), rgba(15, 23, 42, 0.96));
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.chat-markdown :deep(.chat-code-language) {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(226, 232, 240, 0.72);
}

.chat-markdown :deep(.chat-code-copy) {
  border: 0;
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 12px;
  color: #f8fafc;
  background: rgba(148, 163, 184, 0.18);
  cursor: pointer;
  transition: background-color 0.18s ease, transform 0.18s ease;
}

.chat-markdown :deep(.chat-code-copy:hover) {
  background: rgba(125, 211, 252, 0.28);
}

.chat-markdown :deep(.chat-code-copy:active) {
  transform: translateY(1px);
}

.chat-markdown :deep(.chat-code-pre) {
  margin: 0;
  padding: 14px 16px 16px;
  overflow-x: auto;
  background: transparent;
}

.chat-markdown :deep(.chat-code-pre code) {
  display: block;
  min-width: max-content;
  font-size: 13px;
  line-height: 1.7;
  background: transparent;
}

.chat-markdown :deep(.chat-table-wrap) {
  overflow-x: auto;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.66);
}

.chat-markdown :deep(table) {
  width: 100%;
  min-width: 420px;
  border-collapse: collapse;
}

.chat-markdown :deep(th),
.chat-markdown :deep(td) {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  text-align: left;
  vertical-align: top;
}

.chat-markdown :deep(th) {
  background: rgba(241, 245, 249, 0.95);
  font-weight: 700;
  color: #0f172a;
}

.chat-markdown :deep(tr:last-child td) {
  border-bottom: 0;
}

.chat-markdown :deep(a) {
  color: #0369a1;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
}

.chat-markdown :deep(a:hover) {
  color: #075985;
}

.chat-markdown :deep(hr) {
  border: 0;
  border-top: 1px solid rgba(148, 163, 184, 0.3);
}

.chat-markdown :deep(.task-list) {
  padding-left: 0;
  list-style: none;
}

.chat-markdown :deep(.task-list-item) {
  list-style: none;
}

.chat-markdown :deep(.task-list-checkbox) {
  margin-right: 10px;
  vertical-align: middle;
}

.chat-markdown.typing::after {
  content: "|";
  animation: typing-cursor 0.8s ease-in-out infinite;
  color: var(--accent-primary);
}

@keyframes typing-cursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
