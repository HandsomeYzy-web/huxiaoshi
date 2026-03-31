<template>
  <section class="panel-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">知识库列表</div>
        <div class="panel-subtitle">创建、查看并选择当前联调目标知识库</div>
      </div>
      <el-button type="primary" @click="dialogVisible = true">新建知识库</el-button>
    </div>

    <div class="panel-toolbar">
      <el-button text @click="fetchKnowledgeBases">刷新</el-button>
      <el-tag type="info" effect="plain">共 {{ knowledgeBases.length }} 个</el-tag>
    </div>

    <el-scrollbar class="list-scroll">
      <div v-if="knowledgeBases.length === 0" class="empty-block">
        <el-empty description="还没有知识库，先创建一个用于上传与问答测试" />
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
            <el-button
              type="primary"
              size="small"
              text
              @click.stop="handleEdit(item)"
            >编辑</el-button>
            <el-popconfirm
              title="确定要删除该知识库吗？此操作将同时删除所有文件和向量数据，不可恢复！"
              confirm-button-text="确认删除"
              cancel-button-text="取消"
              confirm-button-type="danger"
              width="260"
              @confirm="handleDelete(item.id)"
            >
              <template #reference>
                <el-button
                  type="danger"
                  size="small"
                  text
                  :loading="deleting === item.id"
                  @click.stop
                >删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
        <div class="kb-desc">{{ item.description || '暂无描述' }}</div>
        <div class="kb-meta">
          <span>默认切片 {{ item.default_chunk_size }}</span>
          <span>重叠 {{ item.default_chunk_overlap }}</span>
          <span>Top-K {{ item.retrieval_top_k }}</span>
          <span>阈值 {{ item.retrieval_score_threshold }}</span>
          <el-tag v-if="item.enable_rerank" size="small" type="success" effect="plain">Rerank</el-tag>
        </div>
      </div>
    </el-scrollbar>

    <el-dialog v-model="dialogVisible" title="新建知识库" width="480px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="例如：政策文件库" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="说明这个知识库的用途与收录范围"
          />
        </el-form-item>
        <el-form-item label="默认切片大小">
          <el-input-number v-model="form.default_chunk_size" :min="100" :max="4000" :step="100" />
        </el-form-item>
        <el-form-item label="默认重叠">
          <el-input-number
            v-model="form.default_chunk_overlap"
            :min="0"
            :max="1000"
            :step="50"
          />
        </el-form-item>
        <el-form-item label="检索条数 Top-K">
          <el-input-number v-model="form.retrieval_top_k" :min="1" :max="50" :step="1" />
        </el-form-item>
        <el-form-item label="相似度阈值">
          <el-input-number
            v-model="form.retrieval_score_threshold"
            :min="0"
            :max="1"
            :step="0.05"
            :precision="2"
          />
        </el-form-item>
        <el-form-item label="启用 Rerank">
          <el-switch v-model="form.enable_rerank" />
          <span style="margin-left:10px;font-size:12px;color:#888">开启后检索结果将经过精排模型重新排序</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑知识库弹窗 -->
    <el-dialog v-model="editDialogVisible" title="编辑知识库" width="480px">
      <el-form :model="editForm" label-width="110px">
        <el-form-item label="描述">
          <el-input
            v-model="editForm.description"
            type="textarea"
            :rows="3"
            placeholder="说明这个知识库的用途与收录范围"
          />
        </el-form-item>
        <el-form-item label="默认切片大小">
          <el-input-number v-model="editForm.default_chunk_size" :min="100" :max="4000" :step="100" />
        </el-form-item>
        <el-form-item label="默认重叠">
          <el-input-number v-model="editForm.default_chunk_overlap" :min="0" :max="1000" :step="50" />
        </el-form-item>
        <el-form-item label="检索条数 Top-K">
          <el-tooltip content="该知识库单独检索时返回的最多条目数" placement="right">
            <el-input-number v-model="editForm.retrieval_top_k" :min="1" :max="50" :step="1" />
          </el-tooltip>
        </el-form-item>
        <el-form-item label="相似度阈值">
          <el-tooltip content="0=不过滤；设置后低于此分的结果将被丢弃" placement="right">
            <el-input-number
              v-model="editForm.retrieval_score_threshold"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
            />
          </el-tooltip>
        </el-form-item>
        <el-form-item label="启用 Rerank">
          <el-switch v-model="editForm.enable_rerank" />
          <span style="margin-left:10px;font-size:12px;color:#888">开启后检索结果将经过精排模型重新排序</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSubmitting" @click="handleEditSubmit">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  getKnowledgeBases,
  updateKnowledgeBase,
  type CreateKnowledgeBasePayload,
  type KnowledgeBase,
  type UpdateKnowledgeBasePayload
} from '../api/kb'

const props = withDefaults(
  defineProps<{
    modelValue?: number | null
    autoSelectFirst?: boolean
  }>(),
  {
    modelValue: null,
    autoSelectFirst: true
  }
)

