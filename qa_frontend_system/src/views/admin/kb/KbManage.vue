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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getKnowledgeBases, createKnowledgeBase } from '../../../api/admin'
import type { KnowledgeBaseItem, KBCreateForm } from '../../../api/admin'

const loading = ref(false)
const submitLoading = ref(false)
const showCreateDialog = ref(false)

// 真实的表格数据源
const tableData = ref<KnowledgeBaseItem[]>([])

// 真实的表单数据
const kbForm = ref<KBCreateForm>({
  name: '',
  description: '',
  embedding_model: 'e5-mistral-7b-instruct' // 锁定为你后端支持的模型
})

// === 🌟 核心逻辑：获取列表 ===
const fetchKBList = async () => {
  try {
    loading.value = true
    // 发起网络请求，直接拿到后端返回的 List 数据
    const res = await getKnowledgeBases()
    tableData.value = res
  } catch (error: any) {
    ElMessage.error(error.message || '获取知识库列表失败')
  } finally {
    loading.value = false
  }
}

// === 🌟 核心逻辑：提交创建 ===
const submitCreateKB = async () => {
  if (!kbForm.value.name) {
    ElMessage.warning('知识库名称不能为空')
    return
  }

  try {
    submitLoading.value = true
    // 调用创建接口
    await createKnowledgeBase(kbForm.value)
    ElMessage.success('知识库创建成功！')

    // 成功后关闭弹窗，清空表单，并重新拉取最新列表
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

const handleUpload = (row: KnowledgeBaseItem) => {
  console.log('准备给这个知识库传文件：', row.name, 'ID:', row.id)
  ElMessage.info(`后续将打开抽屉，上传至: ${row.name}`)
}

// 🌟 页面组件一挂载，立刻去请求数据
onMounted(() => {
  fetchKBList()
})
</script>

<style scoped>
.toolbar-card { margin-bottom: 20px; border-radius: 8px; }
.table-card { border-radius: 8px; }
</style>