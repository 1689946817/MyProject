/**
 * i18n 配置
 */
import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

const STORAGE_KEY = 'multimodal-rag-locale'

function getSavedLocale(): 'zh-CN' | 'en-US' {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'zh-CN' || saved === 'en-US') {
    return saved
  }
  return 'zh-CN'
}

export const i18n = createI18n({
  legacy: false,
  locale: getSavedLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS
  }
})

export function setLocale(locale: 'zh-CN' | 'en-US') {
  i18n.global.locale.value = locale
  localStorage.setItem(STORAGE_KEY, locale)
}

export function getLocale(): 'zh-CN' | 'en-US' {
  return i18n.global.locale.value as 'zh-CN' | 'en-US'
}
