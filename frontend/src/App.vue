<template>
  <div class="app-container" :class="{ 'is-dark': isDark }">
    <!-- 侧边栏 -->
    <el-aside width="240px" class="sidebar">
      <div class="sidebar-header">
        <div class="logo-area">
          <div class="logo-icon">
            <i class="i-ep-grid pulse-glow"></i>
          </div>
          <span class="logo-text gradient-text">{{ t('app.title') }}</span>
        </div>
      </div>

      <el-menu
        router
        default-active="/kb"
        class="sidebar-menu"
        :background-color="'transparent'"
        :text-color="isDark ? '#a0a0b0' : '#606266'"
        :active-text-color="'var(--accent-primary)'"
      >
        <el-menu-item index="/kb">
          <template #title>
            <i class="i-ep-picture mr-2"></i>
            <span>{{ t('nav.knowledgeBase') }}</span>
          </template>
        </el-menu-item>
        <el-menu-item index="/search">
          <template #title>
            <i class="i-ep-search mr-2"></i>
            <span>{{ t('nav.search') }}</span>
          </template>
        </el-menu-item>
        <el-menu-item index="/chat">
          <template #title>
            <i class="i-ep-chat-dot-round mr-2"></i>
            <span>{{ t('nav.chat') }}</span>
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
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import { setLocale, getLocale } from '@/locales'
import { http } from '@/api/http'

const { t } = useI18n()
const { isDark, toggleTheme } = useTheme()

const backendConnected = ref(false)
const currentLocale = ref(getLocale())

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

/* 侧边栏 */
.sidebar {
  background: linear-gradient(180deg, #1a1a2e 0%, #0f0f1a 100%);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.sidebar::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 200px;
  background: radial-gradient(ellipse at top, rgba(0, 212, 255, 0.1) 0%, transparent 70%);
  pointer-events: none;
}

.sidebar-header {
  padding: 24px 16px;
  border-bottom: 1px solid var(--border-color);
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: var(--accent-primary);
  background: rgba(0, 212, 255, 0.1);
  border-radius: 8px;
  border: 1px solid rgba(0, 212, 255, 0.3);
}

.logo-text {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
}

/* 菜单 */
.sidebar-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  padding: 12px 0;
}

.sidebar-menu :deep(.el-menu-item) {
  height: 48px;
  line-height: 48px;
  margin: 4px 8px;
  border-radius: 8px;
  position: relative;
  transition: all 0.3s ease;
}

.sidebar-menu :deep(.el-menu-item::before) {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 0;
  background: var(--accent-primary);
  border-radius: 0 2px 2px 0;
  transition: height 0.3s ease;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  background: rgba(0, 212, 255, 0.1);
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-primary);
}

.sidebar-menu :deep(.el-menu-item.is-active::before) {
  height: 24px;
  box-shadow: 0 0 10px var(--accent-primary);
}

/* 页脚 */
.sidebar-footer {
  padding: 16px;
  border-top: 1px solid var(--border-color);
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: pulse-glow 2s ease-in-out infinite;
}

.status-dot.connected {
  background: #67c23a;
  box-shadow: 0 0 6px #67c23a;
}

.status-dot.disconnected {
  background: #f56c6c;
  box-shadow: 0 0 6px #f56c6c;
}

/* 主内容区 */
.main-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

.main-header {
  height: 56px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-btn {
  color: var(--text-secondary);
  font-size: 14px;
}

.header-btn:hover {
  color: var(--accent-primary);
}

.main-content {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background: var(--bg-primary);
}

/* 路由切换动画 */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s ease;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* Dropdown */
:deep(.el-dropdown-menu__item.is-active) {
  color: var(--accent-primary);
  background: rgba(0, 212, 255, 0.1);
}
</style>
