/**
 * 主题管理 Composable
 *
 * 提供深色/浅色主题切换功能，主题选择持久化到 localStorage。
 * 使用模块级单例模式，确保多个组件共享同一主题状态。
 */
import { ref, onMounted } from 'vue'

/** 主题类型：dark=深色模式, light=浅色模式 */
export type Theme = 'dark' | 'light'

/** localStorage 存储键名 */
const STORAGE_KEY = 'multimodal-rag-theme'

/** 当前是否为深色模式（响应式引用，跨组件共享） */
const isDark = ref(false)
/** 是否已完成初始化（防止重复读取 localStorage） */
let initialized = false

/**
 * 应用主题到 DOM 并持久化
 * @param theme 目标主题
 */
function applyTheme(theme: Theme) {
  isDark.value = theme === 'dark'
  if (theme === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
  localStorage.setItem(STORAGE_KEY, theme)
}

/**
 * 确保主题已初始化（惰性加载，首次调用时从 localStorage 读取）
 */
function ensureThemeInitialized() {
  if (initialized) return
  const saved = localStorage.getItem(STORAGE_KEY) as Theme | null
  applyTheme(saved || 'light')
  initialized = true
}

/**
 * 主题管理 Composable Hook
 *
 * @returns isDark - 当前是否为深色模式（响应式）
 * @returns setTheme - 设置指定主题
 * @returns toggleTheme - 切换深色/浅色模式
 */
export function useTheme() {
  /**
   * 设置指定主题
   * @param theme 目标主题
   */
  function setTheme(theme: Theme) {
    applyTheme(theme)
  }

  /** 切换深色/浅色模式 */
  function toggleTheme() {
    setTheme(isDark.value ? 'light' : 'dark')
  }

  // 初始化时读取 localStorage
  onMounted(() => {
    ensureThemeInitialized()
  })

  return {
    isDark,
    setTheme,
    toggleTheme
  }
}
