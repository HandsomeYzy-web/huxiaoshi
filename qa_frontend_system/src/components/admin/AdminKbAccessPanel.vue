<template>
  <section class="admin-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">知识库访问控制</div>
        <div class="panel-subtitle">配置每个知识库可被哪些角色访问。</div>
      </div>
      <el-button @click="loadData">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" border class="panel-table">
      <el-table-column prop="kb_id" label="KB ID" width="90" />
      <el-table-column label="知识库" min-width="220">
        <template #default="{ row }">{{ kbNameMap[row.kb_id] || `KB #${row.kb_id}` }}</template>
      </el-table-column>
      <el-table-column label="可访问角色" min-width="280">
        <template #default="{ row }">
          <div class="tag-list">
            <el-tag v-for="roleId in row.accessible_role_ids" :key="roleId" size="small">{{ roleNameMap[roleId] || roleId }}</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openDialog(row)">配置</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="`配置访问 - ${editingLabel}`" width="420px">
      <el-checkbox-group v-model="selectedRoleIds">
        <div v-for="item in roles" :key="item.id" class="checkbox-row">
          <el-checkbox :label="item.id" :value="item.id">{{ item.name }}</el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getKnowledgeBases } from '../../api/kb'
import { getAllKBAccess, listRoles, setKBAccess, type KBAccessInfo, type Role } from '../../api/admin'

const loading = ref(false)
const saving = ref(false)
const rows = ref<KBAccessInfo[]>([])
const roles = ref<Role[]>([])
const kbNameMap = ref<Record<number, string>>({})
const roleNameMap = computed<Record<number, string>>(() => Object.fromEntries(roles.value.map(item => [item.id, item.name])))

const dialogVisible = ref(false)
const editingKbId = ref<number | null>(null)
const editingLabel = ref('')
const selectedRoleIds = ref<number[]>([])

async function loadData() {
  loading.value = true
  try {
    const [accessList, kbList, roleList] = await Promise.all([getAllKBAccess(), getKnowledgeBases(), listRoles()])
    rows.value = accessList
    roles.value = roleList
    kbNameMap.value = Object.fromEntries(kbList.map(item => [item.id, item.name]))
  } finally {
    loading.value = false
  }
}

function openDialog(row: KBAccessInfo) {
  editingKbId.value = row.kb_id
  editingLabel.value = kbNameMap.value[row.kb_id] || `KB #${row.kb_id}`
  selectedRoleIds.value = [...row.accessible_role_ids]
  dialogVisible.value = true
}

async function save() {
  if (!editingKbId.value) return
  saving.value = true
  try {
    await setKBAccess(editingKbId.value, selectedRoleIds.value)
    dialogVisible.value = false
    ElMessage.success('知识库访问权限已更新')
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

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.checkbox-row {
  margin-bottom: 8px;
}
</style>
