/**
 * 应用入口文件
 * 
 * 初始化 Vue 应用，配置路由和 UI 库，挂载到 DOM。
 */
import { createApp } from "vue";
import ElementPlus from "element-plus"; // Element Plus UI 库
import "element-plus/dist/index.css"; // Element Plus 样式

import App from "./App.vue"; // 根组件
import { router } from "./router"; // 路由配置

/**
 * 创建 Vue 应用实例
 */
const app = createApp(App);

// 使用路由
app.use(router);
// 使用 Element Plus UI 库
app.use(ElementPlus);

/**
 * 挂载应用到 DOM
 * 
 * 将应用挂载到 HTML 中的 #app 元素。
 */
app.mount("#app");

