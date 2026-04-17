<template>
  <el-container class="workspace-shell">
    <el-aside class="workspace-aside" width="280px">
      <div class="brand-block">
        <div class="brand-mark">QA</div>
        <div>
          <div class="brand-title">{{ APP_TITLES.workspace }}</div>
        </div>
      </div>

      <el-scrollbar class="menu-scroll">
        <el-menu
          class="workspace-menu"
          :default-active="activePath"
          router
          background-color="transparent"
          text-color="#adc2bd"
          active-text-color="#102a24"
        >
          <template v-for="node in menuTree" :key="node.code">
            <!-- Level 1 with children → sub-menu -->
            <el-sub-menu v-if="node.children.length > 0" :index="node.path || node.code">
              <template #title>
                <el-icon><component :is="resolveIcon(node.icon)" /></el-icon>
                <span>{{ node.name }}</span>
              </template>
              <el-menu-item
                v-for="child in node.children"
                :key="child.code"
                :index="child.path!"
                class="workspace-menu-item"
              >
                <el-icon><component :is="resolveIcon(child.icon)" /></el-icon>
                <span>{{ child.name }}</span>
              </el-menu-item>
            </el-sub-menu>

            <!-- Level 1 without visible children → single item -->
            <el-menu-item
              v-else
              :index="node.path || '/'"
              class="workspace-menu-item"
            >
              <el-icon><component :is="resolveIcon(node.icon)" /></el-icon>
              <span>{{ node.name }}</span>
            </el-menu-item>
          </template>
        </el-menu>
      </el-scrollbar>
    </el-aside>

    <el-container class="workspace-main">
      <el-header class="workspace-header">
        <div>
          <div class="header-eyebrow">{{ currentSection }}</div>
          <div class="header-title">{{ currentTitle }}</div>
        </div>
        <div v-if="authStore.user" class="header-user">
          <span class="user-name">{{ authStore.user.username }}</span>
          <el-button link size="small" class="logout-btn" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>

      <el-main class="workspace-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChatDotRound,
  ChatLineRound,
  DataAnalysis,
  Files,
  FolderOpened,
  Setting,
  User,
  UserFilled,
} from '@element-plus/icons-vue'

import { getSectionLabel } from '../../access/control'
import type { PermissionTreeNode } from '../../api/admin'
import { APP_TITLES, ROUTE_PATHS } from '../../constants/access'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const iconMap: Record<string, unknown> = {
  ChatDotRound,
  ChatLineRound,
  DataAnalysis,
  Files,
  FolderOpened,
  Setting,
  UserFilled,
  User,
}

/**
 * 从权限树构建菜单：
 * - Level 1 带 path 的节点作为菜单分组
 * - Level 2 带 path 的子节点作为菜单项
 * - 过滤掉 chat 分组（chat 有独立页面不在 layout 内）
 */
const menuTree = computed<PermissionTreeNode[]>(() => {
  return authStore.permissionTree
    .filter(node => node.code !== 'chat' && node.path)
    .map(node => ({
      ...node,
      children: (node.children || []).filter(child => child.path),
    }))
})

const currentTitle = computed(() => String(route.meta.title || APP_TITLES.workspace))
const currentSection = computed(() => getSectionLabel(route.path))
const activePath = computed(() => route.path)

function resolveIcon(icon: string | null) {
  return (icon && iconMap[icon]) || Setting
}

function handleLogout() {
  authStore.logout()
  router.push(ROUTE_PATHS.login)
}
</script>

<style scoped>
.workspace-shell {
  min-height: 100vh;
  background:
    radial-gradient(circle at top right, rgba(231, 189, 78, 0.16), transparent 28%),
    linear-gradient(180deg, #f3ede2 0%, #eef3ef 100%);
}

.workspace-aside {
  display: flex;
  flex-direction: column;
  padding: 22px 18px 18px;
  color: #f6f6ee;
  background: linear-gradient(180deg, #14231f 0%, #1a322d 52%, #1d4540 100%);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 26px;
}

.brand-mark {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  font-size: 18px;
  font-weight: 700;
  color: #102a24;
  background: linear-gradient(135deg, #f2d98d 0%, #f3f0db 100%);
}

.brand-title {
  font-size: 18px;
  font-weight: 700;
}

.menu-scroll {
  flex: 1;
  min-height: 0;
}

.workspace-menu {
  border-right: none;
}

:deep(.workspace-menu-item),
:deep(.el-sub-menu__title) {
  height: 46px;
  margin-bottom: 8px;
  border-radius: 14px;
  font-weight: 600;
}

:deep(.workspace-menu-item.is-active) {
  background: linear-gradient(135deg, #f2d98d 0%, #e8f0cf 100%);
}

:deep(.el-sub-menu .el-menu-item) {
  margin: 4px 0 4px 12px;
}

.workspace-main {
  min-width: 0;
}

.workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28px 32px 10px;
}

.header-eyebrow {
  font-size: 12px;
  letter-spacing: 0.12em;
  color: #7b8d86;
}

.header-title {
  font-size: 28px;
  line-height: 1.15;
  font-weight: 800;
  color: #16312a;
}

.header-user {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-name {
  font-size: 14px;
  color: #5d6f69;
}

.logout-btn {
  font-size: 13px;
  color: #888;
}

.workspace-content {
  padding: 0 24px 24px;
}

@media (max-width: 900px) {
  .workspace-shell {
    flex-direction: column;
  }

  .workspace-aside {
    width: 100% !important;
  }

  .workspace-header {
    padding: 18px 20px 8px;
  }

  .workspace-content {
    padding: 0 14px 14px;
  }
}
</style>
