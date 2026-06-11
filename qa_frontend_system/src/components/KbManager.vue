<template>
  <section class="panel-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">知识库管理</div>
        <div class="panel-subtitle">创建、切换并维护知识库配置，直接查看关键检索参数。</div>
      </div>

      <div class="header-actions">
        <el-button :loading="loading" @click="fetchKnowledgeBases(true)">刷新</el-button>
        <el-button type="primary" @click="openCreate">
          新建知识库
        </el-button>
      </div>
    </div>

    <div class="summary-grid">
      <div class="summary-item">
        <span class="summary-label">知识库总数</span>
        <strong class="summary-value">{{ knowledgeBases.length }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">启用重排</span>
        <strong class="summary-value">{{ rerankEnabledCount }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">平均 Top-K</span>
        <strong class="summary-value">{{ averageTopK }}</strong>
      </div>
    </div>

    <div class="panel-toolbar">
      <el-input
        v-model="keyword"
        clearable
        placeholder="按名称或描述搜索知识库"
        class="search-input"
      />
      <el-tag type="info" effect="plain">当前列表 {{ filteredKnowledgeBases.length }} 个</el-tag>
    </div>

    <div v-loading="loading" class="list-wrap">
      <div v-if="errorMessage" class="state-wrap">
        <el-result icon="warning" title="知识库加载失败" :sub-title="errorMessage">
          <template #extra>
            <el-button type="primary" @click="fetchKnowledgeBases(true)">重试</el-button>
          </template>
        </el-result>
      </div>

      <div v-else-if="!filteredKnowledgeBases.length" class="state-wrap">
        <el-empty :description="keyword ? '没有匹配的知识库' : '当前还没有知识库'" />
      </div>

      <el-scrollbar v-else class="list-scroll">
        <div
          v-for="item in filteredKnowledgeBases"
          :key="item.id"
          class="kb-item"
          :class="{ active: item.id === currentKbId }"
          role="button"
          tabindex="0"
          @click="selectKnowledgeBase(item.id)"
          @keydown.enter="selectKnowledgeBase(item.id)"
        >
          <div class="kb-headline">
            <div class="title-group">
              <div class="kb-name">{{ item.name }}</div>
              <el-tag size="small" :type="purposeTagType(item.purpose)" effect="plain">
                {{ purposeLabel(item.purpose) }}
              </el-tag>
              <el-tag v-if="item.id === currentKbId" size="small" type="success">当前选中</el-tag>
            </div>

            <div class="kb-actions" @click.stop>
              <el-tag size="small" effect="plain">ID {{ item.id }}</el-tag>
              <el-button text type="primary" @click="openEdit(item)">
                编辑
              </el-button>
              <el-popconfirm
                title="确认删除该知识库及其关联数据？"
                confirm-button-text="确认删除"
                cancel-button-text="取消"
                confirm-button-type="danger"
                width="260"
                @confirm="handleDelete(item.id)"
              >
                <template #reference>
                  <el-button text type="danger" :loading="deletingId === item.id" @click.stop>删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>

          <div class="kb-desc">{{ item.description || '暂无描述' }}</div>

          <div class="meta-grid">
            <div class="meta-item">
              <span>切分大小</span>
              <strong>{{ item.default_chunk_size }}</strong>
            </div>
            <div class="meta-item">
              <span>切分重叠</span>
              <strong>{{ item.default_chunk_overlap }}</strong>
            </div>
            <div class="meta-item">
              <span>检索 Top-K</span>
              <strong>{{ item.retrieval_top_k }}</strong>
            </div>
            <div class="meta-item">
              <span>阈值</span>
              <strong>{{ item.retrieval_score_threshold }}</strong>
            </div>
          </div>

          <div class="kb-footer">
            <span>创建于 {{ formatDate(item.created_at) }}</span>
            <el-tag v-if="item.enable_rerank" size="small" type="success" effect="plain">启用重排</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">未启用重排</el-tag>
          </div>
        </div>
      </el-scrollbar>
    </div>

    <el-dialog v-model="createVisible" title="新建知识库" width="520px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="130px">
        <el-form-item label="名称" prop="name">
          <el-input v-model.trim="createForm.name" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model.trim="createForm.description" type="textarea" :rows="3" maxlength="240" show-word-limit />
        </el-form-item>
        <el-form-item label="用途" prop="purpose">
          <el-select v-model="createForm.purpose">
            <el-option
              v-for="option in purposeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <div class="purpose-hint">{{ purposeHint(createForm.purpose) }}</div>
        </el-form-item>
        <el-form-item label="切分大小">
          <el-input-number v-model="createForm.default_chunk_size" :min="100" :max="4000" :step="100" />
        </el-form-item>
        <el-form-item label="切分重叠">
          <el-input-number v-model="createForm.default_chunk_overlap" :min="0" :max="1000" :step="50" />
        </el-form-item>
        <el-form-item label="Top-K">
          <el-input-number v-model="createForm.retrieval_top_k" :min="1" :max="50" />
        </el-form-item>
        <el-form-item label="得分阈值">
          <el-input-number
            v-model="createForm.retrieval_score_threshold"
            :min="0"
            :max="1"
            :step="0.05"
            :precision="2"
          />
        </el-form-item>
        <el-form-item label="启用重排">
          <el-switch v-model="createForm.enable_rerank" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑知识库" width="520px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="130px">
        <el-form-item label="名称" prop="name">
          <el-input v-model.trim="editForm.name" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model.trim="editForm.description" type="textarea" :rows="3" maxlength="240" show-word-limit />
        </el-form-item>
        <el-form-item label="用途" prop="purpose">
          <el-select v-model="editForm.purpose">
            <el-option
              v-for="option in purposeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <div class="purpose-hint">{{ purposeHint(editForm.purpose) }}</div>
        </el-form-item>
        <el-form-item label="切分大小">
          <el-input-number v-model="editForm.default_chunk_size" :min="100" :max="4000" :step="100" />
        </el-form-item>
        <el-form-item label="切分重叠">
          <el-input-number v-model="editForm.default_chunk_overlap" :min="0" :max="1000" :step="50" />
        </el-form-item>
        <el-form-item label="Top-K">
          <el-input-number v-model="editForm.retrieval_top_k" :min="1" :max="50" />
        </el-form-item>
        <el-form-item label="得分阈值">
          <el-input-number
            v-model="editForm.retrieval_score_threshold"
            :min="0"
            :max="1"
            :step="0.05"
            :precision="2"
          />
        </el-form-item>
        <el-form-item label="启用重排">
          <el-switch v-model="editForm.enable_rerank" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="updating" @click="handleEditSubmit">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  getKnowledgeBases,
  updateKnowledgeBase,
  type CreateKnowledgeBasePayload,
  type KnowledgeBase,
  type KnowledgeBasePurpose,
  type UpdateKnowledgeBasePayload,
} from '../api/kb'

const purposeOptions: Array<{ value: KnowledgeBasePurpose; label: string }> = [
  { value: 'document', label: '文档问答（默认）' },
  { value: 'table_desc', label: 'Text2SQL 表描述' },
  { value: 'few_shot', label: 'Text2SQL Few-Shot 示例' },
]

const purposeMeta: Record<KnowledgeBasePurpose, { label: string; tagType: 'info' | 'warning' | 'primary'; hint: string }> = {
  document: {
    label: '文档问答',
    tagType: 'info',
    hint: '常规文档知识库，参与文档问答检索。',
  },
  table_desc: {
    label: 'Text2SQL 表描述',
    tagType: 'warning',
    hint: 'text2SQL 查表专用（存放表结构/表描述文档），不参与文档问答；该用途全局只允许一个知识库。',
  },
  few_shot: {
    label: 'Text2SQL Few-Shot',
    tagType: 'primary',
    hint: 'text2SQL 示例专用（存放问题-SQL 示范样例），不参与文档问答；该用途全局只允许一个知识库。',
  },
}

function purposeLabel(purpose?: KnowledgeBasePurpose) {
  return purposeMeta[purpose ?? 'document']?.label ?? '文档问答'
}

function purposeTagType(purpose?: KnowledgeBasePurpose) {
  return purposeMeta[purpose ?? 'document']?.tagType ?? 'info'
}

function purposeHint(purpose?: KnowledgeBasePurpose) {
  return purposeMeta[purpose ?? 'document']?.hint ?? ''
}

const props = withDefaults(defineProps<{ modelValue?: number | null; autoSelectFirst?: boolean }>(), {
  modelValue: null,
  autoSelectFirst: true,
})

const emit = defineEmits<{
  (e: 'update:modelValue', id: number | null): void
  (e: 'kb-selected', id: number): void
  (e: 'loaded', list: KnowledgeBase[]): void
}>()

const knowledgeBases = ref<KnowledgeBase[]>([])
const currentKbId = ref<number | null>(props.modelValue)
const keyword = ref('')
const loading = ref(false)
const errorMessage = ref('')

const createVisible = ref(false)
const editVisible = ref(false)
const creating = ref(false)
const updating = ref(false)
const deletingId = ref<number | null>(null)
const editingKbId = ref<number | null>(null)
const createFormRef = ref<FormInstance>()
const editFormRef = ref<FormInstance>()

const createForm = reactive<CreateKnowledgeBasePayload>({
  name: '',
  description: '',
  purpose: 'document',
  default_chunk_size: 1000,
  default_chunk_overlap: 200,
  retrieval_top_k: 5,
  retrieval_score_threshold: 0,
  enable_rerank: false,
})

const editForm = reactive<UpdateKnowledgeBasePayload>({
  name: '',
  description: '',
  purpose: 'document',
  default_chunk_size: 1000,
  default_chunk_overlap: 200,
  retrieval_top_k: 5,
  retrieval_score_threshold: 0,
  enable_rerank: false,
})

const createRules: FormRules<typeof createForm> = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
}

