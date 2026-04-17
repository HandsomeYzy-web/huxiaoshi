<template>
  <section class="admin-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">模型配置</div>
        <div class="panel-subtitle">管理 LLM、Embedding、Rerank 模型，并触发知识库重建。</div>
      </div>
      <div class="header-tools">
        <el-select v-model="modelTypeFilter" clearable placeholder="按模型类型筛选" style="width: 180px" @change="loadData">
          <el-option label="LLM" value="llm" />
          <el-option label="Embedding" value="embedding" />
          <el-option label="Rerank" value="rerank" />
        </el-select>
        <el-button type="primary" @click="openCreate">新建模型</el-button>
        <el-button type="warning" :loading="rebuilding" @click="rebuildAll">重建全部知识库</el-button>
      </div>
    </div>

    <el-table :data="models" v-loading="loading" border class="panel-table">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" width="180" />
      <el-table-column prop="model_type" label="类型" width="120" />
      <el-table-column label="提供商" width="160">
        <template #default="{ row }">{{ providerName(row.provider) }}</template>
      </el-table-column>
      <el-table-column prop="model_name" label="模型标识" min-width="200" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '已激活' : '未激活' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="success" :disabled="row.is_active" @click="activate(row)">激活</el-button>
          <el-button size="small" type="warning" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" :disabled="row.is_active" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingModelId ? '编辑模型' : '新建模型'" width="560px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="模型类型">
          <el-select v-model="form.model_type" style="width: 100%" :disabled="!!editingModelId">
            <el-option label="llm" value="llm" />
            <el-option label="embedding" value="embedding" />
            <el-option label="rerank" value="rerank" />
          </el-select>
        </el-form-item>
        <el-form-item label="提供商">
          <el-select v-model="form.provider" filterable style="width: 100%">
            <el-option v-for="item in filteredProviders" :key="item.provider" :label="item.display_name" :value="item.provider" />
          </el-select>
        </el-form-item>
        <el-form-item label="显示名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="模型标识"><el-input v-model="form.model_name" /></el-form-item>
        <el-form-item label="API Base"><el-input v-model="form.api_base_url" /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="form.api_key" show-password /></el-form-item>
        <el-form-item label="额外参数"><el-input v-model="form.extra_params" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  activateModelConfig,
  createModelConfig,
  deleteModelConfig,
  listModelConfigs,
  listModelProviders,
  rebuildAllKnowledgeBases,
  updateModelConfig,
  type ModelConfig,
  type ModelConfigCreate,
  type ModelConfigUpdate,
  type ModelProviderInfo,
} from '../../api/admin'

const loading = ref(false)
const saving = ref(false)
const rebuilding = ref(false)
const dialogVisible = ref(false)
const editingModelId = ref<number | null>(null)
const modelTypeFilter = ref<string | undefined>(undefined)
const models = ref<ModelConfig[]>([])
const providers = ref<ModelProviderInfo[]>([])
const form = ref<ModelConfigCreate>({ model_type: 'llm', provider: '', name: '', model_name: '', api_base_url: '', api_key: '', extra_params: '' })

const filteredProviders = computed(() => providers.value.filter(item => item.supported_types.includes(form.value.model_type)))

async function loadData() {
  loading.value = true
  try {
    models.value = await listModelConfigs(modelTypeFilter.value)
  } finally {
    loading.value = false
  }
}

function providerName(code: string) {
  return providers.value.find(item => item.provider === code)?.display_name || code
}

function openCreate() {
  editingModelId.value = null
  form.value = { model_type: 'llm', provider: '', name: '', model_name: '', api_base_url: '', api_key: '', extra_params: '' }
  dialogVisible.value = true
}

function openEdit(row: ModelConfig) {
  editingModelId.value = row.id
  form.value = { model_type: row.model_type, provider: row.provider, name: row.name, model_name: row.model_name, api_base_url: row.api_base_url, api_key: '', extra_params: row.extra_params || '' }
  dialogVisible.value = true
}

async function save() {
  saving.value = true
  try {
    if (editingModelId.value) {
      const payload: ModelConfigUpdate = {
        name: form.value.name,
        model_name: form.value.model_name,
        api_base_url: form.value.api_base_url,
        extra_params: form.value.extra_params || undefined,
      }
      if (form.value.api_key) payload.api_key = form.value.api_key
      await updateModelConfig(editingModelId.value, payload)
    } else {
      await createModelConfig(form.value)
    }
    dialogVisible.value = false
    ElMessage.success('模型已保存')
    await loadData()
  } finally {
    saving.value = false
  }
}

async function activate(row: ModelConfig) {
  await ElMessageBox.confirm(`确认激活模型“${row.name}”吗？`, '激活模型', { type: 'warning' })
  await activateModelConfig(row.id)
  ElMessage.success('模型已激活')
  await loadData()
}

async function remove(row: ModelConfig) {
  await ElMessageBox.confirm(`确认删除模型“${row.name}”吗？`, '删除模型', { type: 'warning' })
  await deleteModelConfig(row.id)
  ElMessage.success('模型已删除')
  await loadData()
}

async function rebuildAll() {
  await ElMessageBox.confirm('确认重建全部知识库吗？', '批量重建', { type: 'warning' })
  rebuilding.value = true
  try {
    const result = await rebuildAllKnowledgeBases()
    ElMessage.success(`已提交重建任务：${result.total_kbs} 个知识库，${result.total_files} 个文件`)
  } finally {
    rebuilding.value = false
  }
}

onMounted(async () => {
  providers.value = await listModelProviders().catch(() => [])
  await loadData()
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

.header-tools {
  display: flex;
  gap: 12px;
}

.panel-table {
  border-radius: 18px;
  overflow: hidden;
}
</style>
