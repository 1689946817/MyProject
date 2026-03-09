/**
 * 路由配置
 * 
 * 配置 Vue Router 路由，定义应用的页面路由结构。
 * 包括：
 * - 知识库管理页面
 * - 搜索页面
 * - 聊天页面
 */
import { createRouter, createWebHistory, RouteRecordRaw } from "vue-router";

// 导入页面组件
import KnowledgeBase from "@/views/KnowledgeBase.vue"; // 知识库管理页面
import Search from "@/views/Search.vue"; // 搜索页面
import Chat from "@/views/Chat.vue"; // 聊天页面

/**
 * 路由配置数组
 * 
 * 定义应用的路由结构，包括路径和对应的组件。
 */
const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/kb" }, // 根路径重定向到知识库页面
  { path: "/kb", component: KnowledgeBase }, // 知识库管理页面
  { path: "/search", component: Search }, // 搜索页面
  { path: "/chat", component: Chat } // 聊天页面
];

/**
 * Vue Router 实例
 * 
 * 创建并配置路由实例，使用 HTML5 History 模式。
 */
export const router = createRouter({
  history: createWebHistory(), // 使用 HTML5 History 模式
  routes // 应用路由配置
});

