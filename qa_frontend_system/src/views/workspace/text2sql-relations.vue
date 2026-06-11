<template>
  <div class="text2sql-panel">
    <section class="panel-card">
      <div class="panel-header">
        <div>
          <div class="panel-title">Text2SQL 关联关系配置</div>
          <div class="panel-subtitle">管理多表 Text2SQL 自然语言查询时允许进行 JOIN 的数据表关联关系白名单。</div>
        </div>

      </div>

      <div class="filter-row">
        <el-select v-model="filters.table_name" clearable filterable placeholder="按表筛选" style="width: 220px">
          <el-option v-for="item in tableOptions" :key="item.table_name" :label="item.table_name" :value="item.table_name" />
        </el-select>
        <el-input
          v-model="filters.keyword"
          clearable
          placeholder="在表名或描述中搜索关键字"
          style="max-width: 340px"
          @keyup.enter="handleSearch"
        />
        <el-button :disabled="loading" @click="handleSearch">搜索</el-button>
        <el-button :disabled="loading" @click="handleReset">重置</el-button>
        <el-button type="primary" plain :disabled="!canUpdate" @click="openCSVImportDialog">CSV 格式导入</el-button>
        <el-button type="primary" :disabled="!canUpdate" @click="openCreate">新建关联关系</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe class="panel-table">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="源数据表 (Source)" min-width="260">
          <template #default="{ row }">
            <div class="table-line">{{ row.source_table }}</div>
            <div class="column-line">{{ row.source_columns.join(', ') || '--' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="目标数据表 (Target)" min-width="260">
          <template #default="{ row }">
            <div class="table-line">{{ row.target_table }}</div>
            <div class="column-line">{{ row.target_columns.join(', ') || '--' }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="relation_type" label="类型" width="92" align="center" />
        <el-table-column prop="description" label="描述说明" min-width="240" show-overflow-tooltip />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '已启用' : '已禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="180" />
        <el-table-column v-if="canUpdate" label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="warning" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" :loading="deletingId === row.id" @click="removeRelation(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager-row">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          background
          layout="total, prev, pager, next, sizes"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </section>

    <el-dialog v-model="dialogVisible" :title="editingRelationId ? '编辑关联关系' : '新建关联关系'" width="700px">
      <el-form :model="form" label-position="top">
        <el-row :gutter="12">
          <el-col :xs="24" :md="12">
            <el-form-item label="源数据表 (Source Table)">
              <el-select
                v-model="form.source_table"
                filterable
                clearable
                placeholder="请选择源数据表"
                style="width: 100%"
                @change="handleSourceTableChange"
              >
                <el-option v-for="item in tableOptions" :key="item.table_name" :label="item.table_name" :value="item.table_name" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="目标数据表 (Target Table)">
              <el-select
                v-model="form.target_table"
                filterable
                clearable
                placeholder="请选择目标数据表"
                style="width: 100%"
                @change="handleTargetTableChange"
              >
                <el-option v-for="item in tableOptions" :key="item.table_name" :label="item.table_name" :value="item.table_name" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="12">
          <el-col :xs="24" :md="12">
            <el-form-item label="源表关联字段 (Source Columns)">
              <el-select
                v-model="form.source_columns"
                multiple
                filterable
                collapse-tags
                collapse-tags-tooltip
                placeholder="请选择源表字段（多字段即为复合外键）"
                style="width: 100%"
              >
                <el-option v-for="item in sourceColumns" :key="item.name" :label="item.name" :value="item.name" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="目标表关联字段 (Target Columns)">
              <el-select
                v-model="form.target_columns"
                multiple
                filterable
                collapse-tags
                collapse-tags-tooltip
                placeholder="请选择目标表字段（多字段即为复合外键）"
                style="width: 100%"
              >
                <el-option v-for="item in targetColumns" :key="item.name" :label="item.name" :value="item.name" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="12">
          <el-col :xs="24" :md="12">
            <el-form-item label="关联类型 (Relation Type)">
              <el-select v-model="form.relation_type" style="width: 100%">
                <el-option label="N:1 (多对一)" value="N:1" />
                <el-option label="1:N (一对多)" value="1:N" />
                <el-option label="1:1 (一对一)" value="1:1" />
                <el-option label="N:N (多对多)" value="N:N" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="是否启用">
              <el-switch v-model="form.is_active" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="描述说明 (Description)">
          <el-input v-model="form.description" type="textarea" :rows="3" resize="none" placeholder="描述此 JOIN 关联的实际意义（选填）" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRelation">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importDialogVisible" title="CSV 格式导入关联关系" width="800px">
      <el-alert
        type="info"
        show-icon
        :closable="false"
        style="margin-bottom: 16px"
      >
        <template #title>
          <div style="font-weight: bold; margin-bottom: 4px;">CSV 导入说明：</div>
          <div>1. 表头字段必须包含：<code>source_table</code>, <code>source_columns</code>, <code>target_table</code>, <code>target_columns</code>。</div>
          <div>2. 选填表头字段：<code>relation_type</code>, <code>description</code>, <code>is_active</code>。</div>
          <div>3. 复合关联键（多列）请在 CSV 单元格中用分号 <code>;</code> 隔开，例如 <code>"customer_id;branch_id"</code>。</div>
        </template>
      </el-alert>

      <div class="csv-upload-actions" style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
        <input type="file" ref="fileInput" @change="handleFileChange" accept=".csv" style="display: none" />
        <el-button type="primary" @click="triggerFileInput">选择 CSV 文件</el-button>
        <el-button type="success" plain @click="downloadTemplate">下载 CSV 模板</el-button>
        <span v-if="csvFileName" style="font-size: 14px; color: #606266; font-weight: 500;">
          已选择文件: <el-tag type="info" size="small">{{ csvFileName }}</el-tag>
        </span>
      </div>

      <div v-if="parsedRelations.length > 0" class="csv-preview-container" style="margin-bottom: 16px;">
        <div style="font-size: 14px; font-weight: bold; color: #4a2a24; margin-bottom: 8px;">数据解析预览 (共 {{ parsedRelations.length }} 条记录):</div>
        <el-table :data="parsedRelations" max-height="250" border stripe size="small" style="border-radius: 8px;">
          <el-table-column prop="source_table" label="源数据表" min-width="120" />
          <el-table-column label="源表字段" min-width="120">
            <template #default="{ row }">
              {{ row.source_columns.join(', ') }}
            </template>
          </el-table-column>
          <el-table-column prop="target_table" label="目标数据表" min-width="120" />
          <el-table-column label="目标表字段" min-width="120">
            <template #default="{ row }">
              {{ row.target_columns.join(', ') }}
            </template>
          </el-table-column>
          <el-table-column prop="relation_type" label="关系类型" width="85" align="center" />
          <el-table-column prop="description" label="描述说明" min-width="150" show-overflow-tooltip />
          <el-table-column label="是否启用" width="85" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-form label-position="left" style="margin-top: 14px">
        <el-form-item label="当关联关系已存在时:">
          <el-switch
            v-model="importForm.overwrite_existing"
            active-text="覆盖已有关系"
            inactive-text="跳过重复关系"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" :disabled="parsedRelations.length === 0" @click="submitBatchImport">开始导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  batchImportText2SQLRelations,
  createText2SQLRelation,
  deleteText2SQLRelation,
  getText2SQLRelationTableColumns,
  getText2SQLTableOptions,
  listText2SQLRelations,
  updateText2SQLRelation,
  type CreateText2SQLRelationRequest,
  type Text2SQLColumnInfo,
  type Text2SQLRelationItem,
  type Text2SQLTableOption,
} from '../../api/text2sql'

const loading = ref(false)
const saving = ref(false)
const importing = ref(false)
const deletingId = ref<number | null>(null)
const dialogVisible = ref(false)
const importDialogVisible = ref(false)
const editingRelationId = ref<number | null>(null)
const canUpdate = computed(() => true)

const tableOptions = ref<Text2SQLTableOption[]>([])
const sourceColumns = ref<Text2SQLColumnInfo[]>([])
const targetColumns = ref<Text2SQLColumnInfo[]>([])
const columnCache = ref<Record<string, Text2SQLColumnInfo[]>>({})
const rows = ref<Text2SQLRelationItem[]>([])

// CSV Import States
const fileInput = ref<HTMLInputElement | null>(null)
const csvFileName = ref('')
const parsedRelations = ref<CreateText2SQLRelationRequest[]>([])

const filters = reactive({
  keyword: '',
  table_name: '',
})

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0,
})

const form = reactive<CreateText2SQLRelationRequest>({
  source_table: '',
  source_columns: [],
  target_table: '',
  target_columns: [],
  relation_type: 'N:1',
  description: '',
  is_active: true,
})

const importForm = reactive({
  raw: '',
  overwrite_existing: false,
})

function resetForm() {
  form.source_table = ''
  form.source_columns = []
  form.target_table = ''
  form.target_columns = []
  form.relation_type = 'N:1'
  form.description = ''
  form.is_active = true
  sourceColumns.value = []
  targetColumns.value = []
}

async function loadTableOptions() {
  const data = await getText2SQLTableOptions()
  tableOptions.value = data.tables || []
}

async function loadColumns(tableName: string, key: 'source' | 'target') {
  if (!tableName) {
    if (key === 'source') sourceColumns.value = []
    else targetColumns.value = []
    return
  }

  let columns = columnCache.value[tableName]
  if (!columns) {
    const data = await getText2SQLRelationTableColumns(tableName)
    columns = data.columns || []
    columnCache.value = {
      ...columnCache.value,
      [tableName]: columns,
    }
  }

  if (key === 'source') {
    sourceColumns.value = columns
    form.source_columns = form.source_columns.filter(item => columns.some(col => col.name === item))
  } else {
    targetColumns.value = columns
    form.target_columns = form.target_columns.filter(item => columns.some(col => col.name === item))
  }
}

async function loadRelations() {
  loading.value = true
  try {
    const data = await listText2SQLRelations({
      page: pagination.page,
      page_size: pagination.page_size,
      keyword: filters.keyword.trim(),
      table_name: filters.table_name,
    })
    rows.value = data.items || []
    pagination.total = data.total || 0
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  void loadRelations()
}

function handleReset() {
  filters.keyword = ''
  filters.table_name = ''
  pagination.page = 1
  void loadRelations()
}

function handlePageChange(page: number) {
  pagination.page = page
  void loadRelations()
}

function handleSizeChange(size: number) {
  pagination.page_size = size
  pagination.page = 1
  void loadRelations()
}

function parseCSV(text: string): string[][] {
  const result: string[][] = []
  let row: string[] = []
  let inQuotes = false
  let currentVal = ''

  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    const nextChar = text[i + 1]

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        currentVal += '"'
        i++
      } else {
        inQuotes = !inQuotes
      }
    } else if (char === ',' && !inQuotes) {
      row.push(currentVal)
      currentVal = ''
    } else if ((char === '\r' || char === '\n') && !inQuotes) {
      if (char === '\r' && nextChar === '\n') {
        i++
      }
      row.push(currentVal)
      result.push(row)
      row = []
      currentVal = ''
    } else {
      currentVal += char
    }
  }
  if (currentVal || row.length > 0) {
    row.push(currentVal)
    result.push(row)
  }
  return result
}

