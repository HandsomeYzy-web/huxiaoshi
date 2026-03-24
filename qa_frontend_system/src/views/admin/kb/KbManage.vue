<template>
  <div class="kb-manage">
    <el-card shadow="never" class="toolbar-card">
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">
        创建新知识库
      </el-button>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table :data="tableData" style="width: 100%" v-loading="loading">
        <el-table-column prop="name" label="知识库名称" min-width="150" />
        <el-table-column prop="description" label="描述" min-width="200" />
        <el-table-column prop="embedding_model" label="绑定向量模型" width="200">
          <template #default="scope">
            <el-tag size="small" type="info">{{ scope.row.embedding_model }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />

        <el-table-column label="操作" width="280" fixed="right">
          <template #default="scope">
            <el-button size="small" type="success" plain @click="handleUpload(scope.row)">
              上传文档
            </el-button>
            <el-button size="small" type="warning" plain>
              管理一级索引
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="showCreateDialog" title="创建知识库" width="500px">
      <el-form ref="formRef" :model="kbForm" label-width="100px">
        <el-form-item label="名称" prop="name" required>
          <el-input v-model="kbForm.name" placeholder="例如：湖南师范大学规章制度" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="kbForm.description" type="textarea" placeholder="可选填" />
        </el-form-item>
        <el-form-item label="向量模型" prop="embedding_model">
          <el-input v-model="kbForm.embedding_model" disabled />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" :loading="submitLoading" @click="submitCreateKB">确认创建</el-button>
        </span>
      </template>
    </el-dialog>

    <el-drawer v-model="uploadDrawerVisible" :title="`批量上传至：${currentKb?.name}`" size="450px" @close="clearUploadQueue">
      <div class="upload-container">
        <el-upload
          drag
          multiple
          :auto-upload="false"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :file-list="fileList"
          accept=".doc,.docx"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            将多个 Word 文档拖到此处，或 <em>点击多选</em>
          </div>
        </el-upload>

        <div style="margin-top: 20px;">
          <el-button
            type="primary"
            style="width: 100%"
            :disabled="fileList.length === 0"
            :loading="isUploading"
            @click="submitBatchUpload"
          >
            {{ isUploading ? '正在上传并解析中...' : '确认开始批量上传' }}
          </el-button>
        </div>

        <div v-if="uploadStatus" class="status-box" :class="uploadStatus.type">
          {{ uploadStatus.text }}
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadFiles } from 'element-plus'
import { Plus, UploadFilled } from '@element-plus/icons-vue'

// 注意：这里引入的是 uploadDocuments (批量) 而不是 uploadDocument
import { getKnowledgeBases, createKnowledgeBase, uploadDocuments, processDocument } from '../../../api/admin'
import type { KnowledgeBaseItem, KBCreateForm } from '../../../api/admin'

const loading = ref(false)
const submitLoading = ref(false)
const showCreateDialog = ref(false)

const uploadDrawerVisible = ref(false)
const currentKb = ref<KnowledgeBaseItem | null>(null)
const uploadStatus = ref<{ type: 'success' | 'warning' | 'error', text: string } | null>(null)

// 🌟 批量上传专属状态
const fileList = ref<UploadFile[]>([])
const isUploading = ref(false)

// 真实的表格数据源
const tableData = ref<KnowledgeBaseItem[]>([])

// 真实的表单数据
const kbForm = ref<KBCreateForm>({
  name: '',
  description: '',
  embedding_model: 'e5-mistral-7b-instruct'
})

// === 核心逻辑：获取列表 ===
const fetchKBList = async () => {
  try {
    loading.value = true
    const res = await getKnowledgeBases()
    tableData.value = res
  } catch (error: any) {
    ElMessage.error(error.message || '获取知识库列表失败')
  } finally {
    loading.value = false
  }
}

// === 核心逻辑：提交创建 ===
const submitCreateKB = async () => {
  if (!kbForm.value.name) {
    ElMessage.warning('知识库名称不能为空')
    return
  }

  try {
    submitLoading.value = true
    await createKnowledgeBase(kbForm.value)
    ElMessage.success('知识库创建成功！')

    showCreateDialog.value = false
    kbForm.value.name = ''
    kbForm.value.description = ''
    await fetchKBList()

  } catch (error: any) {
    ElMessage.error(error.message || '创建知识库失败')
  } finally {
    submitLoading.value = false
  }
}

// === 打开上传抽屉 ===
const handleUpload = (row: KnowledgeBaseItem) => {
  currentKb.value = row
  clearUploadQueue()
  uploadDrawerVisible.value = true
}

// === 🌟 批量上传组件行为逻辑 ===
const handleFileChange = (_uploadFile: UploadFile, uploadFiles: UploadFiles) => {
  fileList.value = uploadFiles
}

const handleFileRemove = (_uploadFile: UploadFile, uploadFiles: UploadFiles) => {
  fileList.value = uploadFiles
}

const clearUploadQueue = () => {
  fileList.value = []
  uploadStatus.value = null
  isUploading.value = false
}

// === 🌟 核心逻辑：执行批量上传与解析 ===
const submitBatchUpload = async () => {
  if (!currentKb.value || fileList.value.length === 0) return

  try {
    isUploading.value = true
    uploadStatus.value = { type: 'warning', text: '正在将文件传输至服务器...' }

    // 1. 提取出原生的 File 对象数组
    const rawFiles = fileList.value.map(item => item.raw as File)

    // 2. 批量上传到 MySQL
    const res = await uploadDocuments(currentKb.value.id, rawFiles)

    uploadStatus.value = { type: 'warning', text: `成功上传 ${res.uploaded_files.length} 个文件！正在排队解析...` }

    // 3. 循环触发后台的解析入库任务
    for (const doc of res.uploaded_files) {
      await processDocument(doc.doc_id)
    }

    uploadStatus.value = { type: 'success', text: '✅ 所有文件均已加入后台解析队列！请查看终端确认。' }

    // 成功后清空待选列表，方便下次继续选
    fileList.value = []

  } catch (error: any) {
    uploadStatus.value = { type: 'error', text: `❌ 失败: ${error.message}` }
  } finally {
    isUploading.value = false
  }
}

onMounted(() => {
  fetchKBList()
})
</script>

<style scoped>
.toolbar-card { margin-bottom: 20px; border-radius: 8px; }
.table-card { border-radius: 8px; }
.upload-container { padding: 20px; text-align: center; }
.status-box { margin-top: 20px; padding: 15px; border-radius: 4px; font-size: 14px; font-weight: bold; }
.status-box.warning { background-color: #fdf6ec; color: #e6a23c; }
.status-box.success { background-color: #f0f9eb; color: #67c23a; }
.status-box.error { background-color: #fef0f0; color: #f56c6c; }
</style>