const editRules: FormRules<typeof editForm> = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
  description: [{ max: 240, message: '描述不能超过 240 个字符', trigger: 'blur' }],
}

const filteredKnowledgeBases = computed(() => {
  if (!keyword.value.trim()) return knowledgeBases.value
  const search = keyword.value.trim().toLowerCase()
  return knowledgeBases.value.filter(item => {
    return (
      item.name.toLowerCase().includes(search) ||
      (item.description || '').toLowerCase().includes(search) ||
      String(item.id).includes(search)
    )
  })
})

const rerankEnabledCount = computed(() => knowledgeBases.value.filter(item => item.enable_rerank).length)
const averageTopK = computed(() => {
  if (!knowledgeBases.value.length) return '--'
  const totalTopK = knowledgeBases.value.reduce((sum, item) => sum + item.retrieval_top_k, 0)
  return (totalTopK / knowledgeBases.value.length).toFixed(1)
})

watch(
  () => props.modelValue,
  value => {
    currentKbId.value = value
  },
)

async function fetchKnowledgeBases(showLoading = false) {
  if (showLoading) loading.value = true
  errorMessage.value = ''
  try {
    const data = await getKnowledgeBases()
    knowledgeBases.value = data
    emit('loaded', data)

    if (!data.length) {
      currentKbId.value = null
      emit('update:modelValue', null)
      return
    }

    if (data.some(item => item.id === currentKbId.value)) return
    if (props.autoSelectFirst) selectKnowledgeBase(data[0].id)
  } catch (error: any) {
    knowledgeBases.value = []
    errorMessage.value = error?.message || '请检查后端服务与网络后重试'
  } finally {
    if (showLoading) loading.value = false
  }
}

