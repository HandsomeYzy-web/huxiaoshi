<template>
  <section class="admin-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">角色管理</div>
      </div>
      <el-button type="primary" @click="openRoleCreate">新建角色</el-button>
    </div>

    <el-table :data="roles" v-loading="loading" border class="panel-table">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="code" label="编码" width="180" />
      <el-table-column prop="name" label="名称" width="180" />
      <el-table-column prop="description" label="描述" min-width="200" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="权限数" width="100">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.permissions.length }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openRolePerms(row)">配置权限</el-button>
          <el-button size="small" type="warning" :disabled="row.role_type === 'system'" @click="openRoleEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" :disabled="row.role_type === 'system'" @click="removeRole(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="roleDialogVisible" :title="editingRoleId ? '编辑角色' : '新建角色'" width="420px">
      <el-form :model="roleForm" label-width="80px">
        <el-form-item label="编码"><el-input v-model="roleForm.code" :disabled="!!editingRoleId" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="roleForm.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="roleForm.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="rolePermsDialogVisible" :title="permDialogTitle" width="680px">
      <div class="perm-tree-toolbar">
        <el-button size="small" @click="handleCheckAll">全选</el-button>
        <el-button size="small" @click="handleUncheckAll">全不选</el-button>
        <span class="perm-count">已选 {{ selectedPermissionCodes.length }} 项</span>
      </div>
      <el-scrollbar max-height="480px">
        <el-tree
          ref="permTreeRef"
          :data="permissionTree"
          :props="{ label: 'name', children: 'children' }"
          node-key="code"
          show-checkbox
          default-expand-all
          @check="handleTreeCheck"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <span class="tree-node-name">{{ data.name }}</span>
              <span class="tree-node-code">{{ data.code }}</span>
            </span>
          </template>
        </el-tree>
      </el-scrollbar>
      <template #footer>
        <el-button @click="rolePermsDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRolePerms">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox, type ElTree } from 'element-plus'

import {
  createRole,
  deleteRole,
  getFullPermissionTree,
  listRoles,
  setRolePermissions,
  updateRole,
  type PermissionTreeNode,
  type Role,
} from '../../api/admin'

const loading = ref(false)
const saving = ref(false)
const roles = ref<Role[]>([])
const permissionTree = ref<PermissionTreeNode[]>([])

const roleDialogVisible = ref(false)
const editingRoleId = ref<number | null>(null)
const roleForm = ref({ code: '', name: '', description: '' })

const rolePermsDialogVisible = ref(false)
const editingRole = ref<Role | null>(null)
const selectedPermissionCodes = ref<string[]>([])
const permTreeRef = ref<InstanceType<typeof ElTree> | null>(null)

const permDialogTitle = computed(() => `配置权限 - ${editingRole.value?.name ?? ''}`)

async function loadData() {
  loading.value = true
  try {
    const [roleList, tree] = await Promise.all([listRoles(), getFullPermissionTree()])
    roles.value = roleList
    permissionTree.value = tree
  } finally {
    loading.value = false
  }
}

function openRoleCreate() {
  editingRoleId.value = null
  roleForm.value = { code: '', name: '', description: '' }
  roleDialogVisible.value = true
}

function openRoleEdit(row: Role) {
  editingRoleId.value = row.id
  roleForm.value = { code: row.code, name: row.name, description: row.description || '' }
  roleDialogVisible.value = true
}

async function saveRole() {
  saving.value = true
  try {
    if (editingRoleId.value) {
      await updateRole(editingRoleId.value, { name: roleForm.value.name, description: roleForm.value.description })
    } else {
      await createRole(roleForm.value)
    }
    roleDialogVisible.value = false
    ElMessage.success('角色已保存')
    await loadData()
  } finally {
    saving.value = false
  }
}

async function removeRole(row: Role) {
  await ElMessageBox.confirm(`确认删除角色"${row.name}"吗？`, '删除角色', { type: 'warning' })
  await deleteRole(row.id)
  ElMessage.success('角色已删除')
  await loadData()
}

function collectAllCodes(nodes: PermissionTreeNode[]): string[] {
  const codes: string[] = []
  for (const n of nodes) {
    codes.push(n.code)
    if (n.children?.length) codes.push(...collectAllCodes(n.children))
  }
  return codes
}

function getLeafCodes(nodes: PermissionTreeNode[]): string[] {
  const leaves: string[] = []
  for (const n of nodes) {
    if (!n.children?.length) {
      leaves.push(n.code)
    } else {
      leaves.push(...getLeafCodes(n.children))
    }
  }
  return leaves
}

function openRolePerms(row: Role) {
  editingRole.value = row
  const leafCodes = getLeafCodes(permissionTree.value)
  const roleLeaves = row.permissions.filter(c => leafCodes.includes(c))
  selectedPermissionCodes.value = roleLeaves
  rolePermsDialogVisible.value = true
  setTimeout(() => {
    permTreeRef.value?.setCheckedKeys(roleLeaves)
  }, 0)
}

function handleTreeCheck() {
  if (!permTreeRef.value) return
  const checked = permTreeRef.value.getCheckedKeys(false) as string[]
  const halfChecked = permTreeRef.value.getHalfCheckedKeys() as string[]
  selectedPermissionCodes.value = [...checked, ...halfChecked]
}

function handleCheckAll() {
  const allCodes = collectAllCodes(permissionTree.value)
  permTreeRef.value?.setCheckedKeys(allCodes)
  selectedPermissionCodes.value = allCodes
}

function handleUncheckAll() {
  permTreeRef.value?.setCheckedKeys([])
  selectedPermissionCodes.value = []
}

async function saveRolePerms() {
  if (!editingRole.value) return
  saving.value = true
  try {
    await setRolePermissions(editingRole.value.id, selectedPermissionCodes.value)
    rolePermsDialogVisible.value = false
    ElMessage.success('角色权限已更新')
    await loadData()
  } finally {
    saving.value = false
  }
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

.perm-tree-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e8ede8;
}

.perm-count {
  margin-left: auto;
  font-size: 13px;
  color: #70827b;
}

.tree-node {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.tree-node-name {
  font-weight: 600;
  color: #20362f;
}

.tree-node-code {
  font-size: 12px;
  color: #8fa69d;
}

:deep(.el-tree-node__content) {
  height: 36px;
}

:deep(.el-tree-node__expand-icon) {
  font-size: 14px;
}
</style>