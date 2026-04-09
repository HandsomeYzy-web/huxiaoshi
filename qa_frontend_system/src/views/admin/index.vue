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

      <!-- ─── 模型配置 Tab ─────────────────────────────────── -->
      <el-tab-pane label="模型配置" name="models">
        <div class="tab-header">
          <h3>模型管理</h3>
          <div style="display: flex; gap: 10px; align-items: center">
            <el-select v-model="modelTypeFilter" placeholder="全部类型" clearable style="width: 140px" @change="loadModels">
              <el-option label="LLM 大模型" value="llm" />
              <el-option label="Embedding 向量" value="embedding" />
              <el-option label="Rerank 精排" value="rerank" />
            </el-select>
            <el-button type="primary" @click="openCreateModel">新增模型</el-button>
            <el-button type="warning" :loading="rebuilding" @click="handleRebuildAllKBs">
              重建所有知识库
            </el-button>
          </div>
        </div>

        <el-table :data="models" v-loading="modelsLoading" border stripe>
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="name" label="显示名称" width="160" />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag :type="modelTypeTagMap[row.model_type] || 'info'" size="small">
                {{ modelTypeLabel[row.model_type] || row.model_type }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="供应商" width="130">
            <template #default="{ row }">
              {{ providerDisplayName(row.provider) }}
            </template>
          </el-table-column>
          <el-table-column prop="model_name" label="模型标识" min-width="180" show-overflow-tooltip />
          <el-table-column prop="api_base_url" label="API Base URL" min-width="200" show-overflow-tooltip />
          <el-table-column prop="api_key_masked" label="API Key" width="140" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? '激活' : '未激活' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                type="success"
                :disabled="row.is_active"
                @click="handleActivateModel(row)"
              >激活</el-button>
              <el-button size="small" type="warning" @click="openEditModel(row)">编辑</el-button>
              <el-button
                size="small"
                type="danger"
                :disabled="row.is_active"
                @click="handleDeleteModel(row)"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="model-hint">
          <el-icon><InfoFilled /></el-icon>
          <span>每种类型（LLM / Embedding / Rerank）同时只能有一个激活的模型配置。激活新模型会自动关闭同类型的旧模型。</span>
        </div>
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

    <!-- ─── 新建/编辑模型配置 Dialog ──────────────────────── -->
    <el-dialog v-model="modelDialogVisible" :title="modelDialogTitle" width="600px">
      <el-form :model="modelForm" label-width="110px">
        <el-form-item label="模型类型" required>
          <el-select v-model="modelForm.model_type" placeholder="请选择" :disabled="!!editingModelId" style="width: 100%">
            <el-option label="LLM 大模型" value="llm" />
            <el-option label="Embedding 向量" value="embedding" />
            <el-option label="Rerank 精排" value="rerank" />
          </el-select>
        </el-form-item>
        <el-form-item label="供应商" required>
          <el-select v-model="modelForm.provider" placeholder="请选择" filterable style="width: 100%">
            <el-option
              v-for="p in filteredProviders"
              :key="p.provider"
              :label="p.display_name"
              :value="p.provider"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="显示名称" required>
          <el-input v-model="modelForm.name" placeholder="如：GPT-4o 生产环境" />
        </el-form-item>
        <el-form-item label="模型标识" required>
          <el-input v-model="modelForm.model_name" placeholder="如：gpt-4o / qwen-plus / bge-large-zh-v1.5" />
        </el-form-item>
        <el-form-item label="API Base URL" required>
          <el-input v-model="modelForm.api_base_url" placeholder="如：https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="API Key" required>
          <el-input
            v-model="modelForm.api_key"
            :placeholder="editingModelId ? '留空则不修改' : '请输入 API Key'"
            show-password
          />
        </el-form-item>
        <el-form-item label="额外参数">
          <el-input
            v-model="modelForm.extra_params"
            type="textarea"
            :rows="3"
            placeholder='可选，JSON 格式，如：{"temperature": 0.1, "max_tokens": 4096}'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitModelForm">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '../../stores/auth'
import {
  listRoles, createRole, updateRole, deleteRole,
  setRolePermissions, listPermissions, listAdminUsers,
  setUserRoles, setUserAdmin, getAllKBAccess, setKBAccess,
  listModelConfigs, createModelConfig, updateModelConfig,
  deleteModelConfig, activateModelConfig, listModelProviders,
  rebuildAllKnowledgeBases,
} from '../../api/admin'
import { getKnowledgeBases } from '../../api/kb'
import type {
  Role, Permission, AdminUser, KBAccessInfo,
  ModelConfig, ModelConfigCreate, ModelConfigUpdate, ModelProviderInfo,
  ModelActivateResponse,
} from '../../api/admin'

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

// ─── Models ───────────────────────────────────────────────────
const models = ref<ModelConfig[]>([])
const modelsLoading = ref(false)
const modelTypeFilter = ref('')
const providers = ref<ModelProviderInfo[]>([])
const rebuilding = ref(false)
const modelTypeLabel: Record<string, string> = { llm: 'LLM', embedding: 'Embedding', rerank: 'Rerank' }
const modelTypeTagMap: Record<string, string> = { llm: 'danger', embedding: 'warning', rerank: '' }

const filteredProviders = computed(() => {
  if (!modelForm.value.model_type) return providers.value
  return providers.value.filter(p => p.supported_types.includes(modelForm.value.model_type))
})

function providerDisplayName(code: string): string {
  const p = providers.value.find(item => item.provider === code)
  return p ? p.display_name : code
}

async function loadModels() {
  modelsLoading.value = true
  try {
    models.value = await listModelConfigs(modelTypeFilter.value || undefined)
  } finally {
    modelsLoading.value = false
  }
}

// Model CRUD
const modelDialogVisible = ref(false)
const modelDialogTitle = ref('新增模型')
const editingModelId = ref<number | null>(null)
const modelForm = ref<ModelConfigCreate>({
  model_type: 'llm',
  provider: '',
  name: '',
  model_name: '',
  api_base_url: '',
  api_key: '',
  extra_params: '',
})

function openCreateModel() {
  modelDialogTitle.value = '新增模型'
  editingModelId.value = null
  modelForm.value = {
    model_type: 'llm',
    provider: '',
    name: '',
    model_name: '',
    api_base_url: '',
    api_key: '',
    extra_params: '',
  }
  modelDialogVisible.value = true
}

function openEditModel(row: ModelConfig) {
  modelDialogTitle.value = '编辑模型'
  editingModelId.value = row.id
  modelForm.value = {
    model_type: row.model_type,
    provider: row.provider,
    name: row.name,
    model_name: row.model_name,
    api_base_url: row.api_base_url,
    api_key: '', // 不回显密钥
    extra_params: row.extra_params || '',
  }
  modelDialogVisible.value = true
}

async function submitModelForm() {
  const f = modelForm.value
  if (!f.model_type || !f.provider || !f.name || !f.model_name || !f.api_base_url) {
    ElMessage.warning('请填写所有必填项')
    return
  }
  if (!editingModelId.value && !f.api_key) {
    ElMessage.warning('请输入 API Key')
    return
  }
  // 校验 extra_params 是否为合法 JSON
  if (f.extra_params) {
    try {
      JSON.parse(f.extra_params)
    } catch {
      ElMessage.warning('额外参数必须是合法的 JSON 格式')
      return
    }
  }
  saving.value = true
  try {
    if (editingModelId.value) {
      const updateData: ModelConfigUpdate = {
        name: f.name,
        model_name: f.model_name,
        api_base_url: f.api_base_url,
        extra_params: f.extra_params || undefined,
      }
      if (f.api_key) updateData.api_key = f.api_key
      await updateModelConfig(editingModelId.value, updateData)
      ElMessage.success('模型配置更新成功')
    } else {
      await createModelConfig(f)
      ElMessage.success('模型配置创建成功')
    }
    modelDialogVisible.value = false
    await loadModels()
  } finally {
    saving.value = false
  }
}

async function handleActivateModel(row: ModelConfig) {
  await ElMessageBox.confirm(
    `激活「${row.name}」将关闭当前同类型（${modelTypeLabel[row.model_type]}）的已激活模型，确定？`,
    '确认激活',
    { type: 'warning' }
  )
  const result: ModelActivateResponse = await activateModelConfig(row.id)
  ElMessage.success('模型已激活')
  await loadModels()

  // Embedding 模型切换后弹出重建提示
  if (result.needs_rebuild) {
    try {
      await ElMessageBox.confirm(
        'Embedding 模型已切换，所有知识库的向量数据维度可能不兼容。\n是否立即重建所有知识库？（文件将重新解析和向量化，耗时取决于数据量）',
        '⚠️ 需要重建知识库',
        {
          confirmButtonText: '立即重建',
          cancelButtonText: '稍后手动重建',
          type: 'warning',
          dangerouslyUseHTMLString: false,
        }
      )
      rebuilding.value = true
      const rebuildResult = await rebuildAllKnowledgeBases()
      ElMessage.success(
        `重建任务已提交：${rebuildResult.total_kbs} 个知识库，${rebuildResult.total_files} 个文件排队处理中`
      )
    } catch {
      ElMessage.info('你可以稍后在模型配置页面点击「重建所有知识库」按钮手动执行')
    } finally {
      rebuilding.value = false
    }
  }
}

async function handleDeleteModel(row: ModelConfig) {
  await ElMessageBox.confirm(`确定删除模型配置「${row.name}」吗？`, '确认删除', { type: 'warning' })
  await deleteModelConfig(row.id)
  ElMessage.success('删除成功')
  await loadModels()
}

async function handleRebuildAllKBs() {
  await ElMessageBox.confirm(
    '此操作将删除所有知识库的向量数据并重新处理所有文件，耗时取决于数据量。确定继续？',
    '确认重建所有知识库',
    { confirmButtonText: '确认重建', cancelButtonText: '取消', type: 'warning' }
  )
  rebuilding.value = true
  try {
    const result = await rebuildAllKnowledgeBases()
    ElMessage.success(
      `重建任务已提交：${result.total_kbs} 个知识库，${result.total_files} 个文件排队处理中`
    )
  } finally {
    rebuilding.value = false
  }
}

// ─── Init ─────────────────────────────────────────────────────
onMounted(async () => {
  const [, perms] = await Promise.all([
    loadRoles(),
    listPermissions(),
  ])
  allPermissions.value = perms
  await Promise.all([loadUsers(), loadKBAccess(), loadModels()])
  // 加载供应商列表
  try { providers.value = await listModelProviders() } catch { /* ignore */ }
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
.model-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 14px;
  padding: 10px 14px;
  background: #ecf5ff;
  border-radius: 6px;
  color: #409eff;
  font-size: 13px;
}
</style>
