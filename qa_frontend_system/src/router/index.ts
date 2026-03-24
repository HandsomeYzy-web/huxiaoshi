// src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/admin/kb' // 默认跳到管理端
    },
    {
      path: '/admin',
      name: 'Admin',
      component: () => import('../views/admin/AdminLayout.vue'),
      children: [
        {
          path: 'kb',
          name: 'KbManage',
          component: () => import('../views/admin/kb/KbManage.vue')
        },
        // 预留的数据库管理页面
        // {
        //   path: 'db',
        //   name: 'DbManage',
        //   component: () => import('../views/admin/db/DbManage.vue')
        // }
      ]
    }
  ]
})

export default router