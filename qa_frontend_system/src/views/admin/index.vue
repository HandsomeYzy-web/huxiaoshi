<template>
  <section class="admin-page">
    <div class="panel-body">
      <AdminRolesPanel v-if="activePanel === 'roles'" />
      <AdminUsersPanel v-else-if="activePanel === 'users'" />
      <AdminPermissionsPanel v-else-if="activePanel === 'permissions'" />
      <AdminKbAccessPanel v-else-if="activePanel === 'kb-access'" />
      <AdminModelsPanel v-else-if="activePanel === 'models'" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import AdminKbAccessPanel from '../../components/admin/AdminKbAccessPanel.vue'
import AdminModelsPanel from '../../components/admin/AdminModelsPanel.vue'
import AdminPermissionsPanel from '../../components/admin/AdminPermissionsPanel.vue'
import AdminRolesPanel from '../../components/admin/AdminRolesPanel.vue'
import AdminUsersPanel from '../../components/admin/AdminUsersPanel.vue'

const route = useRoute()

const activePanel = computed(() => {
  const segments = route.path.split('/')
  return segments[segments.length - 1] || 'roles'
})
</script>

<style scoped>
.admin-page {
  min-height: 100%;
}

.panel-body {
  height: 100%;
}
</style>
