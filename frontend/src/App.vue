<template>
  <div class="app-container" :class="{ 'is-dark': isDark, 'sidebar-collapsed': sidebarCollapsed && !isMobile }">
    <el-aside
      v-if="!isMobile"
      :width="sidebarCollapsed ? '56px' : '156px'"
      class="sidebar"
    >
      <div class="sidebar-header">
        <div class="logo-area">
          <div class="logo-icon">
            <i class="i-ep-grid"></i>
          </div>
          <transition name="fade-slide">
            <div v-if="!sidebarCollapsed" class="logo-copy">
              <span class="logo-text">{{ t("app.title") }}</span>
              <span class="logo-subtitle">{{ t("app.subtitle") }}</span>
            </div>
          </transition>
        </div>
      </div>

      <el-menu
        router
        :collapse="sidebarCollapsed"
        :default-active="activeMenu"
        class="sidebar-menu"
        :background-color="'transparent'"
        :text-color="isDark ? '#a0a0b0' : '#606266'"
        :active-text-color="'var(--accent-primary)'"
      >
        <el-menu-item
          v-for="item in navItems"
          :key="item.path"
          :index="item.path"
          :class="{ 'primary-nav-item': item.path === '/chat' }"
        >
          <el-icon>
            <component :is="item.icon" />
          </el-icon>
          <template #title>
            <span>{{ item.label }}</span>
          </template>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">
        <div class="connection-status">
          <span class="status-dot" :class="backendConnected ? 'connected' : 'disconnected'"></span>
          <span v-if="!sidebarCollapsed" class="status-text">
            {{ backendConnected ? t("app.connectionOk") : t("app.connectionError") }}
          </span>
        </div>
      </div>
    </el-aside>

    <el-drawer
      v-model="mobileNavOpen"
      direction="ltr"
      size="280px"
      :with-header="false"
      class="mobile-nav-drawer"
    >
      <div class="drawer-header">
        <div class="logo-area">
          <div class="logo-icon">
            <i class="i-ep-grid"></i>
          </div>
          <div class="logo-copy">
            <span class="logo-text">{{ t("app.title") }}</span>
            <span class="logo-subtitle">{{ t("app.subtitle") }}</span>
          </div>
        </div>
      </div>

      <el-menu
        :default-active="activeMenu"
        class="sidebar-menu mobile-menu"
        :background-color="'transparent'"
        :text-color="isDark ? '#a0a0b0' : '#606266'"
        :active-text-color="'var(--accent-primary)'"
        @select="handleMobileNavigate"
      >
        <el-menu-item
          v-for="item in navItems"
          :key="item.path"
          :index="item.path"
          :class="{ 'primary-nav-item': item.path === '/chat' }"
        >
          <el-icon>
            <component :is="item.icon" />
          </el-icon>
          <template #title>
            <span>{{ item.label }}</span>
          </template>
        </el-menu-item>
      </el-menu>
    </el-drawer>

    <el-container class="main-container">
      <el-header class="main-header">
        <div class="header-left">
          <el-button
            text
            class="header-btn nav-trigger"
            :title="isMobile ? t('nav.openDrawer') : sidebarCollapsed ? t('nav.expand') : t('nav.collapse')"
            @click="toggleNavigation"
          >
            <i :class="isMobile ? 'i-ep-operation' : sidebarCollapsed ? 'i-ep-expand' : 'i-ep-fold'"></i>
          </el-button>
        </div>
        <div class="header-right">
          <el-dropdown @command="handleLocaleChange" trigger="click">
            <el-button text class="header-btn">
              <i class="i-ep-global mr-1"></i>
              {{ currentLocale === "zh-CN" ? "中文" : "English" }}
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

          <el-button text class="header-btn" @click="toggleTheme" :title="isDark ? t('theme.light') : t('theme.dark')">
            <i v-if="isDark" class="i-ep-sunny"></i>
            <i v-else class="i-ep-moon"></i>
          </el-button>
        </div>
      </el-header>

      <el-main class="main-content" :class="{ 'chat-mode': route.path === '/chat' }">
        <router-view v-slot="{ Component, route: currentRoute }">
          <transition name="fade-slide" mode="out-in">
            <keep-alive v-if="currentRoute.meta.keepAlive">
              <component :is="Component" />
            </keep-alive>
            <component :is="Component" v-else />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ChatDotRound, Search, Picture, Document, DataAnalysis, Setting } from "@element-plus/icons-vue";
import { useTheme } from "@/composables/useTheme";
import { setLocale, getLocale } from "@/locales";
import { http } from "@/api/http";
import { useRoute, useRouter } from "vue-router";

const { t } = useI18n();
const { isDark, toggleTheme } = useTheme();
const route = useRoute();
const router = useRouter();

const backendConnected = ref(false);
const currentLocale = ref(getLocale());
const activeMenu = computed(() => route.path);
const sidebarCollapsed = ref(false);
const mobileNavOpen = ref(false);
const isMobile = ref(false);

const navItems = computed(() => [
  { path: "/chat", icon: ChatDotRound, label: t("nav.chat") },
  { path: "/search", icon: Search, label: t("nav.search") },
  { path: "/kb", icon: Picture, label: t("nav.knowledgeBase") },
  { path: "/docs", icon: Document, label: t("nav.documents") },
  { path: "/ops", icon: DataAnalysis, label: t("nav.ops") },
  { path: "/settings", icon: Setting, label: t("nav.settings") },
]);

