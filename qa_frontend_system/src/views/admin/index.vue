<template>
  <div class="admin-container">
    <el-tabs v-model="activeTab" class="admin-tabs">
      <!-- ─── 角色管理 Tab ─────────────────────────────────── -->
      <el-tab-pane label="角色管理" name="roles">
        <div class="tab-header">
          <h3>角色列表</h3>
          <el-button type="primary" @click="openCreateRole">新建角色</el-button>
        </div>

        <el-table :data="roles" v-loading="rolesLoading" border stripe>
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="name" label="角色名称" width="140" />
          <el-table-column prop="description" label="描述" />
          <el-table-column label="权限" min-width="200">
            <template #default="{ row }">
              <el-tag
                v-for="code in row.permissions"
                :key="code"
                size="small"
                class="perm-tag"
              >{{ permNameMap[code] || code }}</el-tag>
              <span v-if="!row.permissions.length" class="empty-tip">无权限</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_system ? 'danger' : 'info'" size="small">
                {{ row.is_system ? '系统' : '自定义' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEditPermissions(row)">配置权限</el-button>
              <el-button
                size="small"
                type="warning"
                :disabled="row.is_system"
                @click="openEditRole(row)"
              >编辑</el-button>
              <el-button
                size="small"
                type="danger"
                :disabled="row.is_system"
                @click="handleDeleteRole(row)"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ─── 用户管理 Tab ─────────────────────────────────── -->
      <el-tab-pane label="用户管理" name="users">
        <div class="tab-header">
          <h3>用户列表</h3>
          <el-input
            v-model="userSearch"
            placeholder="搜索用户名..."
            style="width: 240px"
            clearable
          />
        </div>

        <el-table :data="filteredUsers" v-loading="usersLoading" border stripe>
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="username" label="用户名" width="140" />
          <el-table-column prop="email" label="邮箱" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
                {{ row.is_active ? '正常' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="管理员" width="90">
            <template #default="{ row }">
              <el-switch
                :model-value="row.is_admin"
                @change="(val: boolean) => handleToggleAdmin(row, val)"
                :disabled="row.id === authStore.user?.id"
              />
            </template>
          </el-table-column>
          <el-table-column label="当前角色">
            <template #default="{ row }">
              <el-tag v-for="r in row.roles" :key="r.id" size="small" class="perm-tag">
                {{ r.name }}
              </el-tag>
              <span v-if="!row.roles.length" class="empty-tip">未分配角色</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="openAssignRoles(row)">
                分配角色
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ─── 知识库访问控制 Tab ───────────────────────────── -->
      <el-tab-pane label="知识库访问控制" name="kb-access">
        <div class="tab-header">
          <h3>知识库可见性配置</h3>
          <span class="tip-text">配置每个知识库对哪些角色可见（可检索）</span>
        </div>

        <el-table :data="kbAccessList" v-loading="kbAccessLoading" border stripe>
          <el-table-column prop="kb_id" label="知识库ID" width="100" />
          <el-table-column label="知识库名称">
            <template #default="{ row }">
              {{ kbNameMap[row.kb_id] || `KB #${row.kb_id}` }}
            </template>
          </el-table-column>
          <el-table-column label="可访问角色">
            <template #default="{ row }">
              <el-tag
                v-for="rid in row.accessible_role_ids"
                :key="rid"
                size="small"
                type="success"
                class="perm-tag"
              >{{ roleNameMap[rid] || `角色 #${rid}` }}</el-tag>
              <span v-if="!row.accessible_role_ids.length" class="empty-tip">
                所有用户不可访问
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="openEditKBAccess(row)">
                配置
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ─── 新建/编辑角色 Dialog ──────────────────────────── -->
    <el-dialog v-model="roleDialogVisible" :title="roleDialogTitle" width="440px">
      <el-form :model="roleForm" label-width="80px">
        <el-form-item label="角色名称" required>
          <el-input v-model="roleForm.name" placeholder="如：senior_user" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="roleForm.description" type="textarea" rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitRoleForm">确定</el-button>
      </template>
    </el-dialog>

    <!-- ─── 配置角色权限 Dialog ────────────────────────────── -->
    <el-dialog v-model="permDialogVisible" :title="`配置权限 — ${editingRole?.name}`" width="560px">
      <div v-for="mod in permissionModules" :key="mod" class="perm-module">
        <div class="perm-module-title">{{ moduleLabel(mod) }}</div>
        <el-checkbox-group v-model="selectedPermCodes">
          <el-checkbox
            v-for="p in permsByModule[mod]"
            :key="p.code"
            :label="p.code"
            :value="p.code"
          >
            <span>{{ p.name }}</span>
            <span class="perm-desc">{{ p.description }}</span>
          </el-checkbox>
        </el-checkbox-group>
      </div>
      <template #footer>
        <el-button @click="permDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitPermissions">保存</el-button>
      </template>
    </el-dialog>

    <!-- ─── 分配用户角色 Dialog ────────────────────────────── -->
    <el-dialog v-model="userRoleDialogVisible" :title="`分配角色 — ${editingUser?.username}`" width="440px">
      <el-checkbox-group v-model="selectedRoleIds">
        <div v-for="r in roles" :key="r.id" class="role-item">
          <el-checkbox :label="r.id" :value="r.id">
            <span class="role-name">{{ r.name }}</span>
            <span class="perm-desc">{{ r.description }}</span>
          </el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="userRoleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitUserRoles">保存</el-button>
      </template>
    </el-dialog>

    <!-- ─── 配置知识库访问 Dialog ──────────────────────────── -->
    <el-dialog v-model="kbAccessDialogVisible" :title="`配置知识库访问 — ${kbNameMap[editingKB?.kb_id ?? 0]}`" width="440px">
      <p class="dialog-tip">选择哪些角色可以检索此知识库：</p>
      <el-checkbox-group v-model="selectedKBRoleIds">
        <div v-for="r in roles" :key="r.id" class="role-item">
          <el-checkbox :label="r.id" :value="r.id">{{ r.name }}</el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="kbAccessDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitKBAccess">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  listRoles, createRole, updateRole, deleteRole,
  setRolePermissions, listPermissions, listAdminUsers,
  setUserRoles, setUserAdmin, getAllKBAccess, setKBAccess,
} from '../../api/admin'
import { getKnowledgeBases } from '../../api/kb'
import type { Role, Permission, AdminUser, KBAccessInfo } from '../../api/admin'

const authStore = useAuthStore()
const activeTab = ref('roles')
const saving = ref(false)

// ─── Roles ────────────────────────────────────────────────────
const roles = ref<Role[]>([])
const rolesLoading = ref(false)
const allPermissions = ref<Permission[]>([])

const permNameMap = computed(() => {
  const m: Record<string, string> = {}
  allPermissions.value.forEach(p => { m[p.code] = p.name })
  return m
})
const roleNameMap = computed(() => {
  const m: Record<number, string> = {}
  roles.value.forEach(r => { m[r.id] = r.name })
  return m
})
const permissionModules = computed(() => [...new Set(allPermissions.value.map(p => p.module))])
const permsByModule = computed(() => {
  const m: Record<string, Permission[]> = {}
  allPermissions.value.forEach(p => {
    if (!m[p.module]) m[p.module] = []
    m[p.module].push(p)
  })
  return m
})
const moduleLabel = (mod: string) => ({
  kb: '知识库', file: '文件', chat: '聊天', qa: '问答测试', admin: '管理功能'
}[mod] || mod)

async function loadRoles() {
  rolesLoading.value = true
  try {
    roles.value = await listRoles()
  } finally {
    rolesLoading.value = false
  }
}

// ─── Role CRUD ────────────────────────────────────────────────
const roleDialogVisible = ref(false)
const roleDialogTitle = ref('新建角色')
const roleForm = ref({ name: '', description: '' })
const editingRoleId = ref<number | null>(null)

function openCreateRole() {
  roleDialogTitle.value = '新建角色'
  editingRoleId.value = null
  roleForm.value = { name: '', description: '' }
  roleDialogVisible.value = true
}

function openEditRole(role: Role) {
  roleDialogTitle.value = '编辑角色'
  editingRoleId.value = role.id
  roleForm.value = { name: role.name, description: role.description || '' }
  roleDialogVisible.value = true
}

async function submitRoleForm() {
  if (!roleForm.value.name.trim()) { ElMessage.warning('请输入角色名称'); return }
  saving.value = true
  try {
    if (editingRoleId.value) {
      await updateRole(editingRoleId.value, roleForm.value)
      ElMessage.success('角色更新成功')
    } else {
      await createRole(roleForm.value)
      ElMessage.success('角色创建成功')
    }
    roleDialogVisible.value = false
    await loadRoles()
  } finally {
    saving.value = false
  }
}

async function handleDeleteRole(role: Role) {
  await ElMessageBox.confirm(`确定删除角色「${role.name}」吗？`, '确认删除', { type: 'warning' })
  await deleteRole(role.id)
  ElMessage.success('删除成功')
  await loadRoles()
}

// ─── Role Permissions ─────────────────────────────────────────
const permDialogVisible = ref(false)
const editingRole = ref<Role | null>(null)
const selectedPermCodes = ref<string[]>([])

function openEditPermissions(role: Role) {
  editingRole.value = role
  selectedPermCodes.value = [...role.permissions]
  permDialogVisible.value = true
}

async function submitPermissions() {
  if (!editingRole.value) return
  saving.value = true
  try {
    await setRolePermissions(editingRole.value.id, selectedPermCodes.value)
    ElMessage.success('权限配置已保存')
    permDialogVisible.value = false
    await loadRoles()
  } finally {
    saving.value = false
  }
}

// ─── Users ────────────────────────────────────────────────────
const users = ref<AdminUser[]>([])
const usersLoading = ref(false)
const userSearch = ref('')
const filteredUsers = computed(() =>
  userSearch.value
    ? users.value.filter(u => u.username.includes(userSearch.value))
    : users.value
)

async function loadUsers() {
  usersLoading.value = true
  try {
    users.value = await listAdminUsers()
  } finally {
    usersLoading.value = false
  }
}

async function handleToggleAdmin(user: AdminUser, val: boolean) {
  await setUserAdmin(user.id, val)
  user.is_admin = val
  ElMessage.success(val ? '已设为管理员' : '已取消管理员')
  await loadUsers()
}

// User Role Assignment
const userRoleDialogVisible = ref(false)
const editingUser = ref<AdminUser | null>(null)
const selectedRoleIds = ref<number[]>([])

function openAssignRoles(user: AdminUser) {
  editingUser.value = user
  selectedRoleIds.value = user.roles.map(r => r.id)
  userRoleDialogVisible.value = true
}

async function submitUserRoles() {
  if (!editingUser.value) return
  saving.value = true
  try {
    await setUserRoles(editingUser.value.id, selectedRoleIds.value)
    ElMessage.success('角色分配成功')
    userRoleDialogVisible.value = false
    await loadUsers()
  } finally {
    saving.value = false
  }
}

// ─── KB Access ────────────────────────────────────────────────
const kbAccessList = ref<KBAccessInfo[]>([])
const kbAccessLoading = ref(false)
const kbNameMap = ref<Record<number, string>>({})

async function loadKBAccess() {
  kbAccessLoading.value = true
  try {
    const [accessData, kbData] = await Promise.all([getAllKBAccess(), getKnowledgeBases()])
    kbAccessList.value = accessData
    kbData.forEach(kb => { kbNameMap.value[kb.id] = kb.name })
    // 补充名称映射中已有 access 但可能不在 kbData 里的
    accessData.forEach(a => {
      if (!kbNameMap.value[a.kb_id]) kbNameMap.value[a.kb_id] = `KB #${a.kb_id}`
    })
  } finally {
    kbAccessLoading.value = false
  }
}

const kbAccessDialogVisible = ref(false)
const editingKB = ref<KBAccessInfo | null>(null)
const selectedKBRoleIds = ref<number[]>([])

function openEditKBAccess(row: KBAccessInfo) {
  editingKB.value = row
  selectedKBRoleIds.value = [...row.accessible_role_ids]
  kbAccessDialogVisible.value = true
}

async function submitKBAccess() {
  if (!editingKB.value) return
  saving.value = true
  try {
    await setKBAccess(editingKB.value.kb_id, selectedKBRoleIds.value)
    ElMessage.success('访问控制配置已保存')
    kbAccessDialogVisible.value = false
    await loadKBAccess()
  } finally {
    saving.value = false
  }
}

// ─── Init ─────────────────────────────────────────────────────
onMounted(async () => {
  const [, perms] = await Promise.all([
    loadRoles(),
    listPermissions(),
  ])
  allPermissions.value = perms
  await Promise.all([loadUsers(), loadKBAccess()])
})
</script>

<style scoped>
.admin-container {
  padding: 16px;
}
.admin-tabs {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.tab-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.perm-tag {
  margin: 2px 3px 2px 0;
}
.empty-tip {
  color: #999;
  font-size: 12px;
}
.tip-text {
  font-size: 13px;
  color: #666;
}
.perm-module {
  margin-bottom: 16px;
}
.perm-module-title {
  font-weight: 600;
  margin-bottom: 8px;
  color: #333;
  border-left: 3px solid #409eff;
  padding-left: 8px;
}
.perm-desc {
  font-size: 12px;
  color: #999;
  margin-left: 6px;
}
.role-item {
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}
.role-name {
  font-weight: 500;
}
.dialog-tip {
  color: #666;
  margin-bottom: 12px;
  font-size: 14px;
}
</style>
