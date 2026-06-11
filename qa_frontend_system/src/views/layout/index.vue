<template>
  <el-container class="workspace-shell">
    <el-aside class="workspace-aside" width="300px">
      <div class="brand-block">
        <img class="brand-emblem" src="/hunnu-emblem.jpg" alt="湖南师范大学校徽" />
        <div class="brand-text">
          <div class="brand-university">湖南师范大学</div>
          <div class="brand-university-en">HUNAN NORMAL UNIVERSITY</div>
          <div class="brand-platform">智慧知识服务平台</div>
        </div>
      </div>

      <el-scrollbar class="menu-scroll">
        <el-menu
          class="workspace-menu"
          :default-active="activePath"
          router
          background-color="transparent"
          text-color="#f4ddca"
          active-text-color="#7f1f20"
        >
          <template v-for="node in menuTree" :key="node.code">
            <el-sub-menu v-if="node.children.length > 0" :index="node.path || node.code">
              <template #title>
                <el-icon><component :is="resolveIcon(node.icon)" /></el-icon>
                <span>{{ node.name }}</span>
              </template>
              <template v-for="child in node.children" :key="child.code">
                <el-sub-menu v-if="child.children.length > 0" :index="child.path || child.code">
                  <template #title>
                    <el-icon><component :is="resolveIcon(child.icon)" /></el-icon>
                    <span>{{ child.name }}</span>
                  </template>
                  <el-menu-item
                    v-for="grandChild in child.children"
                    :key="grandChild.code"
                    :index="grandChild.path!"
                    class="workspace-menu-item"
                  >
                    <el-icon><component :is="resolveIcon(grandChild.icon)" /></el-icon>
                    <span>{{ grandChild.name }}</span>
                  </el-menu-item>
                </el-sub-menu>

                <el-menu-item v-else :index="child.path!" class="workspace-menu-item">
                  <el-icon><component :is="resolveIcon(child.icon)" /></el-icon>
                  <span>{{ child.name }}</span>
                </el-menu-item>
              </template>
            </el-sub-menu>

            <el-menu-item v-else :index="node.path || '/'" class="workspace-menu-item">
              <el-icon><component :is="resolveIcon(node.icon)" /></el-icon>
              <span>{{ node.name }}</span>
            </el-menu-item>
          </template>
        </el-menu>
      </el-scrollbar>

      <div class="aside-footer">仁爱精勤</div>
    </el-aside>

    <el-container class="workspace-main">
      <el-header class="workspace-header">
        <div class="header-left">
          <div class="header-breadcrumb">{{ currentSection }} / {{ currentTitle }}</div>
          <div class="header-title-wrap">
            <h1 class="header-title">{{ currentTitle }}</h1>

          </div>
        </div>
      </el-header>

      <el-main class="workspace-content">
        <router-view />
      </el-main>

      <footer class="workspace-footer">湖南师范大学 版权所有 © 2026</footer>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChatDotRound,
  ChatLineRound,
  DataAnalysis,
  DataLine,
  Files,
  FolderOpened,
  Setting,
  Share,
} from '@element-plus/icons-vue'

import { ROUTE_PATHS } from '../../constants/access'

interface MenuNode {
  code: string
  name: string
  path: string
  icon: string
  children: MenuNode[]
}

const route = useRoute()

const iconMap: Record<string, unknown> = {
  ChatDotRound,
  ChatLineRound,
  DataAnalysis,
  DataLine,
  Files,
  FolderOpened,
  Setting,
  Share,
}