let checkInterval: number | undefined;

async function checkBackendConnection() {
  try {
    await http.get("/api/knowledge-base/list", { params: { skip: 0, limit: 1 } });
    backendConnected.value = true;
  } catch {
    backendConnected.value = false;
  }
}

function handleLocaleChange(locale: "zh-CN" | "en-US") {
  currentLocale.value = locale;
  setLocale(locale);
}

function updateViewportState() {
  isMobile.value = window.innerWidth < 960;
  if (isMobile.value) {
    mobileNavOpen.value = false;
  }
}

function toggleNavigation() {
  if (isMobile.value) {
    mobileNavOpen.value = true;
    return;
  }
  sidebarCollapsed.value = !sidebarCollapsed.value;
}

function handleMobileNavigate(path: string) {
  mobileNavOpen.value = false;
  router.push(path);
}

onMounted(() => {
  updateViewportState();
  window.addEventListener("resize", updateViewportState);
  checkBackendConnection();
  checkInterval = window.setInterval(checkBackendConnection, 30000);
});

onUnmounted(() => {
  window.removeEventListener("resize", updateViewportState);
  if (checkInterval) {
    clearInterval(checkInterval);
  }
});
</script>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  background: var(--bg-primary);
  overflow: hidden;
}

.sidebar {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.68)),
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.08), transparent 24%);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  box-shadow: 18px 0 52px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(20px);
  transition: width 0.24s ease;
}

.sidebar-header {
  padding: 12px 8px 10px;
  border-bottom: 1px solid var(--border-color);
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.logo-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: var(--accent-primary);
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.14), rgba(96, 165, 250, 0.07));
  border-radius: 16px;
  border: 1px solid rgba(37, 99, 235, 0.14);
  flex-shrink: 0;
}

.logo-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.logo-text {
  font-size: 13px;
  font-weight: 800;
  letter-spacing: -0.02em;
  white-space: nowrap;
  color: var(--text-primary);
}

.logo-subtitle {
  display: none;
  color: var(--text-tertiary);
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  padding: 10px 6px;
}

.sidebar-menu :deep(.el-menu-item) {
  height: 38px;
  line-height: 38px;
  margin: 4px 0;
  border-radius: 10px;
  position: relative;
  font-weight: 600;
  transition: background-color 0.18s ease, color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.7);
  transform: translateX(2px);
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(96, 165, 250, 0.06));
  color: var(--accent-primary);
  box-shadow:
    inset 0 0 0 1px rgba(37, 99, 235, 0.1),
    0 12px 30px rgba(37, 99, 235, 0.08);
}

.sidebar-menu :deep(.el-menu-item.primary-nav-item) {
  font-weight: 600;
}

.sidebar-menu :deep(.el-menu--collapse .el-menu-item) {
  width: 40px;
  height: 40px;
  line-height: 40px;
  padding: 0 !important;
  min-width: 40px;
  margin-left: auto;
  margin-right: auto;
  display: block;
  text-align: center;
  box-sizing: border-box;
  position: relative;
}

.sidebar-menu :deep(.el-menu--collapse .el-menu-item .el-icon) {
  margin: auto !important;
  width: 18px;
  height: 18px;
  display: inline-flex !important;
  align-items: center;
  justify-content: center;
  flex: 0 0 18px;
  position: absolute;
  inset: 0;
  line-height: 18px;
}

.sidebar-menu :deep(.el-menu--collapse .el-menu-item .el-icon svg) {
  width: 18px;
  height: 18px;
}

.sidebar-footer {
  padding: 10px 6px 10px;
  border-top: 1px solid var(--border-color);
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  padding: 6px 8px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.56);
  border: 1px solid var(--border-color);
}

.status-text {
  white-space: nowrap;
}

.main-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  min-width: 0;
}

.main-header {
  height: 54px;
  background: rgba(255, 255, 255, 0.62);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  backdrop-filter: blur(18px);
  flex-shrink: 0;
}

.is-dark .main-header {
  background: rgba(17, 28, 51, 0.78);
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-btn {
  min-height: 32px;
  padding: 0 10px;
  color: var(--text-secondary);
  font-size: 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.46);
  border: 1px solid transparent;
}

.header-btn:hover {
  color: var(--accent-primary);
  background: rgba(255, 255, 255, 0.76);
  border-color: var(--border-color);
}

.nav-trigger {
  width: 32px;
}

.main-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 10px 12px 12px;
  overflow-y: auto;
  background: var(--bg-primary);
  min-width: 0;
}

.main-content.chat-mode {
  overflow-y: auto;
}

.drawer-header {
  padding: 8px 8px 16px;
}

.mobile-menu {
  padding-left: 0;
  padding-right: 0;
}

:deep(.el-dropdown-menu__item.is-active) {
  color: var(--accent-primary);
  background: var(--bg-accent-soft);
}

:deep(.mobile-nav-drawer .el-drawer__body) {
  padding: 18px;
  background: var(--bg-secondary);
}

@media (max-width: 960px) {
  .main-header {
    padding: 0 12px;
  }

  .main-content {
    padding: 12px;
  }
}
</style>
