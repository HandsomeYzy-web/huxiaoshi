import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/chat/index.vue'),
    meta: { title: '跨库聊天' }
  },
  {
    path: '/',
    component: () => import('../views/layout/index.vue'),
    redirect: '/workspace/overview',
    children: [
      {
        path: 'workspace/overview',
        name: 'WorkspaceOverview',
        component: () => import('../views/workspace/overview.vue'),
        meta: { title: '工作台总览', section: 'overview' }
      },
      {
        path: 'workspace/knowledge-bases',
        name: 'WorkspaceKnowledgeBases',
        component: () => import('../views/workspace/knowledge-bases.vue'),
        meta: { title: '知识库管理', section: 'knowledge-bases' }
      },
      {
        path: 'workspace/files',
        name: 'WorkspaceFiles',
        component: () => import('../views/workspace/files.vue'),
        meta: { title: '文件处理', section: 'files' }
      },
      {
        path: 'workspace/qa-test',
        name: 'WorkspaceQaTest',
        component: () => import('../views/workspace/qa-test.vue'),
        meta: { title: '召回测试', section: 'qa-test' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