// 去鉴权后菜单为静态定义（不再依赖后端权限树）。
const menuTree: MenuNode[] = [
  { code: 'chat', name: '智能问答', path: ROUTE_PATHS.chat, icon: 'ChatDotRound', children: [] },
  {
    code: 'workspace',
    name: '工作台',
    path: ROUTE_PATHS.overview,
    icon: 'DataAnalysis',
    children: [
      { code: 'workspace.overview', name: '工作台概览', path: ROUTE_PATHS.overview, icon: 'DataAnalysis', children: [] },
      { code: 'workspace.kb', name: '知识库管理', path: ROUTE_PATHS.knowledgeBases, icon: 'FolderOpened', children: [] },
      { code: 'workspace.file', name: '文件处理', path: ROUTE_PATHS.files, icon: 'Files', children: [] },
      { code: 'workspace.qa', name: '召回测试', path: ROUTE_PATHS.qaTest, icon: 'ChatLineRound', children: [] },
      { code: 'workspace.models', name: '模型配置', path: ROUTE_PATHS.models, icon: 'Setting', children: [] },
      {
        code: 'workspace.text2sql',
        name: 'Text2SQL配置',
        path: ROUTE_PATHS.text2sqlQuery,
        icon: 'DataLine',
        children: [
          { code: 'workspace.text2sql.query', name: 'SQL查询', path: ROUTE_PATHS.text2sqlQuery, icon: 'DataLine', children: [] },
          { code: 'workspace.text2sql.connection', name: '连接配置', path: ROUTE_PATHS.text2sqlConnection, icon: 'Setting', children: [] },
          { code: 'workspace.text2sql.tables', name: '数据表配置', path: ROUTE_PATHS.text2sqlTables, icon: 'Files', children: [] },
          { code: 'workspace.text2sql.relations', name: '关联关系', path: ROUTE_PATHS.text2sqlRelations, icon: 'Share', children: [] },
        ],
      },
    ],
  },
]

function getSectionLabel(path: string) {
  if (path.startsWith('/workspace')) return '工作区'
  if (path.startsWith('/chat')) return '智能问答'
  return '导航'
}

const currentTitle = computed(() => String(route.meta.title || '学院知识库概览'))
const currentSection = computed(() => getSectionLabel(route.path))
const activePath = computed(() => route.path)

function resolveIcon(icon: string | null) {
  return (icon && iconMap[icon]) || Setting
}
</script>

<style scoped>
.workspace-shell {
  min-height: 100vh;
  background:
    radial-gradient(circle at 78% 10%, rgba(172, 52, 40, 0.06), transparent 30%),
    linear-gradient(180deg, #f7f2eb 0%, #f2ece2 100%);
}

.workspace-aside {
  display: flex;
  flex-direction: column;
  padding: 20px 14px 16px;
  color: #f5e7dc;
  background:
    linear-gradient(180deg, rgba(117, 18, 24, 0.95) 0%, rgba(135, 20, 30, 0.98) 46%, rgba(93, 11, 18, 1) 100%),
    radial-gradient(circle at 16% 92%, rgba(255, 218, 180, 0.1), transparent 30%);
  border-right: 1px solid rgba(232, 204, 183, 0.24);
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.08);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 6px 18px;
  margin-bottom: 10px;
  border-bottom: 1px solid rgba(246, 227, 211, 0.2);
}

.brand-emblem {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  object-fit: contain;
  flex: 0 0 auto;
  box-shadow: 0 8px 22px rgba(35, 6, 8, 0.4);
}

.brand-text {
  min-width: 0;
}

.brand-university {
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: 23px;
  font-weight: 700;
  line-height: 1.05;
  color: #f9eee4;
}

.brand-university-en {
  margin-top: 2px;
  font-family: 'Cinzel', serif;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: rgba(252, 234, 217, 0.86);
}

.brand-platform {
  margin-top: 8px;
  font-size: 16px;
  letter-spacing: 0.08em;
  color: #ffe9cf;
}

.menu-scroll {
  flex: 1;
  min-height: 0;
  padding-top: 10px;
}

.workspace-menu {
  border-right: none;
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: rgba(255, 230, 201, 0.14);
  --el-menu-text-color: #f3d8c3;
  --el-menu-active-color: #7f1f20;
}

:deep(.workspace-menu-item),
:deep(.el-sub-menu__title) {
  height: 46px;
  margin-bottom: 8px;
  border-radius: 22px;
  font-size: 15px;
  font-weight: 600;
  color: #f3d8c3;
}

:deep(.el-sub-menu__title:hover),
:deep(.workspace-menu-item:hover) {
  background: rgba(255, 229, 205, 0.16);
}

