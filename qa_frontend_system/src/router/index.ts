import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import { APP_TITLES, ROUTE_PATHS } from '../constants/access'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    section?: string
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: ROUTE_PATHS.chat,
    name: 'Chat',
    component: () => import('../views/chat/index.vue'),
    meta: { title: '智能问答' },
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
        meta: { title: '知识库管理', section: 'knowledge-bases' },
      },
      {
        path: 'workspace/files',
        name: 'WorkspaceFiles',
        component: () => import('../views/workspace/files.vue'),
        meta: { title: '文件处理', section: 'files' },
      },
      {
        path: 'workspace/qa-test',
        name: 'WorkspaceQaTest',
        component: () => import('../views/workspace/qa-test.vue'),
        meta: { title: '召回测试', section: 'qa-test' },
      },
      {
        path: 'workspace/models',
        name: 'WorkspaceModels',
        component: () => import('../views/workspace/models.vue'),
        meta: { title: '模型配置', section: 'models' },
      },
      {
        path: 'workspace/text2sql',
        redirect: ROUTE_PATHS.text2sqlQuery,
        meta: { title: 'Text2SQL 配置', section: 'text2sql' },
      },
      {
        path: 'workspace/text2sql/query',
        name: 'WorkspaceText2SqlQuery',
        component: () => import('../views/workspace/text2sql.vue'),
        meta: { title: 'Text2SQL 查询', section: 'text2sql' },
      },
      {
        path: 'workspace/text2sql/connection',
        name: 'WorkspaceText2SqlConnection',
        component: () => import('../views/workspace/text2sql-connection.vue'),
        meta: { title: 'Text2SQL 连接配置', section: 'text2sql' },
      },
      {
        path: 'workspace/text2sql/tables',
        name: 'WorkspaceText2SqlTables',
        component: () => import('../views/workspace/text2sql-tables.vue'),
        meta: { title: 'Text2SQL 数据表配置', section: 'text2sql' },
      },
      {
        path: 'workspace/text2sql/relations',
        name: 'WorkspaceText2SqlRelations',
        component: () => import('../views/workspace/text2sql-relations.vue'),
        meta: { title: 'Text2SQL 关联关系配置', section: 'text2sql' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(to => {
  document.title = `${String(to.meta.title || APP_TITLES.workspace)} - ${APP_TITLES.appName}`
})

export default router
