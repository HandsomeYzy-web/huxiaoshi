<template>
  <div class="text2sql-panel">
    <section class="panel-card">
      <div class="panel-header">
        <div>
          <div class="panel-title">Text2SQL 数据表配置</div>
          <div class="panel-subtitle">管理选中的数据表，并配置 Text2SQL 生成时使用的提示词微调说明。</div>
        </div>

      </div>

      <el-alert
        v-if="!canUpdate"
        title="当前账户对数据表配置是只读的，无修改权限。"
        type="warning"
        :closable="false"
        show-icon
        class="block-alert"
      />

      <el-form v-loading="loading" label-position="top">
        <el-form-item label="允许用于 Text2SQL 的数据表">
          <el-select
            v-model="config.selected_tables"
            multiple
            filterable
            clearable
            collapse-tags
            collapse-tags-tooltip
            style="width: 100%"
            placeholder="请选择允许通过自然语言进行查询的数据表"
          >
            <el-option
              v-for="item in tableOptions"
              :key="item.table_name"
              :label="item.table_comment ? `${item.table_name} (${item.table_comment})` : item.table_name"
              :value="item.table_name"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="提示词微调说明 (Prompt Hint)">
          <el-input
            v-model="config.prompt_hint"
            type="textarea"
            :rows="4"
            resize="none"
            placeholder="（可选）用于指导 Text2SQL 生成的领域知识、特殊业务规则或字段映射说明。"
          />
        </el-form-item>
      </el-form>

      <div class="form-actions">
        <el-button :disabled="configSaving || fieldsSaving" @click="loadBaseData">重新加载</el-button>
        <el-button type="primary" :loading="configSaving" :disabled="!canUpdate || fieldsSaving" @click="saveConfig">
          保存配置
        </el-button>
      </div>
    </section>

    <section class="panel-card">
      <div class="panel-header">
        <div>
          <div class="panel-title">字段权限配置</div>
          <div class="panel-subtitle">精细化控制每个数据表中允许被自然语言查询的列/字段。</div>
        </div>

      </div>

      <div class="inline-tools">
        <el-select
          v-model="selectedTable"
          filterable
          clearable
          style="width: 360px; max-width: 100%"
          placeholder="请选择数据表"
          @change="handleTableChange"
        >
          <el-option
            v-for="item in tableOptions"
            :key="item.table_name"
            :label="item.table_comment ? `${item.table_name} (${item.table_comment})` : item.table_name"
            :value="item.table_name"
          />
        </el-select>
        <el-button type="primary" :loading="fieldsSaving" :disabled="!canUpdate || !tableFields" @click="saveFields">
          保存字段权限
        </el-button>
      </div>

      <el-table v-if="tableFields" v-loading="fieldsLoading" :data="tableFields.fields" border stripe class="panel-table">
        <el-table-column prop="name" label="字段名 (Column)" min-width="180" />
        <el-table-column prop="type" label="类型 (Type)" width="140" />
        <el-table-column prop="comment" label="描述/注释 (Comment)" min-width="220" show-overflow-tooltip />
        <el-table-column label="是否可查询 (Queryable)" width="130" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.query_enabled" :disabled="!canUpdate" />
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="请先选择一个数据表以配置其字段的查询权限。" />
    </section>

    <section v-if="canViewSchema" class="panel-card">
      <div class="panel-header">
        <div>
          <div class="panel-title">数据库 Schema 预览</div>
          <div class="panel-subtitle">只读数据库 Schema 预览，包含完整的表和字段信息。</div>
        </div>

      </div>

      <el-skeleton v-if="schemaLoading" animated>
        <template #template>
          <el-skeleton-item variant="h3" style="width: 40%; margin-bottom: 14px;" />
          <el-skeleton-item variant="rect" style="width: 100%; height: 180px;" />
        </template>
      </el-skeleton>

      <el-empty v-else-if="!schemaTables.length" description="暂无 Schema 数据。" />

      <el-collapse v-else v-model="activeSchemaTables">
        <el-collapse-item
          v-for="table in schemaTables"
          :key="table.table_name"
          :name="table.table_name"
          :title="table.table_comment ? `${table.table_name} (${table.table_comment})` : table.table_name"
        >
          <el-table :data="table.columns" border size="small">
            <el-table-column prop="name" label="字段名 (Column)" min-width="180" />
            <el-table-column prop="type" label="类型 (Type)" width="140" />
            <el-table-column prop="comment" label="描述/注释 (Comment)" min-width="220" show-overflow-tooltip />
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  getText2SQLTableConfig,
  getText2SQLTableFields,
  getText2SQLTableOptions,
  getText2SQLTableSchema,
  updateText2SQLTableConfig,
  updateText2SQLTableFields,
  type Text2SQLConfigResponse,
  type Text2SQLTableFieldsResponse,
  type Text2SQLTableInfo,
  type Text2SQLTableOption,
  type UpdateText2SQLConfigRequest,
} from '../../api/text2sql'

