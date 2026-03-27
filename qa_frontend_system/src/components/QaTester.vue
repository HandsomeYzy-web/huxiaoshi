<template>
  <section class="panel-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">召回测试</div>
        <div class="panel-subtitle">选择多个知识库后，仅展示召回到的文档片段。</div>
      </div>
      <el-tag v-if="selectedKbIds.length" type="success" effect="plain">
        已选 {{ selectedKbIds.length }} 个知识库
      </el-tag>
    </div>

    <div class="tester-grid">
      <div class="tester-form">
        <el-form label-position="top">
          <el-form-item label="知识库（可多选）">
            <el-select
              v-model="selectedKbIds"
              multiple
              collapse-tags
              collapse-tags-tooltip
              placeholder="请选择知识库"
              filterable
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

          <el-form-item label="测试问题">
            <el-input
              v-model="question"
              type="textarea"
              :rows="7"
              resize="none"
              placeholder="例如：对比这些知识库中与合同终止相关的风险点"
            />
          </el-form-item>

          <div class="form-actions">
            <el-button @click="question = ''">清空</el-button>
            <el-button type="primary" :loading="asking" @click="handleAsk">开始测试</el-button>
          </div>
        </el-form>
      </div>

      <div class="result-card citations-card">
        <div class="result-header">
          <span>召回片段</span>
          <span class="result-meta">{{ answerData?.retrieved_count ?? 0 }} 条</span>
        </div>
        <el-scrollbar v-if="answerData?.citations.length" class="citation-scroll">
          <div class="citation-list">
            <div
              v-for="item in answerData.citations"
              :key="`${item.kb_id}-${item.chunk_id}`"
              class="citation-item"
            >
              <div class="citation-headline">
                <strong>{{ item.kb_name }}</strong>
                <span>{{ item.file_name }}</span>
                <span>chunk #{{ item.chunk_id }}</span>
                <span>score {{ item.score.toFixed(4) }}</span>
              </div>
              <div class="citation-content">{{ item.content }}</div>
            </div>
          </div>
        </el-scrollbar>
        <el-empty v-else description="还没有召回结果" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { retrieveKnowledgeBase, type QaAskResponse } from '../api/qa'
import type { KnowledgeBase } from '../api/kb'

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
  { immediate: true }
)

const handleAsk = async () => {
  if (!selectedKbIds.value.length) {
    ElMessage.warning('请至少选择一个知识库')
    return
  }
  if (!question.value.trim()) {
    ElMessage.warning('请输入测试问题')
    return
  }

  asking.value = true
  try {
    answerData.value = await retrieveKnowledgeBase({
      kb_ids: selectedKbIds.value,
      question: question.value.trim()
    })
  } finally {
    asking.value = false
  }
}
</script>

<style scoped>
.panel-card {
  height: 100%;
  min-height: 0;
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

.tester-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 20px;
  margin-top: 22px;
  align-items: stretch;
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

.result-card {
  min-height: 0;
  display: flex;
  flex-direction: column;
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

.citation-content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.75;
  color: #314942;
}

.citation-list {
  display: grid;
  gap: 12px;
  padding-right: 8px;
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
  min-height: 0;
}

.citation-scroll {
  flex: 1;
  min-height: 0;
}

@media (max-width: 1080px) {
  .tester-grid {
    grid-template-columns: 1fr;
  }
}
</style>