const emit = defineEmits<{
  (e: 'update:modelValue', id: number | null): void
  (e: 'kb-selected', id: number): void
  (e: 'loaded', list: KnowledgeBase[]): void
}>()

const knowledgeBases = ref<KnowledgeBase[]>([])
const currentKbId = ref<number | null>(props.modelValue)
const dialogVisible = ref(false)
const submitting = ref(false)
const deleting = ref<number | null>(null)

const form = reactive<CreateKnowledgeBasePayload>({
  name: '',
  description: '',
  default_chunk_size: 1000,
  default_chunk_overlap: 200,
  retrieval_top_k: 5,
  retrieval_score_threshold: 0.0,
  enable_rerank: false
})

// 编辑对话框
const editDialogVisible = ref(false)
const editingKbId = ref<number | null>(null)
const editSubmitting = ref(false)
const editForm = reactive<UpdateKnowledgeBasePayload>({
  description: '',
  default_chunk_size: 1000,
  default_chunk_overlap: 200,
  retrieval_top_k: 5,
  retrieval_score_threshold: 0.0,
  enable_rerank: false
})

watch(
  () => props.modelValue,
  value => {
    currentKbId.value = value
  }
)

const selectKnowledgeBase = (id: number) => {
  currentKbId.value = id
  emit('update:modelValue', id)
  emit('kb-selected', id)
}

const fetchKnowledgeBases = async () => {
  const data = await getKnowledgeBases()
  knowledgeBases.value = data
  emit('loaded', data)

  if (!data.length) {
    currentKbId.value = null
    emit('update:modelValue', null)
    return
  }

  const matched = data.find(item => item.id === currentKbId.value)
  if (matched) return

  if (props.autoSelectFirst) {
    selectKnowledgeBase(data[0].id)
  }
}

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.default_chunk_size = 1000
  form.default_chunk_overlap = 200
  form.retrieval_top_k = 5
  form.retrieval_score_threshold = 0.0
  form.enable_rerank = false
}

const handleCreate = async () => {
  if (!form.name.trim()) {
    ElMessage.warning('知识库名称不能为空')
    return
  }

  submitting.value = true
  try {
    const created = await createKnowledgeBase({
      name: form.name.trim(),
      description: form.description?.trim(),
      default_chunk_size: form.default_chunk_size,
      default_chunk_overlap: form.default_chunk_overlap,
      retrieval_top_k: form.retrieval_top_k,
      retrieval_score_threshold: form.retrieval_score_threshold,
      enable_rerank: form.enable_rerank
    })
    ElMessage.success('知识库创建成功')
    dialogVisible.value = false
    resetForm()
    await fetchKnowledgeBases()
    selectKnowledgeBase(created.id)
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (id: number) => {
  deleting.value = id
  try {
    await deleteKnowledgeBase(id)
    ElMessage.success('知识库已删除')
    if (currentKbId.value === id) {
      currentKbId.value = null
      emit('update:modelValue', null)
    }
    await fetchKnowledgeBases()
  } finally {
    deleting.value = null
  }
}

const handleEdit = (item: KnowledgeBase) => {
  editingKbId.value = item.id
  editForm.description = item.description
  editForm.default_chunk_size = item.default_chunk_size
  editForm.default_chunk_overlap = item.default_chunk_overlap
  editForm.retrieval_top_k = item.retrieval_top_k
  editForm.retrieval_score_threshold = item.retrieval_score_threshold
  editForm.enable_rerank = item.enable_rerank
  editDialogVisible.value = true
}

const handleEditSubmit = async () => {
  if (!editingKbId.value) return
  editSubmitting.value = true
  try {
    await updateKnowledgeBase(editingKbId.value, editForm)
    ElMessage.success('知识库配置已更新')
    editDialogVisible.value = false
    await fetchKnowledgeBases()
  } finally {
    editSubmitting.value = false
  }
}

defineExpose({
  refresh: fetchKnowledgeBases
})

onMounted(fetchKnowledgeBases)
</script>

<style scoped>
.panel-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 24px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 18px 40px rgba(32, 50, 45, 0.08);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
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

.panel-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 18px 0 12px;
}

.list-scroll {
  flex: 1;
  min-height: 260px;
}

.empty-block {
  padding: 30px 0;
}

.kb-item {
  padding: 16px 18px;
  margin-bottom: 12px;
  border-radius: 18px;
  cursor: pointer;
  border: 1px solid #e5ece6;
  background: #f8faf7;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.kb-item:hover {
  transform: translateY(-1px);
  border-color: #b6c8bc;
  box-shadow: 0 10px 24px rgba(28, 53, 45, 0.08);
}

.kb-item.active {
  border-color: #2b6150;
  background: linear-gradient(135deg, #eef4dd 0%, #f5ecd2 100%);
}

.kb-headline {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.kb-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.kb-name {
  font-size: 16px;
  font-weight: 700;
  color: #18312a;
}

.kb-desc {
  margin-top: 10px;
  color: #5e706a;
  line-height: 1.6;
}

.kb-meta {
  display: flex;
  gap: 14px;
  margin-top: 12px;
  font-size: 12px;
  color: #768883;
}
</style>