:deep(.workspace-menu-item.is-active) {
  color: #7f1f20;
  background: linear-gradient(92deg, #fde7c8 0%, #f4dcb6 100%);
  box-shadow: 0 8px 18px rgba(57, 8, 11, 0.26);
}

:deep(.el-sub-menu .el-menu-item) {
  margin: 4px 0 4px 12px;
  width: calc(100% - 12px);
}

.aside-footer {
  margin-top: 10px;
  padding: 10px 12px 2px;
  font-size: 15px;
  text-align: center;
  letter-spacing: 0.16em;
  color: rgba(253, 229, 207, 0.7);
}

.workspace-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.workspace-header {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: auto;
  min-height: 118px;
  padding: 14px 30px;
  border-bottom: 1px solid #e9dbc8;
  background:
    linear-gradient(180deg, rgba(255, 251, 246, 0.95) 0%, rgba(249, 241, 230, 0.95) 100%),
    radial-gradient(circle at 74% -20%, rgba(196, 113, 89, 0.1), transparent 48%);
}

.workspace-header::after {
  content: '';
  position: absolute;
  right: 30px;
  left: 36%;
  bottom: 0;
  height: 58px;
  pointer-events: none;
  opacity: 0.35;
  background:
    linear-gradient(0deg, rgba(188, 136, 101, 0.08), rgba(188, 136, 101, 0)),
    repeating-linear-gradient(
      90deg,
      rgba(188, 136, 101, 0) 0 30px,
      rgba(188, 136, 101, 0.22) 30px 31px,
      rgba(188, 136, 101, 0) 31px 62px
    );
}

.header-left {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
}

.header-breadcrumb {
  margin-bottom: 6px;
  font-size: 13px;
  color: #7c6859;
}

.header-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-title {
  margin: 0;
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: clamp(30px, 2.1vw, 42px);
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: #382820;
  word-break: break-word;
}

.header-seal {
  width: 20px;
  height: 20px;
  display: inline-grid;
  place-items: center;
  margin-top: 2px;
  border: 1px solid #ab3c38;
  border-radius: 2px;
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: 14px;
  color: #ab3c38;
}

.header-user {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 2px;
  margin-left: 16px;
  flex: 0 0 auto;
}

.user-avatar {
  width: 46px;
  height: 46px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #fff6ea;
  background: linear-gradient(150deg, #9f2f2f 0%, #7d1f24 100%);
  box-shadow: 0 10px 16px rgba(124, 30, 29, 0.28);
}

.header-user-meta {
  display: grid;
  justify-items: start;
}

.user-name {
  font-size: 16px;
  line-height: 1.2;
  color: #37281f;
}

.logout-link {
  margin-top: 3px;
  border: none;
  background: transparent;
  padding: 0;
  font-size: 13px;
  color: #8a7161;
  cursor: pointer;
}

.logout-link:hover {
  color: #822925;
}

.workspace-content {
  flex: 1;
  padding: 24px;
}

.workspace-footer {
  padding: 12px 26px 18px;
  font-size: 13px;
  color: #8e7867;
}

@media (max-width: 1180px) {
  .workspace-aside {
    width: 270px !important;
  }

  .brand-university {
    font-size: 21px;
  }

  .brand-platform {
    font-size: 14px;
  }

  .header-title {
    font-size: 34px;
  }
}

@media (max-width: 980px) {
  .workspace-shell {
    flex-direction: column;
  }

  .workspace-aside {
    width: 100% !important;
    max-height: 360px;
  }

  .workspace-header {
    min-height: 104px;
    padding: 12px 18px;
  }

  .header-title {
    font-size: 30px;
  }

  .workspace-content {
    padding: 16px;
  }

  .workspace-footer {
    padding: 10px 16px 14px;
  }
}

@media (max-width: 720px) {
  .brand-emblem {
    width: 52px;
    height: 52px;
  }

  .brand-university {
    font-size: 19px;
  }

  .header-breadcrumb {
    font-size: 13px;
  }

  .header-title {
    font-size: 24px;
  }

  .header-user {
    gap: 8px;
  }

  .user-avatar {
    width: 40px;
    height: 40px;
  }

  .user-name {
    font-size: 15px;
  }
}
</style>
