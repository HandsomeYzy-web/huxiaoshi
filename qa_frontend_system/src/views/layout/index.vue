<template>
  <el-container class="workspace-shell">
    <el-aside class="workspace-aside" width="260px">
      <div class="brand-block">
        <div class="brand-mark">QA</div>
        <div>
          <div class="brand-title">管理工作台</div>
          <div class="brand-subtitle">知识库、文件与召回验证</div>
        </div>
      </div>

      <el-menu
        class="workspace-menu"
        :default-active="activePath"
        router
        background-color="transparent"
        text-color="#adc2bd"
        active-text-color="#102a24"
      >
        <el-menu-item
          v-for="item in visibleNavItems"
          :key="item.path"
          :index="item.path"
          class="workspace-menu-item"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>

      <!-- 管理员专属入口 -->
      <div v-if="authStore.isAdmin" class="admin-section">
        <div class="section-divider">管理员</div>
        <el-menu
          class="workspace-menu"
          :default-active="activePath"
          router
          background-color="transparent"
          text-color="#adc2bd"
          active-text-color="#102a24"
        >
          <el-menu-item index="/admin" class="workspace-menu-item">
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </el-menu-item>
        </el-menu>
      </div>
    </el-aside>

    <el-container class="workspace-main">
      <el-header class="workspace-header">
        <div>
          <div class="header-title">{{ currentTitle }}</div>
        </div>
        <div class="header-user" v-if="authStore.user">
          <el-tag v-if="authStore.isAdmin" type="danger" size="small" style="margin-right:8px">管理员</el-tag>
          <span class="user-name">{{ authStore.user.username }}</span>
          <el-button link size="small" @click="handleLogout" class="logout-btn">退出登录</el-button>
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
import { DataAnalysis, FolderOpened, Files, ChatLineRound, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const allNavItems = [
  { path: '/workspace/overview', label: '工作台总览', icon: DataAnalysis, permission: null },
  { path: '/workspace/knowledge-bases', label: '知识库管理', icon: FolderOpened, permission: 'kb.manage' },
  { path: '/workspace/files', label: '文件处理', icon: Files, permission: 'file.manage' },
  { path: '/workspace/qa-test', label: '召回测试', icon: ChatLineRound, permission: 'qa.test' },
]

const visibleNavItems = computed(() =>
  allNavItems.filter(item => !item.permission || authStore.hasPermission(item.permission))
)

const activePath = computed(() => route.path)
const currentTitle = computed(() => String(route.meta.title || '管理工作台'))

function handleLogout() {
  authStore.logout()
  router.push('/login')
}</script>

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
  background:
    linear-gradient(180deg, #14231f 0%, #1a322d 52%, #1d4540 100%);
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
  letter-spacing: 0.04em;
}

.brand-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(246, 246, 238, 0.7);
}

.workspace-menu {
  border-right: none;
}

:deep(.workspace-menu-item) {
  height: 46px;
  margin-bottom: 8px;
  border-radius: 14px;
  font-weight: 600;
}

:deep(.workspace-menu-item.is-active) {
  background: linear-gradient(135deg, #f2d98d 0%, #e8f0cf 100%);
}

.footer-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #f2d98d;
}

.footer-note {
  margin-top: 10px;
  line-height: 1.6;
  font-size: 13px;
  color: rgba(246, 246, 238, 0.75);
}

.workspace-main {
  min-width: 0;
}

.workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28px 32px 10px;
  background: transparent;
}

.header-user {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-name {
  font-size: 14px;
  color: #5d6f69;
  font-weight: 500;
}

.logout-btn {
  font-size: 13px;
  color: #888;
}

.header-title {
  font-size: 28px;
  line-height: 1.15;
  font-weight: 800;
  color: #16312a;
}

.header-subtitle {
  margin-top: 8px;
  font-size: 14px;
  color: #5d6f69;
}

.workspace-content {
  padding: 0 24px 24px;
}

.admin-section {
  margin-top: 16px;
}

.section-divider {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: rgba(242, 217, 141, 0.6);
  padding: 8px 16px 4px;
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
