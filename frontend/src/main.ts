/**
 * 应用入口文件
 *
 * 初始化 Vue 应用，配置路由、UI 库、i18n 和主题，挂载到 DOM。
 */
import { createApp } from "vue";
import ElementPlus from "element-plus"; // Element Plus UI 库
import "element-plus/dist/index.css"; // Element Plus 样式
import "element-plus/theme-chalk/dark/css-vars.css"; // Element Plus 深色模式 CSS 变量

// UnoCSS (在 vite.config.ts 中配置，这里只需导入虚拟模块)
import "virtual:uno.css";

// 导入全局样式
import "./styles/variables.css"; // CSS 变量（主题色）
import "./styles/global.css"; // 全局样式

import App from "./App.vue"; // 根组件
import { router } from "./router"; // 路由配置
import { i18n } from "./locales"; // i18n 配置

/**
 * 创建 Vue 应用实例
 */
const app = createApp(App);

// 使用路由
app.use(router);
// 使用 Element Plus UI 库
app.use(ElementPlus);
// 使用 i18n
app.use(i18n);

/**
 * 挂载应用到 DOM
 *
 * 将应用挂载到 HTML 中的 #app 元素。
 */
app.mount("#app");
