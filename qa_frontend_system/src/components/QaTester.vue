<template>
  <section class="panel-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">问答联调区</div>
        <div class="panel-subtitle">直接调用后端 `/qa/ask`，观察回答、检索片段和模型信息</div>
      </div>
      <el-tag v-if="selectedKbId" type="success" effect="plain">测试知识库 ID {{ selectedKbId }}</el-tag>
    </div>

    <div class="tester-grid">
      <div class="tester-form">
        <el-form label-position="top">
          <el-form-item label="知识库">
            <el-select
              v-model="selectedKbId"
              placeholder="请选择知识库"
              filterable
              clearable
              style="width: 100%"
            >
              <el-option
                v-for="item in knowledgeBases"
                :key="item.id"
                :label="`${item.name} (#${item.id})`"
                :value="item.id"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="Top K">
            <el-slider v-model="topK" :min="1" :max="10" show-input />
          </el-form-item>

          <el-form-item label="问题">
            <el-input
              v-model="question"
              type="textarea"
              :rows="7"
              resize="none"
              placeholder="例如：这个知识库里有哪些与合同终止相关的风险点？"
            />
          </el-form-item>

          <div class="form-actions">
            <el-button @click="question = ''">清空</el-button>
            <el-button type="primary" :loading="asking" @click="handleAsk">发送测试</el-button>
          </div>
        </el-form>
      </div>

      <div class="tester-result">
        <div class="result-card">
          <div class="result-header">
            <span>回答结果</span>
            <span class="result-meta">
              {{ answerData?.model_used ? `模型 ${answerData.model_used}` : '未配置 LLM，当前为检索回显模式' }}
            </span>
          </div>
          <div v-if="answerData" class="answer-content">{{ answerData.answer }}</div>
          <el-empty v-else description="提交问题后，这里显示回答结果" />
        </div>

        <div class="result-card citations-card">
          <div class="result-header">
            <span>命中片段</span>
            <span class="result-meta">{{ answerData?.retrieved_count ?? 0 }} 条</span>
          </div>
          <div v-if="answerData?.citations.length" class="citation-list">
            <div v-for="item in answerData.citations" :key="item.chunk_id" class="citation-item">
              <div class="citation-headline">
                <strong>{{ item.file_name }}</strong>
                <span>chunk #{{ item.chunk_id }}</span>
                <span>score {{ item.score.toFixed(4) }}</span>
              </div>
              <div class="citation-content">{{ item.content }}</div>
            </div>
          </div>
          <el-empty v-else description="还没有检索结果" />
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { askKnowledgeBase, type QaAskResponse } from '../api/qa'
import type { KnowledgeBase } from '../api/kb'

const props = defineProps<{
  knowledgeBases: KnowledgeBase[]
  kbId?: number | null
}>()

const selectedKbId = ref<number | null>(props.kbId ?? null)
const topK = ref(5)
const question = ref('')
const asking = ref(false)
const answerData = ref<QaAskResponse | null>(null)

watch(
  () => props.kbId,
  value => {
    selectedKbId.value = value ?? null
  },
  { immediate: true }
)

const handleAsk = async () => {
  if (!selectedKbId.value) {
    ElMessage.warning('请先选择知识库')
    return
  }
  if (!question.value.trim()) {
    ElMessage.warning('请输入测试问题')
    return
  }

  asking.value = true
  try {
    answerData.value = await askKnowledgeBase({
      kb_id: selectedKbId.value,
      question: question.value.trim(),
      top_k: topK.value
    })
  } finally {
    asking.value = false
  }
}
</script>

<style scoped>
.panel-card {
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

.tester-grid {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 20px;
  margin-top: 22px;
}

.tester-form,
.result-card {
  border-radius: 20px;
  border: 1px solid #e6ece6;
  background: #f9fbf8;
}

.tester-form {
  padding: 20px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.tester-result {
  display: grid;
  gap: 16px;
}

.result-card {
  padding: 18px 20px;
}

.result-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
  font-weight: 700;
  color: #18312a;
}

.result-meta {
  font-size: 12px;
  color: #6b7c76;
}

.answer-content,
.citation-content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.75;
  color: #314942;
}

.citation-list {
  display: grid;
  gap: 12px;
}

.citation-item {
  padding: 14px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid #e6ece6;
}

.citation-headline {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #61746e;
}

.citations-card {
  min-height: 260px;
}

@media (max-width: 1080px) {
  .tester-grid {
    grid-template-columns: 1fr;
  }
}
</style>
