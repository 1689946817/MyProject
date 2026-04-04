/**
 * 主题管理 Hook
 *
 * 提供深色/浅色主题切换功能，持久化到 localStorage
 */
import { ref, onMounted } from 'vue'

export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'multimodal-rag-theme'

const isDark = ref(true)
let initialized = false

function applyTheme(theme: Theme) {
  isDark.value = theme === 'dark'
  if (theme === 'dark') {
    document.documentElement.classList.remove('light')
  } else {
    document.documentElement.classList.add('light')
  }
  localStorage.setItem(STORAGE_KEY, theme)
}

function ensureThemeInitialized() {
  if (initialized) return
  const saved = localStorage.getItem(STORAGE_KEY) as Theme | null
  applyTheme(saved || 'dark')
  initialized = true
}

export function useTheme() {
  function setTheme(theme: Theme) {
    applyTheme(theme)
  }

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
