<template>
  <section class="admin-page">
    <div class="hero">
      <div>
        <p class="eyebrow">系统管理台</p>
        <h1 class="title">统一管理角色、用户、权限与模型配置</h1>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="admin-tabs">
      <el-tab-pane v-if="authStore.hasPermission('role.view')" label="角色管理" name="roles">
        <AdminRolesPanel />
      </el-tab-pane>
      <el-tab-pane v-if="authStore.hasPermission('user.view')" label="用户管理" name="users">
        <AdminUsersPanel />
      </el-tab-pane>
      <el-tab-pane v-if="authStore.hasPermission('permission.view')" label="权限管理" name="permissions">
        <AdminPermissionsPanel />
      </el-tab-pane>
      <el-tab-pane v-if="authStore.hasPermission('kb_access.view')" label="知识库访问" name="kb-access">
        <AdminKbAccessPanel />
      </el-tab-pane>
      <el-tab-pane v-if="authStore.hasPermission('model.view')" label="模型配置" name="models">
        <AdminModelsPanel />
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'

import AdminKbAccessPanel from '../../components/admin/AdminKbAccessPanel.vue'
import AdminModelsPanel from '../../components/admin/AdminModelsPanel.vue'
import AdminPermissionsPanel from '../../components/admin/AdminPermissionsPanel.vue'
import AdminRolesPanel from '../../components/admin/AdminRolesPanel.vue'
import AdminUsersPanel from '../../components/admin/AdminUsersPanel.vue'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const activeTab = ref('roles')

const availableTabs = computed(() => {
  const tabs: string[] = []
  if (authStore.hasPermission('role.view')) tabs.push('roles')
  if (authStore.hasPermission('user.view')) tabs.push('users')
  if (authStore.hasPermission('permission.view')) tabs.push('permissions')
  if (authStore.hasPermission('kb_access.view')) tabs.push('kb-access')
  if (authStore.hasPermission('model.view')) tabs.push('models')
  return tabs
})

watchEffect(() => {
  if (!availableTabs.value.includes(activeTab.value)) {
    activeTab.value = availableTabs.value[0] || 'roles'
  }
})
</script>

<style scoped>
.admin-page {
  min-height: 100%;
  padding: 24px;
  background:
    radial-gradient(circle at top right, rgba(61, 142, 103, 0.16), transparent 24%),
    radial-gradient(circle at left center, rgba(224, 187, 106, 0.18), transparent 18%),
    linear-gradient(180deg, #f4f7f1 0%, #edf2eb 100%);
}

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
  padding: 28px;
  border: 1px solid rgba(33, 72, 57, 0.08);
  border-radius: 28px;
  background: linear-gradient(135deg, rgba(255, 253, 248, 0.98), rgba(244, 249, 244, 0.98));
  box-shadow: 0 24px 60px rgba(27, 56, 45, 0.08);
}

.eyebrow {
  margin: 0 0 10px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  color: #5a7a67;
}

.title {
  margin: 0;
  max-width: 720px;
  font-size: 32px;
  line-height: 1.2;
  color: #18342a;
}

.subtitle {
  margin: 12px 0 0;
  max-width: 760px;
  font-size: 14px;
  line-height: 1.8;
  color: #6d8076;
}

.hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
}

.badge {
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(24, 52, 42, 0.06);
  color: #1a4637;
  font-size: 13px;
  font-weight: 600;
}

.admin-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.admin-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: rgba(24, 52, 42, 0.08);
}

.admin-tabs :deep(.el-tabs__item) {
  height: 44px;
  color: #60766c;
  font-weight: 600;
}

.admin-tabs :deep(.el-tabs__item.is-active) {
  color: #1d5945;
}

.admin-tabs :deep(.el-tabs__active-bar) {
  background: linear-gradient(90deg, #2b7a5e, #d59c3e);
}

@media (max-width: 900px) {
  .hero {
    flex-direction: column;
  }

  .hero-badges {
    justify-content: flex-start;
  }
}
</style>
