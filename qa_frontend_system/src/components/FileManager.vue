<template>
  <section class="panel-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">文件处理区</div>
        <div class="panel-subtitle">上传文件、观察解析状态，并按文件重设切分策略。</div>
      </div>
      <div class="header-actions">
        <el-tag v-if="kbId" type="success" effect="plain">当前知识库 ID {{ kbId }}</el-tag>
        <el-button
          v-if="authStore.hasPermission('file.upload')"
          type="primary"
          :disabled="!kbId"
          @click="uploadDialogVisible = true"
        >上传文件</el-button>
      </div>
    </div>

    <div v-if="!kbId" class="empty-state">
      <el-empty description="请先选择一个知识库，然后再管理文件与触发解析。" />
    </div>

    <template v-else>
      <div class="status-bar">
        <div class="status-group">
          <span>文件总数 {{ total }}</span>
          <span>当前页 {{ fileList.length }}</span>
          <span>本页已完成 {{ finishedCount }}</span>
          <span>本页处理中 {{ processingCount }}</span>
        </div>
        <el-tag v-if="polling" type="warning" effect="plain">正在轮询解析状态</el-tag>
      </div>

      <div class="table-section">
        <el-table :data="fileList" class="file-table" v-loading="loading">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="file_name" label="文件名" min-width="220" show-overflow-tooltip />
          <el-table-column prop="file_type" label="类型" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ String(row.file_type || '-').toUpperCase() }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="110">
            <template #default="{ row }">{{ formatFileSize(row.file_size) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="140" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.status === 0" type="info">待处理</el-tag>
              <el-tag v-else-if="row.status === 1" type="warning">解析中</el-tag>
              <el-tag v-else-if="row.status === 2" type="success">已完成</el-tag>
              <el-tooltip v-else :content="row.error_msg || '解析失败'" placement="top">
                <el-tag type="danger">失败</el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="切分策略" min-width="180">
            <template #default="{ row }">
              {{ row.custom_chunk_size || '默认' }} / {{ row.custom_chunk_overlap ?? '默认' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="authStore.hasPermission('file.reprocess')"
                text
                type="primary"
                @click="openStrategyDialog(row)"
              >重新切分</el-button>
              <el-button
                v-if="row.status === 2"
                text
                type="success"
                @click="openChunkPreview(row)"
              >分段预览</el-button>
              <el-popconfirm
                v-if="authStore.hasPermission('file.delete')"
                title="确认删除该文件？将同时清除其所有向量数据，不可恢复！"
                confirm-button-text="确认删除"
                cancel-button-text="取消"
                confirm-button-type="danger"
                width="240"
                @confirm="handleDeleteFile(row.id)"
              >
                <template #reference>
                  <el-button text type="danger" :loading="deletingFileId === row.id">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-bar">
          <el-pagination
            background
            layout="total, sizes, prev, pager, next"
            :total="total"
            :current-page="page"
            :page-size="pageSize"
            :page-sizes="[10, 20, 50, 100]"
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </div>
    </template>

    <el-dialog v-model="uploadDialogVisible" title="上传文件" width="560px" @close="closeUploadDialog">
      <el-upload
        drag
        multiple
        action="#"
        :auto-upload="false"
        :on-change="handleFileChange"
        :on-remove="handleFileChange"
        :file-list="tempFiles"
      >
        <div class="upload-copy">拖拽文件到这里，或点击选择文件</div>
      </el-upload>

      <el-divider>批量应用切分策略</el-divider>

      <el-form :model="uploadForm" label-width="110px">
        <el-form-item label="切片大小">
          <el-input-number v-model="uploadForm.custom_chunk_size" :min="100" :step="100" />
        </el-form-item>
        <el-form-item label="重叠大小">
          <el-input-number v-model="uploadForm.custom_chunk_overlap" :min="0" :step="50" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="closeUploadDialog">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="!tempFiles.length" @click="handleUpload">
          开始上传
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="strategyDialogVisible" title="修改切分策略" width="460px">
      <el-alert
        title="修改后会清空该文件旧向量，并在后台重新解析。"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 18px"
      />
      <el-form :model="strategyForm" label-width="110px">
        <el-form-item label="切片大小">
          <el-input-number v-model="strategyForm.custom_chunk_size" :min="100" :step="100" />
        </el-form-item>
        <el-form-item label="重叠大小">
          <el-input-number v-model="strategyForm.custom_chunk_overlap" :min="0" :step="50" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="strategyDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="updating" @click="handleUpdateStrategy">确认重算</el-button>
      </template>
    </el-dialog>

    <!-- 分段预览 Dialog -->
    <el-dialog
      v-model="chunkPreviewVisible"
      :title="`分段预览 — ${chunkPreviewFile?.file_name || ''}`"
      width="760px"
      destroy-on-close
    >
      <div class="chunk-stats">
        <el-tag effect="plain">共 {{ chunkTotal }} 个分段</el-tag>
        <el-tag effect="plain" type="info">当前页 {{ chunkPage }} / {{ chunkTotalPages }}</el-tag>
      </div>

      <div v-if="chunkLoading" class="chunk-loading">
        <el-skeleton :rows="6" animated />
      </div>

      <div v-else-if="chunkList.length === 0" class="chunk-empty">
        <el-empty description="该文件暂无分段数据" />
      </div>

      <div v-else class="chunk-list">
        <div
          v-for="chunk in chunkList"
          :key="chunk.id"
          class="chunk-item"
        >
          <div class="chunk-header">
            <span class="chunk-index"># {{ chunk.chunk_index + 1 }}</span>
            <el-tag size="small" type="info" effect="plain">{{ chunk.char_count }} 字</el-tag>
          </div>
          <div class="chunk-content">{{ chunk.content }}</div>
        </div>
      </div>

      <div class="chunk-pagination">
        <el-pagination
          background
          layout="prev, pager, next"
          :total="chunkTotal"
          :current-page="chunkPage"
          :page-size="chunkPageSize"
          @current-change="handleChunkPageChange"
        />
      </div>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import {
  deleteFile,
  getFileChunks,
  getFilesByKnowledgeBase,
  updateFileStrategy,
  uploadKnowledgeFiles,
  type ChunkItem,
  type KnowledgeFile,
  type UploadResult
} from '../api/file'

const authStore = useAuthStore()


const props = defineProps<{
  kbId: number | null
}>()

const fileList = ref<KnowledgeFile[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const polling = ref(false)
const uploadDialogVisible = ref(false)
const strategyDialogVisible = ref(false)
const uploading = ref(false)
const updating = ref(false)
const currentFile = ref<KnowledgeFile | null>(null)
const tempFiles = ref<any[]>([])
const deletingFileId = ref<number | null>(null)

// --- 分段预览 ---
const chunkPreviewVisible = ref(false)
const chunkPreviewFile = ref<KnowledgeFile | null>(null)
const chunkList = ref<ChunkItem[]>([])
const chunkTotal = ref(0)
const chunkPage = ref(1)
const chunkPageSize = ref(20)
const chunkTotalPages = ref(0)
const chunkLoading = ref(false)
const uploadForm = reactive<{ custom_chunk_size?: number; custom_chunk_overlap?: number }>({
  custom_chunk_size: undefined,
  custom_chunk_overlap: undefined
})
const strategyForm = reactive({
  custom_chunk_size: 1000,
  custom_chunk_overlap: 200
})

let timer: ReturnType<typeof setInterval> | null = null

const processingCount = computed(() => fileList.value.filter(item => item.status === 0 || item.status === 1).length)
const finishedCount = computed(() => fileList.value.filter(item => item.status === 2).length)

const fetchFiles = async (showLoading = true) => {
  if (!props.kbId) return
  if (showLoading) loading.value = true

  try {
    const data = await getFilesByKnowledgeBase(props.kbId, {
      page: page.value,
      page_size: pageSize.value
    })
    fileList.value = data.items
    total.value = data.total
    if (data.items.some(item => item.status === 0 || item.status === 1)) {
      startPolling()
    } else {
      stopPolling()
    }
  } catch (_error) {
    stopPolling()
  } finally {
    if (showLoading) loading.value = false
  }
}

const startPolling = () => {
  if (timer || !props.kbId) return
  polling.value = true
  timer = setInterval(() => {
    void fetchFiles(false)
  }, 3000)
}

const stopPolling = () => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  polling.value = false
}

const formatFileSize = (size: number) => `${(size / 1024 / 1024).toFixed(2)} MB`

const buildUploadMessage = (results: UploadResult[]) => {
  const successCount = results.filter(item => item.status === 'success').length
  const skippedCount = results.filter(item => item.status === 'skipped').length
  const failedItems = results.filter(item => item.status === 'failed')

  if (failedItems.length) {
    const firstFailure = failedItems[0]
    return {
      type: 'warning' as const,
      text: `上传已返回，但有 ${failedItems.length} 个文件失败：${firstFailure.filename}${firstFailure.reason ? `，${firstFailure.reason}` : ''}`
    }
  }

  if (successCount === 0 && skippedCount > 0) {
    return {
      type: 'warning' as const,
      text: `没有新文件入库，${skippedCount} 个文件因重复被跳过`
    }
  }

  return {
    type: 'success' as const,
    text: `已接收 ${successCount} 个文件，后台开始解析${skippedCount ? `，${skippedCount} 个重复文件被跳过` : ''}`
  }
}

watch(
  () => props.kbId,
  newKbId => {
    stopPolling()
    fileList.value = []
    total.value = 0
    page.value = 1
    if (newKbId) {
      void fetchFiles(true)
    }
  },
  { immediate: true }
)

const handleFileChange = (_file: unknown, fileListSnapshot: any[]) => {
  tempFiles.value = fileListSnapshot
}

const closeUploadDialog = () => {
  uploadDialogVisible.value = false
  tempFiles.value = []
  uploadForm.custom_chunk_size = undefined
  uploadForm.custom_chunk_overlap = undefined
}

const handleUpload = async () => {
  if (!props.kbId || !tempFiles.value.length) return

  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('kb_id', String(props.kbId))
    tempFiles.value.forEach(item => formData.append('files', item.raw))

    if (uploadForm.custom_chunk_size) {
      formData.append('custom_chunk_size', String(uploadForm.custom_chunk_size))
    }

    if (uploadForm.custom_chunk_overlap !== undefined) {
      formData.append('custom_chunk_overlap', String(uploadForm.custom_chunk_overlap))
    }

    const results = await uploadKnowledgeFiles(formData)
    const message = buildUploadMessage(results)
    ElMessage[message.type](message.text)
    closeUploadDialog()
    page.value = 1
    await fetchFiles(true)
    startPolling()
  } finally {
    uploading.value = false
  }
}

const openStrategyDialog = (file: KnowledgeFile) => {
  currentFile.value = file
  strategyForm.custom_chunk_size = file.custom_chunk_size || 1000
  strategyForm.custom_chunk_overlap = file.custom_chunk_overlap ?? 200
  strategyDialogVisible.value = true
}

const handleUpdateStrategy = async () => {
  if (!currentFile.value) return

  updating.value = true
  try {
    await updateFileStrategy(currentFile.value.id, {
      custom_chunk_size: strategyForm.custom_chunk_size,
      custom_chunk_overlap: strategyForm.custom_chunk_overlap
    })
    ElMessage.success('切分策略已更新，后台开始重算')
    strategyDialogVisible.value = false
    await fetchFiles(true)
    startPolling()
  } finally {
    updating.value = false
  }
}

const handleDeleteFile = async (fileId: number) => {
  deletingFileId.value = fileId
  try {
    await deleteFile(fileId)
    ElMessage.success('文件已删除')
    await fetchFiles(true)
  } finally {
    deletingFileId.value = null
  }
}

const openChunkPreview = async (file: KnowledgeFile) => {
  chunkPreviewFile.value = file
  chunkPage.value = 1
  chunkList.value = []
  chunkPreviewVisible.value = true
  await fetchChunks()
}

const fetchChunks = async () => {
  if (!chunkPreviewFile.value) return
  chunkLoading.value = true
  try {
    const data = await getFileChunks(chunkPreviewFile.value.id, {
      page: chunkPage.value,
      page_size: chunkPageSize.value
    })
    chunkList.value = data.items
    chunkTotal.value = data.total
    chunkTotalPages.value = data.total_pages
  } finally {
    chunkLoading.value = false
  }
}

const handleChunkPageChange = (nextPage: number) => {
  chunkPage.value = nextPage
  void fetchChunks()
}

const handlePageChange = (nextPage: number) => {
  page.value = nextPage
  void fetchFiles(true)
}

const handlePageSizeChange = (nextPageSize: number) => {
  pageSize.value = nextPageSize
  page.value = 1
  void fetchFiles(true)
}

defineExpose({
  refresh: fetchFiles
})

onUnmounted(stopPolling)
</script>

<style scoped>
.panel-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
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

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.empty-state {
  flex: 1;
  display: grid;
  place-items: center;
}

.status-bar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin: 20px 0 16px;
}

.status-group {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: #5d7069;
  font-size: 13px;
}

.table-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.file-table {
  flex: 1;
  min-height: 0;
  height: 100%;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
}

.upload-copy {
  padding: 24px 0;
  color: #5d7069;
}

/* 分段预览样式 */
.chunk-stats {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.chunk-loading {
  padding: 12px 0;
}

.chunk-empty {
  padding: 24px 0;
}

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 520px;
  overflow-y: auto;
  padding-right: 4px;
}

.chunk-item {
  border: 1px solid #e5ece6;
  border-radius: 12px;
  padding: 14px 16px;
  background: #f8faf7;
}

.chunk-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.chunk-index {
  font-size: 13px;
  font-weight: 700;
  color: #2b6150;
}

.chunk-content {
  font-size: 13px;
  line-height: 1.7;
  color: #3a4f47;
  white-space: pre-wrap;
  word-break: break-word;
}

.chunk-pagination {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

@media (max-width: 900px) {
  .panel-header,
  .status-bar {
    flex-direction: column;
    align-items: flex-start;
  }

  .pagination-bar {
    width: 100%;
    overflow-x: auto;
  }
}
</style>
