// src/main.ts
import { createApp } from 'vue'
import App from './App.vue'
import router from './router' // 引入路由
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css' // 引入 Element Plus 的样式
import * as ElementPlusIconsVue from '@element-plus/icons-vue' // 引入图标
import './style.css' // 这是 vite 默认的全局样式，可以保留

const app = createApp(App)

// 注册所有的 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(ElementPlus) // 使用 Element Plus
app.use(router)      // 使用路由

app.mount('#app')