<template>
  <section class="admin-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">用户管理</div>
        <div class="panel-subtitle">查看用户并为用户绑定角色。</div>
      </div>
      <div class="header-tools">
        <el-input v-model="keyword" clearable placeholder="搜索用户名或邮箱" style="width: 240px" />
      </div>
    </div>

    <el-table :data="pagedUsers" v-loading="loading" border class="panel-table">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" width="180" />
      <el-table-column prop="email" label="邮箱" min-width="240" />
      <el-table-column label="角色" min-width="320">
        <template #default="{ row }">
          <div class="tag-list">
            <el-tag v-for="role in row.roles" :key="role.id" size="small">{{ role.name }}</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openUserRoles(row)">绑定角色</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-bar">
      <el-pagination
        background
        layout="total, sizes, prev, pager, next"
        :total="filteredUsers.length"
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        @current-change="handlePageChange"
        @size-change="handlePageSizeChange"
      />
    </div>

    <el-dialog v-model="userRolesDialogVisible" :title="`绑定角色 - ${editingUser?.username || ''}`" width="420px">
      <el-checkbox-group v-model="selectedRoleIds">
        <div v-for="item in roles" :key="item.id" class="checkbox-row">
          <el-checkbox :label="item.id" :value="item.id">{{ item.name }}</el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="userRolesDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveUserRoles">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { listAdminUsers, listRoles, setUserRoles, type AdminUser, type Role } from '../../api/admin'

const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(10)

const users = ref<AdminUser[]>([])
const roles = ref<Role[]>([])
const userRolesDialogVisible = ref(false)
const editingUser = ref<AdminUser | null>(null)
const selectedRoleIds = ref<number[]>([])

const filteredUsers = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  return text
    ? users.value.filter(item => item.username.toLowerCase().includes(text) || item.email.toLowerCase().includes(text))
    : users.value
})

const pagedUsers = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredUsers.value.slice(start, start + pageSize.value)
})

watch(keyword, () => {
  page.value = 1
})

async function loadData() {
  loading.value = true
  try {
    const [userList, roleList] = await Promise.all([listAdminUsers(), listRoles()])
    users.value = userList
    roles.value = roleList
  } finally {
    loading.value = false
  }
}

function openUserRoles(row: AdminUser) {
  editingUser.value = row
  selectedRoleIds.value = row.roles.map(item => item.id)
  userRolesDialogVisible.value = true
}

async function saveUserRoles() {
  if (!editingUser.value) return
  saving.value = true
  try {
    await setUserRoles(editingUser.value.id, selectedRoleIds.value)
    userRolesDialogVisible.value = false
    ElMessage.success('用户角色已更新')
    await loadData()
  } finally {
    saving.value = false
  }
}

function handlePageChange(nextPage: number) {
  page.value = nextPage
}

function handlePageSizeChange(nextPageSize: number) {
  pageSize.value = nextPageSize
  page.value = 1
}

onMounted(() => {
  void loadData()
})
</script>

<style scoped>
.admin-card {
  padding: 20px;
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 247, 0.96));
  box-shadow: 0 16px 38px rgba(25, 42, 37, 0.08);
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.panel-title {
  font-size: 20px;
  font-weight: 800;
  color: #173229;
}

.panel-subtitle {
  margin-top: 6px;
  color: #70827b;
  font-size: 13px;
}

.panel-table {
  border-radius: 18px;
  overflow: hidden;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.checkbox-row {
  margin-bottom: 8px;
}
</style>
