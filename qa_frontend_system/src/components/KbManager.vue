<template>
  <section class="panel-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">知识库管理</div>
        <div class="panel-subtitle">创建、编辑、删除知识库，并切换当前激活的知识库。</div>
      </div>
      <el-button v-if="authStore.hasPermission('kb.create')" type="primary" @click="openCreate">
        新建知识库
      </el-button>
    </div>

    <div class="panel-toolbar">
      <el-button text @click="fetchKnowledgeBases">刷新</el-button>
      <el-tag type="info" effect="plain">共 {{ knowledgeBases.length }} 个</el-tag>
    </div>

    <el-scrollbar class="list-scroll">
      <div v-if="knowledgeBases.length === 0" class="empty-block">
        <el-empty description="当前还没有知识库。" />
      </div>

      <div
        v-for="item in knowledgeBases"
        :key="item.id"
        class="kb-item"
        :class="{ active: item.id === currentKbId }"
        @click="selectKnowledgeBase(item.id)"
      >
        <div class="kb-headline">
          <div class="kb-name">{{ item.name }}</div>
          <div class="kb-actions" @click.stop>
            <el-tag size="small" effect="plain">ID {{ item.id }}</el-tag>
            <el-button v-if="authStore.hasPermission('kb.update')" text type="primary" @click.stop="openEdit(item)">
              编辑
            </el-button>
            <el-popconfirm
              v-if="authStore.hasPermission('kb.delete')"
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
        <div class="kb-meta">
          <span>分块大小 {{ item.default_chunk_size }}</span>
          <span>重叠 {{ item.default_chunk_overlap }}</span>
          <span>Top-K {{ item.retrieval_top_k }}</span>
          <span>阈值 {{ item.retrieval_score_threshold }}</span>
          <el-tag v-if="item.enable_rerank" size="small" type="success" effect="plain">启用重排</el-tag>
        </div>
      </div>
    </el-scrollbar>

    <el-dialog v-model="createVisible" title="新建知识库" width="500px">
      <el-form :model="createForm" label-width="130px">
        <el-form-item label="名称"><el-input v-model="createForm.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="createForm.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="分块大小"><el-input-number v-model="createForm.default_chunk_size" :min="100" :max="4000" :step="100" /></el-form-item>
        <el-form-item label="分块重叠"><el-input-number v-model="createForm.default_chunk_overlap" :min="0" :max="1000" :step="50" /></el-form-item>
        <el-form-item label="Top-K"><el-input-number v-model="createForm.retrieval_top_k" :min="1" :max="50" /></el-form-item>
        <el-form-item label="得分阈值"><el-input-number v-model="createForm.retrieval_score_threshold" :min="0" :max="1" :step="0.05" :precision="2" /></el-form-item>
        <el-form-item label="启用重排"><el-switch v-model="createForm.enable_rerank" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑知识库" width="500px">
      <el-form :model="editForm" label-width="130px">
        <el-form-item label="描述"><el-input v-model="editForm.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="分块大小"><el-input-number v-model="editForm.default_chunk_size" :min="100" :max="4000" :step="100" /></el-form-item>
        <el-form-item label="分块重叠"><el-input-number v-model="editForm.default_chunk_overlap" :min="0" :max="1000" :step="50" /></el-form-item>
        <el-form-item label="Top-K"><el-input-number v-model="editForm.retrieval_top_k" :min="1" :max="50" /></el-form-item>
        <el-form-item label="得分阈值"><el-input-number v-model="editForm.retrieval_score_threshold" :min="0" :max="1" :step="0.05" :precision="2" /></el-form-item>
        <el-form-item label="启用重排"><el-switch v-model="editForm.enable_rerank" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="updating" @click="handleEditSubmit">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '../stores/auth'
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  getKnowledgeBases,
  updateKnowledgeBase,
  type CreateKnowledgeBasePayload,
  type KnowledgeBase,
  type UpdateKnowledgeBasePayload,
} from '../api/kb'

const authStore = useAuthStore()


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
const createVisible = ref(false)
const editVisible = ref(false)
const creating = ref(false)
const updating = ref(false)
const deletingId = ref<number | null>(null)
const editingKbId = ref<number | null>(null)

const createForm = reactive<CreateKnowledgeBasePayload>({
  name: '',
  description: '',
  default_chunk_size: 1000,
  default_chunk_overlap: 200,
  retrieval_top_k: 5,
  retrieval_score_threshold: 0,
  enable_rerank: false,
})

const editForm = reactive<UpdateKnowledgeBasePayload>({
  description: '',
  default_chunk_size: 1000,
  default_chunk_overlap: 200,
  retrieval_top_k: 5,
  retrieval_score_threshold: 0,
  enable_rerank: false,
})

watch(() => props.modelValue, value => { currentKbId.value = value })

async function fetchKnowledgeBases() {
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
}

function selectKnowledgeBase(id: number) {
  currentKbId.value = id
  emit('update:modelValue', id)
  emit('kb-selected', id)
}

function resetCreateForm() {
  createForm.name = ''
  createForm.description = ''
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
  if (!createForm.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  creating.value = true
  try {
    const created = await createKnowledgeBase({ ...createForm, name: createForm.name.trim() })
    createVisible.value = false
    ElMessage.success('知识库已创建')
    await fetchKnowledgeBases()
    selectKnowledgeBase(created.id)
  } finally {
    creating.value = false
  }
}

function openEdit(item: KnowledgeBase) {
  editingKbId.value = item.id
  editForm.description = item.description || ''
  editForm.default_chunk_size = item.default_chunk_size
  editForm.default_chunk_overlap = item.default_chunk_overlap
  editForm.retrieval_top_k = item.retrieval_top_k
  editForm.retrieval_score_threshold = item.retrieval_score_threshold
  editForm.enable_rerank = item.enable_rerank
  editVisible.value = true
}

async function handleEditSubmit() {
  if (!editingKbId.value) return
  updating.value = true
  try {
    await updateKnowledgeBase(editingKbId.value, { ...editForm })
    editVisible.value = false
    ElMessage.success('知识库已更新')
    await fetchKnowledgeBases()
  } finally {
    updating.value = false
  }
}

async function handleDelete(id: number) {
  deletingId.value = id
  try {
    await deleteKnowledgeBase(id)
    ElMessage.success('知识库已删除')
    await fetchKnowledgeBases()
  } finally {
    deletingId.value = null
  }
}

onMounted(async () => {
  await fetchKnowledgeBases()
})
</script>

<style scoped>
.panel-card {
  height: 100%;
  min-height: 500px;
  display: flex;
  flex-direction: column;
  padding: 24px;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.05);
  box-sizing: border-box;
}

.panel-header,
.panel-toolbar,
.kb-headline,
.kb-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-header {
  margin-bottom: 16px;
}

.panel-toolbar {
  margin-bottom: 12px;
}

.panel-title {
  font-size: 20px;
  font-weight: 700;
  color: #1d2129;
}

.panel-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: #86909c;
}

.list-scroll {
  flex: 1;
}

.empty-block {
  display: grid;
  place-items: center;
  min-height: 260px;
}

.kb-item {
  margin-bottom: 14px;
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 14px;
  cursor: pointer;
  transition: 0.2s ease;
}

.kb-item.active {
  border-color: #409eff;
  box-shadow: 0 0 0 1px rgba(64, 158, 255, 0.15);
}

.kb-name {
  font-size: 16px;
  font-weight: 700;
}

.kb-actions,
.kb-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.kb-desc {
  margin: 10px 0;
  color: #606266;
}
</style>
