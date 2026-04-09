import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    public?: boolean
    permission?: string
    requireAdmin?: boolean
    section?: string
  }
}

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
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('../views/auth/login.vue'),
    meta: { title: '无权限', public: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to) => {
  const token = localStorage.getItem('qa_access_token')

  // 1. 公开页面无需认证
  if (to.meta.public) {
    if (token && (to.path === '/login' || to.path === '/register')) {
      return '/'
    }
    return
  }

  // 2. 未登录跳转登录页
  if (!token) {
    return '/login'
  }

  // 3. 权限校验：懒加载 auth store，确保用户信息已获取
  const { useAuthStore } = await import('../stores/auth')
  const authStore = useAuthStore()

  // 确保用户信息已加载
  if (!authStore.user) {
    await authStore.init()
  }

  // 用户信息加载失败（token 失效等）
  if (!authStore.user) {
    return '/login'
  }

  // 4. 管理员页面校验
  if (to.meta.requireAdmin && !authStore.isAdmin) {
    return '/workspace/overview'
  }

  // 5. 权限码校验
  if (to.meta.permission && !authStore.hasPermission(to.meta.permission)) {
    return '/workspace/overview'
  }
})

export default router

