import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Chat',
      // 修正：加上 user/ 目录
      component: () => import('../views/user/ChatWindow.vue')
    },
    {
      path: '/admin',
      name: 'Admin',
      // 修正：指向你实际存在的 KbList.vue 作为后台默认页面
      component: () => import('../views/admin/KbList.vue')
    }
  ]
})

export default router