const loading = ref(false)
const configSaving = ref(false)
const fieldsLoading = ref(false)
const fieldsSaving = ref(false)
const schemaLoading = ref(false)

const tableOptions = ref<Text2SQLTableOption[]>([])
const schemaTables = ref<Text2SQLTableInfo[]>([])
const selectedTable = ref('')
const tableFields = ref<Text2SQLTableFieldsResponse | null>(null)
const activeSchemaTables = ref<string[]>([])

const config = reactive<UpdateText2SQLConfigRequest>({
  selected_tables: [],
  prompt_hint: '',
})

const canUpdate = computed(() => true)
const canViewSchema = computed(() => true)

function applyConfig(data: Text2SQLConfigResponse) {
  config.selected_tables = [...(data.selected_tables || [])]
  config.prompt_hint = data.prompt_hint || ''
}

async function loadFields(tableName: string) {
  fieldsLoading.value = true
  try {
    tableFields.value = await getText2SQLTableFields(tableName)
  } finally {
    fieldsLoading.value = false
  }
}

async function loadBaseData() {
  loading.value = true
  try {
    const [optionsData, configData] = await Promise.all([getText2SQLTableOptions(), getText2SQLTableConfig()])
    tableOptions.value = optionsData.tables || []
    applyConfig(configData)

    if (canViewSchema.value) {
      schemaLoading.value = true
      try {
        const schemaData = await getText2SQLTableSchema()
        schemaTables.value = schemaData.tables || []
        activeSchemaTables.value = schemaTables.value.slice(0, 1).map(item => item.table_name)
      } finally {
        schemaLoading.value = false
      }
    } else {
      schemaTables.value = []
      activeSchemaTables.value = []
    }

    const nextTable =
      selectedTable.value ||
      config.selected_tables[0] ||
      tableOptions.value[0]?.table_name ||
      ''
    selectedTable.value = nextTable
    if (nextTable) {
      await loadFields(nextTable)
    } else {
      tableFields.value = null
    }
  } finally {
    loading.value = false
  }
}

function handleTableChange(tableName: string) {
  if (!tableName) {
    tableFields.value = null
    return
  }
  void loadFields(tableName)
}

async function saveConfig() {
  configSaving.value = true
  try {
    const data = await updateText2SQLTableConfig({
      selected_tables: [...config.selected_tables],
      prompt_hint: config.prompt_hint,
    })
    applyConfig(data)
    ElMessage.success('数据表配置已成功保存。')
  } finally {
    configSaving.value = false
  }
}

async function saveFields() {
  if (!selectedTable.value || !tableFields.value) return

  const hasEnabledField = tableFields.value.fields.some(item => item.query_enabled)
  if (!hasEnabledField) {
    ElMessage.warning('每个数据表必须至少保留一个允许查询的字段。')
    return
  }

  fieldsSaving.value = true
  try {
    const data = await updateText2SQLTableFields(selectedTable.value, {
      fields: tableFields.value.fields.map(item => ({
        name: item.name,
        query_enabled: item.query_enabled,
      })),
    })
    tableFields.value = data
    ElMessage.success('字段权限配置已成功保存。')
  } finally {
    fieldsSaving.value = false
  }
}

onMounted(() => {
  void loadBaseData()
})
</script>

<style scoped>
.text2sql-panel {
  display: grid;
  gap: 18px;
  min-height: calc(100vh - 220px);
}

.panel-card {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid #ead8c6;
  background: linear-gradient(180deg, #fffdfb 0%, #f9f2e8 100%);
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.panel-title {
  font-size: 22px;
  font-weight: 700;
  color: #4a2a24;
}

.panel-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: #81695b;
}

.inline-tools {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
}

.panel-table {
  border-radius: 12px;
  overflow: hidden;
}

.block-alert {
  margin-bottom: 12px;
}
</style>
