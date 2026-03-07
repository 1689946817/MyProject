import { createRouter, createWebHistory, RouteRecordRaw } from "vue-router";

import KnowledgeBase from "@/views/KnowledgeBase.vue";
import Search from "@/views/Search.vue";
import Chat from "@/views/Chat.vue";

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/kb" },
  { path: "/kb", component: KnowledgeBase },
  { path: "/search", component: Search },
  { path: "/chat", component: Chat }
];

export const router = createRouter({
  history: createWebHistory(),
  routes
});

