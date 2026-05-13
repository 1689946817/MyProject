/**
 * 聊天 Markdown 渲染工具模块
 *
 * 将 Markdown 文本渲染为安全的 HTML，支持代码高亮、任务列表、表格、
 * 复制代码按钮等功能，并通过 DOMPurify 进行 XSS 防护。
 */
import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";

/** 渲染选项 */
type RenderOptions = {
  /** 复制代码按钮的显示文本（如 "复制"） */
  copyCodeLabel: string;
};

/** 聊天 Markdown 块（用于流式渲染时的分块输出） */
export type ChatMarkdownBlock = {
  /** 块唯一键（如 "p-0"） */
  key: string;
  /** 块序号 */
  index: number;
  /** 块的原始 Markdown 文本 */
  raw: string;
};

/** 渲染结果 LRU 缓存 */
const renderCache = new Map<string, string>();
/** 缓存最大容量 */
const MAX_CACHE_SIZE = 120;
/** MarkdownIt 工具方法（用于 HTML 转义等） */
const markdownUtils = new MarkdownIt().utils;

/**
 * 转义 HTML 属性值中的特殊字符
 * @param value 原始字符串
 * @returns 转义后的安全字符串
 */
function escapeHtmlAttribute(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * 将字符串编码为 Base64（使用 UTF-8 编码）
 * @param value 原始字符串
 * @returns Base64 编码字符串
 */
function encodeBase64(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

/**
 * 将 Base64 字符串解码为字符串（使用 UTF-8 解码）
 * @param value Base64 编码字符串
 * @returns 解码后的原始字符串
 */
function decodeBase64(value: string): string {
  const binary = atob(value);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/**
 * 渲染代码块为 HTML（含语法高亮和复制按钮）
 * @param code 代码文本
 * @param language 编程语言标识
 * @param copyCodeLabel 复制按钮显示文本
 * @returns 代码块 HTML 字符串
 */
function renderCodeBlock(code: string, language: string, copyCodeLabel: string): string {
  const normalizedLanguage = language && hljs.getLanguage(language) ? language : "text";
  const highlighted = normalizedLanguage !== "text"
    ? hljs.highlight(code, { language: normalizedLanguage, ignoreIllegals: true }).value
    : markdownUtils.escapeHtml(code);

  return `
    <div class="chat-code-block" data-language="${escapeHtmlAttribute(normalizedLanguage)}">
      <div class="chat-code-toolbar">
        <span class="chat-code-language">${escapeHtmlAttribute(normalizedLanguage)}</span>
        <button
          type="button"
          class="chat-code-copy"
          aria-label="${escapeHtmlAttribute(copyCodeLabel)}"
          data-copy-content="${escapeHtmlAttribute(encodeBase64(code))}"
        >
          ${escapeHtmlAttribute(copyCodeLabel)}
        </button>
      </div>
      <pre class="chat-code-pre"><code class="hljs language-${escapeHtmlAttribute(normalizedLanguage)}">${highlighted}</code></pre>
    </div>
  `.trim();
}

/**
 * 创建配置好的 MarkdownIt 解析器实例
 *
 * 禁用原始 HTML、启用换行转换和自动链接，并自定义链接渲染（新窗口打开 + 安全属性）。
 * @param copyCodeLabel 复制代码按钮文本
 * @returns MarkdownIt 实例
 */
function createMarkdownParser(copyCodeLabel: string): MarkdownIt {
  const markdown = new MarkdownIt({
    html: false,
    breaks: true,
    linkify: true,
    highlight: (code, language) => renderCodeBlock(code, language, copyCodeLabel),
  });

  const defaultLinkOpen: NonNullable<typeof markdown.renderer.rules.link_open> = markdown.renderer.rules.link_open
    ?? ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));

  markdown.renderer.rules.link_open = (...args) => {
    const [tokens, idx, options, env, self] = args;
    const token = tokens[idx];
    token.attrSet("target", "_blank");
    token.attrSet("rel", "noopener noreferrer nofollow");
    return defaultLinkOpen(tokens, idx, options, env, self);
  };

  return markdown;
}

/**
 * 为容器内的所有表格添加横向滚动包裹层
 * @param container DOM 容器元素
 */
function wrapTables(container: HTMLElement) {
  container.querySelectorAll("table").forEach((table) => {
    if (table.parentElement?.classList.contains("chat-table-wrap")) {
      return;
    }
    const wrapper = document.createElement("div");
    wrapper.className = "chat-table-wrap";
    table.parentNode?.insertBefore(wrapper, table);
    wrapper.appendChild(table);
  });
}

/**
 * 增强任务列表：将 [ ] / [x] 语法转换为带复选框的列表项
 * @param container DOM 容器元素
 */
function enhanceTaskLists(container: HTMLElement) {
  container.querySelectorAll("li").forEach((item) => {
    const contentRoot = item.firstElementChild?.tagName === "P"
      ? item.firstElementChild as HTMLElement
      : item;
    const firstNode = contentRoot.firstChild;
    if (!firstNode || firstNode.nodeType !== Node.TEXT_NODE) {
      return;
    }
    const source = firstNode.textContent || "";
    const match = source.match(/^\s*\[([ xX])\]\s+/);
    if (!match) {
      return;
    }

    firstNode.textContent = source.slice(match[0].length);
    item.classList.add("task-list-item");
    item.parentElement?.classList.add("task-list");

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.disabled = true;
    checkbox.checked = match[1].toLowerCase() === "x";
    checkbox.className = "task-list-checkbox";
    contentRoot.insertBefore(checkbox, contentRoot.firstChild);
  });
}

/**
 * 规范化链接：移除 javascript: 协议，添加新窗口打开和安全属性
 * @param container DOM 容器元素
 */
function normalizeLinks(container: HTMLElement) {
  container.querySelectorAll("a[href]").forEach((link) => {
    const href = (link.getAttribute("href") || "").trim();
    if (/^javascript:/i.test(href)) {
      link.removeAttribute("href");
      return;
    }
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer nofollow");
  });
}

/**
 * 对渲染后的 HTML 进行后处理（包裹表格、增强任务列表、规范化链接）
 * @param html 原始 HTML 字符串
 * @returns 后处理后的 HTML 字符串
 */
function postProcessRenderedHtml(html: string): string {
  const container = document.createElement("div");
  container.innerHTML = html;
  wrapTables(container);
  enhanceTaskLists(container);
  normalizeLinks(container);
  return container.innerHTML;
}

/**
 * 使用 DOMPurify 净化 HTML，仅保留安全的标签和属性
 * @param html 待净化的 HTML 字符串
 * @returns 净化后的安全 HTML
 */
function sanitizeRenderedHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "a",
      "blockquote",
      "br",
      "button",
      "code",
      "del",
      "div",
      "em",
      "h1",
      "h2",
      "h3",
      "h4",
      "hr",
      "input",
      "li",
      "ol",
      "p",
      "pre",
      "span",
      "strong",
      "table",
      "tbody",
      "td",
      "th",
      "thead",
      "tr",
      "ul",
    ],
    ALLOWED_ATTR: [
      "aria-label",
      "checked",
      "class",
      "data-copy-content",
      "data-language",
      "disabled",
      "href",
      "rel",
      "target",
      "type",
    ],
    FORBID_TAGS: ["iframe", "script", "style"],
    FORBID_ATTR: ["onerror", "onload", "onclick", "style"],
  });
}