function parseCSVContent(text: string) {
  try {
    const rows = parseCSV(text)
    if (rows.length < 2) {
      ElMessage.warning('CSV 文件内容为空或格式不正确')
      return
    }

    const headers = rows[0].map(h => h.trim().toLowerCase())

    const sourceTableIdx = headers.indexOf('source_table')
    const sourceColsIdx = headers.indexOf('source_columns')
    const targetTableIdx = headers.indexOf('target_table')
    const targetColsIdx = headers.indexOf('target_columns')
    const relTypeIdx = headers.indexOf('relation_type')
    const descIdx = headers.indexOf('description')
    const activeIdx = headers.indexOf('is_active')

    if (sourceTableIdx === -1 || sourceColsIdx === -1 || targetTableIdx === -1 || targetColsIdx === -1) {
      ElMessage.warning('CSV 缺少必要的表头：source_table, source_columns, target_table, target_columns')
      return
    }

    const tempRelations: CreateText2SQLRelationRequest[] = []

    for (let i = 1; i < rows.length; i++) {
      const row = rows[i]
      if (row.length === 0 || (row.length === 1 && !row[0])) continue

      const source_table = row[sourceTableIdx]?.trim() || ''
      const raw_source_cols = row[sourceColsIdx]?.trim() || ''
      const target_table = row[targetTableIdx]?.trim() || ''
      const raw_target_cols = row[targetColsIdx]?.trim() || ''

      if (!source_table || !raw_source_cols || !target_table || !raw_target_cols) {
        continue
      }

      const source_columns = raw_source_cols.split(/[;,]/).map(c => c.trim()).filter(Boolean)
      const target_columns = raw_target_cols.split(/[;,]/).map(c => c.trim()).filter(Boolean)

      const relation_type = relTypeIdx !== -1 ? (row[relTypeIdx]?.trim() || 'N:1') : 'N:1'
      const description = descIdx !== -1 ? (row[descIdx]?.trim() || '') : ''
      const raw_active = activeIdx !== -1 ? (row[activeIdx]?.trim().toLowerCase() || 'true') : 'true'
      const is_active = raw_active === 'true' || raw_active === '1' || raw_active === 'yes'

      tempRelations.push({
        source_table,
        source_columns,
        target_table,
        target_columns,
        relation_type,
        description,
        is_active,
      })
    }

    if (tempRelations.length === 0) {
      ElMessage.warning('未解析到有效的关联关系数据')
      return
    }

    parsedRelations.value = tempRelations
    ElMessage.success(`成功解析 ${tempRelations.length} 条关联关系`)
  } catch (e) {
    ElMessage.error('解析 CSV 失败，请检查文件格式')
  }
}

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  csvFileName.value = file.name

  const reader = new FileReader()
  reader.onload = (e) => {
    const text = e.target?.result as string
    if (!text) return
    parseCSVContent(text)
  }
  reader.readAsText(file, 'utf-8')
  target.value = ''
}