function selectKnowledgeBase(id: number) {
  currentKbId.value = id
  emit('update:modelValue', id)
  emit('kb-selected', id)
}

function resetCreateForm() {
  createForm.name = ''
  createForm.description = ''
  createForm.purpose = 'document'
  createForm.default_chunk_size = 1000
  createForm.default_chunk_overlap = 200
  createForm.retrieval_top_k = 5
  createForm.retrieval_score_threshold = 0
  createForm.enable_rerank = false
}

function openCreate() {
  resetCreateForm()
  createVisible.value = true
}

async function handleCreate() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return

  creating.value = true
  try {
    const created = await createKnowledgeBase({ ...createForm, name: createForm.name.trim() })
    createVisible.value = false
    ElMessage.success('知识库已创建')
    await fetchKnowledgeBases(true)
    selectKnowledgeBase(created.id)
  } finally {
    creating.value = false
  }
}

function openEdit(item: KnowledgeBase) {
  editingKbId.value = item.id
  editForm.name = item.name
  editForm.description = item.description || ''
  editForm.purpose = item.purpose ?? 'document'
  editForm.default_chunk_size = item.default_chunk_size
  editForm.default_chunk_overlap = item.default_chunk_overlap
  editForm.retrieval_top_k = item.retrieval_top_k
  editForm.retrieval_score_threshold = item.retrieval_score_threshold
  editForm.enable_rerank = item.enable_rerank
  editVisible.value = true
}

