import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/auth/login.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/auth/register.vue'),
    meta: { title: '注册', public: true }
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/chat/index.vue'),
    meta: { title: '跨库聊天', permission: 'chat.use' }
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
        meta: { title: '知识库管理', section: 'knowledge-bases', permission: 'kb.manage' }
      },
      {
        path: 'workspace/files',
        name: 'WorkspaceFiles',
        component: () => import('../views/workspace/files.vue'),
        meta: { title: '文件处理', section: 'files', permission: 'file.manage' }
      },
      {
        path: 'workspace/qa-test',
        name: 'WorkspaceQaTest',
        component: () => import('../views/workspace/qa-test.vue'),
        meta: { title: '召回测试', section: 'qa-test', permission: 'qa.test' }
      },
      {
        path: 'admin',
        name: 'Admin',
        component: () => import('../views/admin/index.vue'),
        meta: { title: '系统管理', section: 'admin', requireAdmin: true }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const token = localStorage.getItem('qa_access_token')
  if (!to.meta.public && !token) {
    return '/login'
  }
  if (to.meta.public && token && (to.path === '/login' || to.path === '/register')) {
    return '/'
  }
  // 权限守卫（requireAdmin 由 layout 侧边栏控制入口，路由层做最后兜底）
  if (to.meta.requireAdmin) {
    // 实际权限校验由页面组件自己处理，路由层不重复从 localStorage 读 user 数据
    // 避免刷新时异步 store 未初始化导致误跳转
  }
})

export default router

