import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import { canAccessRoute } from '../access/control'
import { ACCESS_CODES, APP_TITLES, ROUTE_PATHS } from '../constants/access'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    public?: boolean
    permission?: string
    section?: string
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: ROUTE_PATHS.login,
    name: 'Login',
    component: () => import('../views/auth/login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: ROUTE_PATHS.register,
    name: 'Register',
    component: () => import('../views/auth/register.vue'),
    meta: { title: '注册', public: true },
  },
  {
    path: ROUTE_PATHS.chat,
    name: 'Chat',
    component: () => import('../views/chat/index.vue'),
    meta: { title: '智能问答', permission: ACCESS_CODES.chatUse },
  },
  {
    path: ROUTE_PATHS.home,
    component: () => import('../views/layout/index.vue'),
    redirect: ROUTE_PATHS.overview,
    children: [
      {
        path: 'workspace/overview',
        name: 'WorkspaceOverview',
        component: () => import('../views/workspace/overview.vue'),
        meta: { title: '工作台概览', section: 'overview' },
      },
      {
        path: 'workspace/knowledge-bases',
        name: 'WorkspaceKnowledgeBases',
        component: () => import('../views/workspace/knowledge-bases.vue'),
        meta: { title: '知识库管理', section: 'knowledge-bases', permission: ACCESS_CODES.workspaceKb },
      },
      {
        path: 'workspace/files',
        name: 'WorkspaceFiles',
        component: () => import('../views/workspace/files.vue'),
        meta: { title: '文件处理', section: 'files', permission: ACCESS_CODES.workspaceFile },
      },
      {
        path: 'workspace/qa-test',
        name: 'WorkspaceQaTest',
        component: () => import('../views/workspace/qa-test.vue'),
        meta: { title: '召回测试', section: 'qa-test', permission: ACCESS_CODES.workspaceQa },
      },
      {
        path: 'admin',
        redirect: ROUTE_PATHS.adminRoles,
        meta: { title: '系统管理', section: 'admin', permission: ACCESS_CODES.admin },
      },
      {
        path: 'admin/roles',
        name: 'AdminRoles',
        component: () => import('../views/admin/index.vue'),
        meta: { title: '角色管理', section: 'admin', permission: ACCESS_CODES.adminRole },
      },
      {
        path: 'admin/users',
        name: 'AdminUsers',
        component: () => import('../views/admin/index.vue'),
        meta: { title: '用户管理', section: 'admin', permission: ACCESS_CODES.adminUser },
      },
      {
        path: 'admin/permissions',
        name: 'AdminPermissions',
        component: () => import('../views/admin/index.vue'),
        meta: { title: '权限管理', section: 'admin', permission: ACCESS_CODES.adminPermission },
      },
      {
        path: 'admin/kb-access',
        name: 'AdminKbAccess',
        component: () => import('../views/admin/index.vue'),
        meta: { title: '知识库访问', section: 'admin', permission: ACCESS_CODES.adminKbAccess },
      },
      {
        path: 'admin/models',
        name: 'AdminModels',
        component: () => import('../views/admin/index.vue'),
        meta: { title: '模型配置', section: 'admin', permission: ACCESS_CODES.adminModel },
      },
    ],
  },
  {
    path: ROUTE_PATHS.forbidden,
    name: 'Forbidden',
    component: () => import('../views/auth/login.vue'),
    meta: { title: '无权访问', public: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async to => {
  document.title = `${String(to.meta.title || APP_TITLES.workspace)} - ${APP_TITLES.appName}`

  const token = localStorage.getItem('qa_access_token')
  if (to.meta.public) {
    if (token && (to.path === ROUTE_PATHS.login || to.path === ROUTE_PATHS.register)) return ROUTE_PATHS.home
    return
  }
  if (!token) return ROUTE_PATHS.login

  const { useAuthStore } = await import('../stores/auth')
  const authStore = useAuthStore()
  await authStore.init()

  if (!authStore.user) return ROUTE_PATHS.login

  // 纯聊天用户（无工作台/管理权限）直接进入聊天界面
  const hasWorkspaceOrAdmin =
    authStore.hasPermission(ACCESS_CODES.workspace) ||
    authStore.hasPermission(ACCESS_CODES.admin)
  if (!hasWorkspaceOrAdmin && authStore.hasPermission(ACCESS_CODES.chatUse)) {
    if (to.path !== ROUTE_PATHS.chat) return ROUTE_PATHS.chat
    return
  }

  if (
    !canAccessRoute(
      {
        permissions: authStore.permissions,
      },
      to.meta,
    )
  ) {
    return ROUTE_PATHS.overview
  }
})

export default router