async function handleEditSubmit() {
  if (!editingKbId.value) return
  const valid = await editFormRef.value?.validate().catch(() => false)
  if (valid === false) return

  updating.value = true
  try {
    await updateKnowledgeBase(editingKbId.value, { ...editForm })
    editVisible.value = false
    ElMessage.success('知识库已更新')
    await fetchKnowledgeBases(true)
  } finally {
    updating.value = false
  }
}

async function handleDelete(id: number) {
  deletingId.value = id
  try {
    await deleteKnowledgeBase(id)
    ElMessage.success('知识库已删除')
    await fetchKnowledgeBases(true)
  } finally {
    deletingId.value = null
  }
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

defineExpose({
  refresh: fetchKnowledgeBases,
})

onMounted(async () => {
  await fetchKnowledgeBases(true)
})
</script>

<style scoped>
.panel-card {
  height: 100%;
  min-height: 500px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 24px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 18px 40px rgba(32, 50, 45, 0.08);
  box-sizing: border-box;
}

.panel-header,
.panel-toolbar,
.kb-headline,
.kb-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-title {
  font-size: 22px;
  font-weight: 800;
  color: #18312a;
}

.panel-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: #6b7c76;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.summary-item {
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid #e4ece7;
  background: #f7faf8;
}

.summary-label {
  font-size: 12px;
  color: #6b7c76;
}

.summary-value {
  margin-top: 6px;
  display: block;
  font-size: 24px;
  line-height: 1;
  color: #18312a;
}

.panel-toolbar {
  align-items: flex-start;
}

.search-input {
  max-width: 320px;
}

.list-wrap {
  flex: 1;
  min-height: 0;
}

.state-wrap {
  min-height: 260px;
  display: grid;
  place-items: center;
}

.list-scroll {
  height: 100%;
}

.kb-item {
  margin-bottom: 12px;
  padding: 14px 16px;
  border: 1px solid #e5ece6;
  border-radius: 16px;
  background: #fbfdfb;
  transition: 0.18s ease;
  outline: none;
}

.kb-item:hover {
  border-color: #bfd3cc;
}

.kb-item.active {
  border-color: #2f6555;
  box-shadow: 0 0 0 1px rgba(47, 101, 85, 0.2);
  background: #f6faf7;
}

.title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.kb-name {
  font-size: 16px;
  font-weight: 700;
  color: #1b3a31;
}

.kb-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.kb-desc {
  margin: 8px 0 10px;
  color: #4f655d;
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.meta-item {
  padding: 8px 10px;
  border-radius: 10px;
  background: #f3f7f4;
  border: 1px solid #e6eeea;
  display: grid;
  gap: 2px;
}

.meta-item span {
  font-size: 12px;
  color: #6b7c76;
}

.meta-item strong {
  font-size: 14px;
  color: #1e3a33;
}

.kb-footer {
  margin-top: 10px;
  font-size: 12px;
  color: #7c8f89;
}

.purpose-hint {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #8a9b94;
}

@media (max-width: 960px) {
  .panel-header,
  .panel-toolbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }

  .search-input {
    max-width: none;
    width: 100%;
  }

  .meta-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .kb-headline {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
