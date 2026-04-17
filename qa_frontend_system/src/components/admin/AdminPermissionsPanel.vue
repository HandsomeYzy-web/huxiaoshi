<template>
  <section class="admin-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">权限管理</div>
      </div>
      <div class="header-actions">
        <el-button @click="loadTree">刷新</el-button>
        <el-button type="primary" @click="openCreate(null)">新建权限</el-button>
      </div>
    </div>

    <el-scrollbar max-height="600px">
    <el-table
      v-loading="loading"
      :data="tree"
      row-key="code"
      border
      default-expand-all
      :tree-props="{ children: 'children' }"
      class="panel-table"
    >
      <el-table-column prop="name" label="权限名称" min-width="220">
        <template #default="{ row }">
          <span class="perm-name">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="code" label="权限编码" min-width="200">
        <template #default="{ row }">
          <span class="perm-code">{{ row.code }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="module" label="模块" width="100" />
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.type === 'admin' ? 'warning' : 'success'">{{ row.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sort" label="排序" width="70" />
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openCreate(row.code)">添加子权限</el-button>
          <el-button size="small" type="warning" @click="openEdit(row)">编辑</el-button>
          <el-button
            size="small"
            type="danger"
            :disabled="row.children && row.children.length > 0"
            @click="handleDelete(row)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    </el-scrollbar>

    <!-- 新建/编辑权限 -->
    <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑权限' : '新建权限'" width="520px">
      <el-form :model="form" label-width="100px" :rules="formRules" ref="formRef">
        <el-form-item label="权限编码" prop="code">
          <el-input v-model="form.code" :disabled="isEditing" placeholder="如 kb.create" />
        </el-form-item>
        <el-form-item label="权限名称" prop="name">
          <el-input v-model="form.name" placeholder="如 创建知识库" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="父级权限">
          <el-tree-select
            v-model="form.parent_code"
            :data="parentOptions"
            :props="{ label: 'name', value: 'code', children: 'children' }"
            clearable
            check-strictly
            placeholder="无父级（顶层权限）"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="模块" prop="module">
          <el-select v-model="form.module" filterable allow-create placeholder="选择或输入模块">
            <el-option v-for="m in moduleList" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon" placeholder="Element Plus icon 名称（可选）" />
        </el-form-item>
        <el-form-item label="路由路径">
          <el-input v-model="form.path" placeholder="前端路由路径（可选）" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.type">
            <el-radio value="feature">功能</el-radio>
            <el-radio value="admin">管理</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio value="active">启用</el-radio>
            <el-radio value="disabled">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort" :min="0" :max="9999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import {
  createPermission,
  deletePermission,
  getFullPermissionTree,
  updatePermission,
  type PermissionTreeNode,
} from '../../api/admin'

const loading = ref(false)
const saving = ref(false)
const tree = ref<PermissionTreeNode[]>([])

const dialogVisible = ref(false)
const isEditing = ref(false)
const formRef = ref<FormInstance | null>(null)

const defaultForm = () => ({
  code: '',
  name: '',
  description: '',
  parent_code: null as string | null,
  module: '',
  icon: '',
  path: '',
  type: 'feature',
  status: 'active',
  sort: 0,
})
const form = ref(defaultForm())

const formRules: FormRules = {
  code: [{ required: true, message: '请输入权限编码', trigger: 'blur' }],
  name: [{ required: true, message: '请输入权限名称', trigger: 'blur' }],
  module: [{ required: true, message: '请选择模块', trigger: 'change' }],
}

const moduleList = computed(() => {
  const mods = new Set<string>()
  function walk(nodes: PermissionTreeNode[]) {
    for (const n of nodes) {
      if (n.module) mods.add(n.module)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(tree.value)
  return Array.from(mods).sort()
})

const parentOptions = computed(() => {
  // 只允许选择 Level 1 和 Level 2 作为父级
  return tree.value.map(l1 => ({
    ...l1,
    children: (l1.children || []).map(l2 => ({ ...l2, children: [] })),
  }))
})

async function loadTree() {
  loading.value = true
  try {
    tree.value = await getFullPermissionTree()
  } finally {
    loading.value = false
  }
}

function openCreate(parentCode: string | null) {
  isEditing.value = false
  form.value = { ...defaultForm(), parent_code: parentCode }
  // 自动推断 module
  if (parentCode) {
    const parent = findNode(tree.value, parentCode)
    if (parent) {
      form.value.module = parent.module
      form.value.type = parent.type
    }
  }
  dialogVisible.value = true
}

function openEdit(node: PermissionTreeNode) {
  isEditing.value = true
  form.value = {
    code: node.code,
    name: node.name,
    description: node.description || '',
    parent_code: node.parent_code,
    module: node.module,
    icon: node.icon || '',
    path: node.path || '',
    type: node.type,
    status: node.status,
    sort: node.sort,
  }
  dialogVisible.value = true
}

function findNode(nodes: PermissionTreeNode[], code: string): PermissionTreeNode | null {
  for (const n of nodes) {
    if (n.code === code) return n
    if (n.children?.length) {
      const found = findNode(n.children, code)
      if (found) return found
    }
  }
  return null
}

async function handleSave() {
  if (!formRef.value) return
  await formRef.value.validate()

  saving.value = true
  try {
    const payload = {
      ...form.value,
      icon: form.value.icon || undefined,
      path: form.value.path || undefined,
    }
    if (isEditing.value) {
      await updatePermission(form.value.code, payload)
      ElMessage.success('权限已更新')
    } else {
      await createPermission(payload as any)
      ElMessage.success('权限已创建')
    }
    dialogVisible.value = false
    await loadTree()
  } finally {
    saving.value = false
  }
}

async function handleDelete(node: PermissionTreeNode) {
  if (node.children && node.children.length > 0) {
    ElMessage.warning('请先删除子权限')
    return
  }
  await ElMessageBox.confirm(
    `确认删除权限「${node.name}」(${node.code}) 吗？删除后关联的角色授权也会被清除。`,
    '删除权限',
    { type: 'warning' },
  )
  await deletePermission(node.code)
  ElMessage.success('权限已删除')
  await loadTree()
}

onMounted(() => {
  void loadTree()
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

.header-actions {
  display: flex;
  gap: 8px;
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

.perm-name {
  font-weight: 600;
  color: #20362f;
}

.perm-code {
  font-size: 13px;
  color: #6d8076;
  font-family: 'Menlo', 'Consolas', monospace;
}
</style>
