/**
 * 主题管理 Hook
 *
 * 提供深色/浅色主题切换功能，持久化到 localStorage
 */
import { ref, watch, onMounted } from 'vue'

export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'multimodal-rag-theme'

const isDark = ref(true)

export function useTheme() {
  function setTheme(theme: Theme) {
    isDark.value = theme === 'dark'
    if (theme === 'dark') {
      document.documentElement.classList.remove('light')
    } else {
      document.documentElement.classList.add('light')
    }
    localStorage.setItem(STORAGE_KEY, theme)
  }

  function toggleTheme() {
    setTheme(isDark.value ? 'light' : 'dark')
  }

  // 初始化时读取 localStorage
  onMounted(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as Theme | null
    if (saved) {
      setTheme(saved)
    } else {
      // 默认深色模式
      setTheme('dark')
    }
  })

  return {
    isDark,
    setTheme,
    toggleTheme
  }
}
