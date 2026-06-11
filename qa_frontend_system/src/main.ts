import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import ElementAIVue from 'element-ai-vue'
import 'element-plus/dist/index.css'
import 'element-ai-vue/dist/index.css'

import App from './App.vue'
import router from './router'
import './style.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(ElementPlus)
app.use(ElementAIVue)

app.mount('#app')