/** 代码围栏（``` 或 ~~~）的匹配正则 */
const fencePattern = /^\s*(```|~~~)/;

/**
 * 将 Markdown 内容按空行分块（代码围栏内的空行不分割）
 *
 * 用于流式渲染时将回答分段，每段独立渲染和插入 DOM。
 * @param content 原始 Markdown 文本
 * @returns 分块列表，每块包含原始 Markdown 和序号
 */
export function splitChatMarkdownBlocks(content: string): ChatMarkdownBlock[] {
  const normalizedContent = String(content || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");
  if (!normalizedContent.trim()) {
    return [];
  }

  const blocks: string[] = [];
  let current: string[] = [];
  let inFence = false;

  normalizedContent.split("\n").forEach((line) => {
    if (fencePattern.test(line)) {
      current.push(line);
      inFence = !inFence;
      return;
    }

    if (!inFence && !line.trim()) {
      if (current.some((item) => item.trim())) {
        blocks.push(current.join("\n").trim());
        current = [];
      }
      return;
    }

    current.push(line);
  });

  if (current.some((item) => item.trim())) {
    blocks.push(current.join("\n").trim());
  }

  return blocks.map((raw, index) => ({
    key: `p-${index}`,
    index,
    raw,
  }));
}

/**
 * 将 Markdown 内容渲染为安全的 HTML（带缓存）
 *
 * 流程：规范化 → 解析 Markdown → 后处理 → 净化 → 缓存。
 * @param content 原始 Markdown 文本
 * @param options 渲染选项（复制按钮文本）
 * @returns 安全的 HTML 字符串
 */
export function renderChatMarkdown(content: string, options: RenderOptions): string {
  const normalizedContent = String(content || "")
    .replace(/<br\s*\/?>/gi, "\n");
  if (!normalizedContent.trim()) {
    return "";
  }

  const cacheKey = `${options.copyCodeLabel}::${normalizedContent}`;
  const cached = renderCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  const parser = createMarkdownParser(options.copyCodeLabel);
  const rendered = parser.render(normalizedContent);
  const enhanced = postProcessRenderedHtml(rendered);
  const sanitized = sanitizeRenderedHtml(enhanced);

  if (renderCache.size >= MAX_CACHE_SIZE) {
    const oldestKey = renderCache.keys().next().value;
    if (oldestKey) {
      renderCache.delete(oldestKey);
    }
  }
  renderCache.set(cacheKey, sanitized);
  return sanitized;
}

/**
 * 解码复制按钮中的 Base64 编码代码
 * @param encoded Base64 编码的代码字符串
 * @returns 解码后的原始代码
 */
export function decodeCopiedCode(encoded: string): string {
  return decodeBase64(encoded);
}