function downloadTemplate() {
  const headers = ['source_table', 'source_columns', 'target_table', 'target_columns', 'relation_type', 'description', 'is_active']
  const example = ['orders', 'customer_id', 'customers', 'id', 'N:1', 'orders.customer_id -> customers.id', 'true']
  const csvContent = '\uFEFF' + [headers.join(','), example.join(',')].join('\n')

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  link.setAttribute('href', url)
  link.setAttribute('download', 'text2sql_relation_template.csv')
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

function openCSVImportDialog() {
  csvFileName.value = ''
  parsedRelations.value = []
  importForm.overwrite_existing = false
  importDialogVisible.value = true
}

async function submitBatchImport() {
  if (parsedRelations.value.length === 0) {
    ElMessage.warning('没有可导入的数据，请先选择 CSV 文件')
    return
  }

  importing.value = true
  try {
    const result = await batchImportText2SQLRelations({
      relations: parsedRelations.value,
      overwrite_existing: importForm.overwrite_existing,
    })
    importDialogVisible.value = false

    const summary = `导入完成：新建 ${result.created} 条，更新 ${result.updated} 条，跳过 ${result.skipped} 条，失败 ${result.failed} 条。`
    if (result.failed > 0) {
      const preview = result.errors.slice(0, 3).join(' | ')
      ElMessage.warning(preview ? `${summary} 错误预览：${preview}` : summary)
    } else {
      ElMessage.success(summary)
    }

    await loadRelations()
  } catch (error: any) {
    ElMessage.error(error?.message || '批量导入失败')
  } finally {
    importing.value = false
  }
}

function openCreate() {
  editingRelationId.value = null
  resetForm()
  dialogVisible.value = true
}

async function openEdit(row: Text2SQLRelationItem) {
  editingRelationId.value = row.id
  form.source_table = row.source_table
  form.source_columns = [...row.source_columns]
  form.target_table = row.target_table
  form.target_columns = [...row.target_columns]
  form.relation_type = row.relation_type || 'N:1'
  form.description = row.description || ''
  form.is_active = row.is_active
  dialogVisible.value = true
  await Promise.all([loadColumns(form.source_table, 'source'), loadColumns(form.target_table, 'target')])
}

function handleSourceTableChange(tableName: string) {
  form.source_columns = []
  void loadColumns(tableName, 'source')
}

function handleTargetTableChange(tableName: string) {
  form.target_columns = []
  void loadColumns(tableName, 'target')
}

async function saveRelation() {
  if (!form.source_table || !form.target_table) {
    ElMessage.warning('请选择源表和目标表。')
    return
  }
  if (!form.source_columns.length || !form.target_columns.length) {
    ElMessage.warning('请选择关联字段。')
    return
  }
  if (form.source_columns.length !== form.target_columns.length) {
    ElMessage.warning('源表关联字段和目标表关联字段的数量必须一致（等长）。')
    return
  }

  saving.value = true
  try {
    const payload: CreateText2SQLRelationRequest = {
      source_table: form.source_table,
      source_columns: [...form.source_columns],
      target_table: form.target_table,
      target_columns: [...form.target_columns],
      relation_type: form.relation_type,
      description: form.description,
      is_active: form.is_active,
    }
    if (editingRelationId.value) {
      await updateText2SQLRelation(editingRelationId.value, payload)
    } else {
      await createText2SQLRelation(payload)
    }
    dialogVisible.value = false
    ElMessage.success('关联关系已成功保存。')
    await loadRelations()
  } finally {
    saving.value = false
  }
}

async function removeRelation(row: Text2SQLRelationItem) {
  await ElMessageBox.confirm(`确定要删除关联关系 #${row.id} 吗？`, '删除关联关系', { type: 'warning' })
  deletingId.value = row.id
  try {
    await deleteText2SQLRelation(row.id)
    ElMessage.success('关联关系已成功删除。')
    await loadRelations()
  } finally {
    deletingId.value = null
  }
}

onMounted(async () => {
  await loadTableOptions()
  await loadRelations()
})
</script>

<style scoped>
.text2sql-panel {
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

.filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.import-form {
  margin-top: 14px;
}

.panel-table {
  border-radius: 12px;
  overflow: hidden;
}

.table-line {
  font-weight: 600;
  color: #2f241d;
}

.column-line {
  margin-top: 4px;
  font-size: 12px;
  color: #8a6e5c;
}

.pager-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
