import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";

type RenderOptions = {
  copyCodeLabel: string;
};

const renderCache = new Map<string, string>();
const MAX_CACHE_SIZE = 120;
const markdownUtils = new MarkdownIt().utils;

function escapeHtmlAttribute(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function encodeBase64(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

function decodeBase64(value: string): string {
  const binary = atob(value);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

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

function postProcessRenderedHtml(html: string): string {
  const container = document.createElement("div");
  container.innerHTML = html;
  wrapTables(container);
  enhanceTaskLists(container);
  normalizeLinks(container);
  return container.innerHTML;
}

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

export function renderChatMarkdown(content: string, options: RenderOptions): string {
  const normalizedContent = String(content || "");
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

export function decodeCopiedCode(encoded: string): string {
  return decodeBase64(encoded);
}
