<template>
  <div class="app-container" :class="{ 'is-dark': isDark }">
    <!-- 侧边栏 -->
    <el-aside width="240px" class="sidebar">
      <div class="sidebar-header">
        <div class="logo-area">
          <div class="logo-icon">
            <i class="i-ep-grid"></i>
          </div>
          <div class="logo-copy">
            <span class="logo-text">{{ t('app.title') }}</span>
            <span class="logo-subtitle">{{ t('app.subtitle') }}</span>
          </div>
        </div>
      </div>

      <el-menu
        router
        :default-active="activeMenu"
        class="sidebar-menu"
        :background-color="'transparent'"
        :text-color="isDark ? '#a0a0b0' : '#606266'"
        :active-text-color="'var(--accent-primary)'"
      >
        <el-menu-item index="/chat" class="primary-nav-item">
          <template #title>
            <i class="i-ep-chat-dot-round mr-2"></i>
            <span>{{ t('nav.chat') }}</span>
          </template>
        </el-menu-item>
        <el-menu-item index="/search">
          <template #title>
            <i class="i-ep-search mr-2"></i>
            <span>{{ t('nav.search') }}</span>
          </template>
        </el-menu-item>
        <el-menu-item index="/kb">
          <template #title>
            <i class="i-ep-picture mr-2"></i>
            <span>{{ t('nav.knowledgeBase') }}</span>
          </template>
        </el-menu-item>
        <el-menu-item index="/docs">
          <template #title>
            <i class="i-ep-document mr-2"></i>
            <span>{{ t('nav.documents') }}</span>
          </template>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">
        <!-- 连接状态 -->
        <div class="connection-status">
          <span class="status-dot" :class="backendConnected ? 'connected' : 'disconnected'"></span>
          <span class="status-text">{{ backendConnected ? t('app.connectionOk') : t('app.connectionError') }}</span>
        </div>
      </div>
    </el-aside>

    <!-- 主内容区 -->
    <el-container class="main-container">
      <!-- Header -->
      <el-header class="main-header">
        <div class="header-right">
          <!-- 语言切换 -->
          <el-dropdown @command="handleLocaleChange" trigger="click">
            <el-button text class="header-btn">
              <i class="i-ep-global mr-1"></i>
              {{ currentLocale === 'zh-CN' ? '中文' : 'English' }}
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="zh-CN" :class="{ 'is-active': currentLocale === 'zh-CN' }">
                  中文
                </el-dropdown-item>
                <el-dropdown-item command="en-US" :class="{ 'is-active': currentLocale === 'en-US' }">
                  English
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <!-- 主题切换 -->
          <el-button text class="header-btn" @click="toggleTheme" :title="isDark ? t('theme.light') : t('theme.dark')">
            <i v-if="isDark" class="i-ep-sunny"></i>
            <i v-else class="i-ep-moon"></i>
          </el-button>
        </div>
      </el-header>

      <!-- Main Content -->
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import { setLocale, getLocale } from '@/locales'
import { http } from '@/api/http'
import { useRoute } from 'vue-router'

const { t } = useI18n()
const { isDark, toggleTheme } = useTheme()
const route = useRoute()

const backendConnected = ref(false)
const currentLocale = ref(getLocale())
const activeMenu = computed(() => route.path)

let checkInterval: number | undefined

async function checkBackendConnection() {
  try {
    await http.get('/api/knowledge-base/list', { params: { skip: 0, limit: 1 } })
    backendConnected.value = true
  } catch {
    backendConnected.value = false
  }
}

function handleLocaleChange(locale: 'zh-CN' | 'en-US') {
  currentLocale.value = locale
  setLocale(locale)
}

onMounted(() => {
  checkBackendConnection()
  checkInterval = window.setInterval(checkBackendConnection, 30000)
})

onUnmounted(() => {
  if (checkInterval) {
    clearInterval(checkInterval)
  }
})
</script>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  background: var(--bg-primary);
}

.sidebar {
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  box-shadow: 12px 0 32px rgba(15, 23, 42, 0.04);
}

.sidebar-header {
  padding: 24px 20px 18px;
  border-bottom: 1px solid var(--border-color);
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
  border-radius: 14px;
  border: 1px solid rgba(37, 99, 235, 0.12);
}

.logo-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.logo-text {
  font-size: 15px;
  font-weight: 700;
  white-space: nowrap;
  color: var(--text-primary);
}

.logo-subtitle {
  font-size: 12px;
  color: var(--text-tertiary);
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  padding: 14px 12px;
}

.sidebar-menu :deep(.el-menu-item) {
  height: 46px;
  line-height: 46px;
  margin: 6px 0;
  border-radius: 12px;
  position: relative;
  font-weight: 500;
  transition: background-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  background: var(--bg-tertiary);
  transform: translateX(2px);
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: var(--bg-accent-soft);
  color: var(--accent-primary);
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.12);
}

.sidebar-menu :deep(.el-menu-item.primary-nav-item) {
  font-weight: 600;
}

.sidebar-footer {
  padding: 16px 20px 20px;
  border-top: 1px solid var(--border-color);
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.main-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

.main-header {
  height: 68px;
  background: rgba(255, 255, 255, 0.72);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 24px;
  backdrop-filter: blur(16px);
}

.is-dark .main-header {
  background: rgba(17, 28, 51, 0.78);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-btn {
  min-height: 38px;
  padding: 0 12px;
  color: var(--text-secondary);
  font-size: 14px;
  border-radius: 12px;
}

.header-btn:hover {
  color: var(--accent-primary);
  background: var(--bg-tertiary);
}

.main-content {
  flex: 1;
  padding: 28px;
  overflow-y: auto;
  background: var(--bg-primary);
}

:deep(.el-dropdown-menu__item.is-active) {
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
}

@media (max-width: 1200px) {
  .sidebar {
    width: 220px;
  }
}

@media (max-width: 960px) {
  .main-content {
    padding: 20px;
  }
}
</style>
