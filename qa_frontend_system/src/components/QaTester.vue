<template>
  <section class="panel-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">召回测试</div>
        <div class="panel-subtitle">选择一个或多个知识库，仅查看检索命中的片段内容。</div>
      </div>
      <el-tag v-if="selectedKbIds.length" type="success" effect="plain">已选择 {{ selectedKbIds.length }} 个</el-tag>
    </div>

    <div class="tester-grid">
      <div class="tester-form">
        <el-form label-position="top">
          <el-form-item label="知识库">
            <el-select
              v-model="selectedKbIds"
              multiple
              collapse-tags
              collapse-tags-tooltip
              placeholder="请选择知识库"
              filterable
              style="width: 100%"
            >
              <el-option v-for="item in knowledgeBases" :key="item.id" :label="`${item.name} (#${item.id})`" :value="item.id" />
            </el-select>
          </el-form-item>

          <el-form-item label="问题">
            <el-input
              v-model="question"
              type="textarea"
              :rows="7"
              resize="none"
              placeholder="例如：查找与合同解除相关的风险点"
            />
          </el-form-item>

          <div class="form-actions">
            <el-button @click="question = ''">清空</el-button>
            <el-button v-if="authStore.hasPermission('qa.run')" type="primary" :loading="asking" @click="handleAsk">
              开始测试
            </el-button>
          </div>
        </el-form>
      </div>

      <div class="result-card">
        <div class="result-header">
          <span>召回片段</span>
          <span class="result-meta">{{ answerData?.retrieved_count ?? 0 }} 条</span>
        </div>

        <div class="scroll-container">
          <el-scrollbar v-if="answerData?.citations?.length" class="citation-scroll">
            <div class="citation-list">
              <div v-for="item in answerData.citations" :key="`${item.kb_id}-${item.chunk_id}`" class="citation-item">
                <div class="citation-headline">
                  <span class="kb-tag">{{ item.kb_name }}</span>
                  <span class="file-name">{{ item.file_name }}</span>
                  <span class="score-tag">Score: {{ item.score.toFixed(4) }}</span>
                </div>
                <div class="citation-content">{{ item.content }}</div>
              </div>
            </div>
          </el-scrollbar>
          <el-empty v-else :image-size="100" description="暂无结果" />
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '../stores/auth'
import { retrieveKnowledgeBase, type QaAskResponse } from '../api/qa'
import type { KnowledgeBase } from '../api/kb'

const authStore = useAuthStore()

const props = defineProps<{
  knowledgeBases: KnowledgeBase[]
  kbId?: number | null
}>()

const selectedKbIds = ref<number[]>(props.kbId ? [props.kbId] : [])
const question = ref('')
const asking = ref(false)
const answerData = ref<QaAskResponse | null>(null)

watch(
  () => props.kbId,
  value => {
    selectedKbIds.value = value ? [value] : []
  },
  { immediate: true },
)

async function handleAsk() {
  if (!selectedKbIds.value.length) {
    ElMessage.warning('请至少选择一个知识库')
    return
  }
  if (!question.value.trim()) {
    ElMessage.warning('请输入问题')
    return
  }

  asking.value = true
  try {
    answerData.value = await retrieveKnowledgeBase({
      kb_ids: selectedKbIds.value,
      question: question.value.trim(),
    })
  } finally {
    asking.value = false
  }
}


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
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
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

.tester-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px;
}

.tester-form,
.result-card {
  min-height: 0;
  padding: 20px;
  border-radius: 12px;
  background: #f7f8fa;
}

.result-card {
  display: flex;
  flex-direction: column;
}

.result-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
  font-weight: 600;
}

.scroll-container {
  flex: 1;
  min-height: 0;
  position: relative;
}

.citation-scroll {
  position: absolute;
  inset: 0;
}

.citation-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 12px;
}

.citation-item {
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #e5e6eb;
  background: #fff;
}

.citation-headline {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.kb-tag {
  padding: 2px 8px;
  border-radius: 4px;
  background: #e8f3ff;
  color: #165dff;
  font-size: 12px;
  font-weight: 700;
}

.file-name {
  font-size: 12px;
  color: #4e5969;
}

.score-tag {
  margin-left: auto;
  font-size: 12px;
  color: #ff7d00;
}

.citation-content {
  white-space: pre-wrap;
  line-height: 1.7;
  color: #1d2129;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

@media (max-width: 1080px) {
  .tester-grid {
    grid-template-columns: 1fr;
  }
}
</style>
