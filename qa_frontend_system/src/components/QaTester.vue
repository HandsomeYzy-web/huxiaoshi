<template>
  <section class="panel-card">
    <div class="panel-header">
      <div>
        <div class="panel-title">召回测试</div>
        <div class="panel-subtitle">按问题检索片段，快速评估命中质量与分数分布。</div>
      </div>
      <el-tag v-if="selectedKbIds.length" type="success" effect="plain">已选择 {{ selectedKbIds.length }} 个知识库</el-tag>
    </div>

    <div class="tester-grid">
      <div class="tester-form">
        <div class="input-overview">
          <el-tag effect="plain">问题字数 {{ questionLength }}</el-tag>
          <el-tag effect="plain" type="info">可选知识库 {{ documentKbs.length }}</el-tag>
        </div>

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
              <el-option
                v-for="item in documentKbs"
                :key="item.id"
                :label="`${item.name} (#${item.id})`"
                :value="item.id"
              />
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

          <div class="selected-kb-list">
            <span class="selected-label">当前选择：</span>
            <el-tag
              v-for="name in selectedKbNames"
              :key="name"
              size="small"
              effect="plain"
              type="success"
            >
              {{ name }}
            </el-tag>
            <span v-if="!selectedKbNames.length" class="selected-empty">未选择知识库</span>
          </div>

          <el-alert
            v-if="errorMessage"
            type="warning"
            :closable="false"
            :title="errorMessage"
            show-icon
            class="error-alert"
          />

          <div class="form-actions">
            <el-button @click="clearQuestion">清空</el-button>
            <el-button type="primary" :loading="asking" @click="handleAsk">
              开始测试
            </el-button>
          </div>
        </el-form>
      </div>

      <div class="result-card">
        <div class="result-header">
          <div class="result-title">召回结果</div>
          <div class="result-meta">
            <el-tag effect="plain">片段 {{ retrievedCount }}</el-tag>
            <el-tag effect="plain" type="info">文件 {{ uniqueFileCount }}</el-tag>
            <el-tag effect="plain" type="warning">均分 {{ averageScore }}</el-tag>
            <el-tag effect="plain" type="success">模型 {{ modelUsed }}</el-tag>
          </div>
        </div>

        <div v-if="asking" class="loading-wrap">
          <el-skeleton animated>
            <template #template>
              <el-skeleton-item variant="text" style="width: 36%" />
              <el-skeleton-item variant="rect" style="width: 100%; height: 90px; margin-top: 12px" />
              <el-skeleton-item variant="rect" style="width: 100%; height: 90px; margin-top: 12px" />
              <el-skeleton-item variant="rect" style="width: 100%; height: 90px; margin-top: 12px" />
            </template>
          </el-skeleton>
        </div>

        <template v-else>
          <div v-if="answerData?.answer" class="answer-card">
            <div class="answer-label">接口返回回答</div>
            <div class="answer-content">{{ answerData.answer }}</div>
          </div>

          <el-scrollbar v-if="sortedCitations.length" class="citation-scroll">
            <div class="citation-list">
              <div
                v-for="item in sortedCitations"
                :key="`${item.kb_id}-${item.chunk_id}`"
                class="citation-item"
              >
                <div class="citation-headline">
                  <div class="headline-left">
                    <el-tag size="small" type="success" effect="plain">{{ item.kb_name }}</el-tag>
                    <span class="file-name">{{ item.file_name }}</span>
                  </div>
                  <el-tag size="small" type="warning">Score {{ item.score.toFixed(4) }}</el-tag>
                </div>

                <el-progress
                  :percentage="scorePercent(item.score)"
                  :stroke-width="8"
                  :show-text="false"
                  :color="getScoreColor(item.score)"
                />

                <div class="citation-content">{{ item.content }}</div>
              </div>
            </div>
          </el-scrollbar>

          <div v-else class="empty-wrap">
            <el-empty :image-size="96" description="暂无召回结果，填写问题后开始测试" />
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
const errorMessage = ref('')

const questionLength = computed(() => question.value.trim().length)
// 知识库隔离：table_desc / few_shot 为 text2SQL 专用保留库，文档召回测试只可选文档库
const documentKbs = computed(() =>
  props.knowledgeBases.filter(item => (item.purpose ?? 'document') === 'document'),
)
const sortedCitations = computed(() => {
  const citations = answerData.value?.citations || []
  return [...citations].sort((a, b) => b.score - a.score)
})
const retrievedCount = computed(() => answerData.value?.retrieved_count ?? 0)
const uniqueFileCount = computed(() => new Set(sortedCitations.value.map(item => item.file_id)).size)
const averageScore = computed(() => {
  if (!sortedCitations.value.length) return '--'
  const total = sortedCitations.value.reduce((sum, item) => sum + item.score, 0)
  return (total / sortedCitations.value.length).toFixed(4)
})
const modelUsed = computed(() => answerData.value?.model_used || '--')
const selectedKbNames = computed(() => {
  const selected = new Set(selectedKbIds.value)
  return props.knowledgeBases.filter(item => selected.has(item.id)).map(item => item.name)
})

watch(
  () => props.kbId,
  value => {
    if (!value) {
      selectedKbIds.value = []
      return
    }
    const kb = props.knowledgeBases.find(item => item.id === value)
    const isReserved = kb != null && (kb.purpose ?? 'document') !== 'document'
    selectedKbIds.value = isReserved ? [] : [value]
  },
  { immediate: true },
)

function scorePercent(score: number) {
  const normalized = Math.min(Math.max(score, 0), 1)
  return Number((normalized * 100).toFixed(1))
}

function getScoreColor(score: number) {
  if (score >= 0.8) return '#2f6555'
  if (score >= 0.6) return '#c98a1e'
  return '#d35d4a'
}

function clearQuestion() {
  question.value = ''
}

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
  errorMessage.value = ''
  answerData.value = null
  try {
    answerData.value = await retrieveKnowledgeBase({
      kb_ids: selectedKbIds.value,
      question: question.value.trim(),
    })
  } catch (error: any) {
    errorMessage.value = error?.message || '召回请求失败，请稍后重试'
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
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 18px 40px rgba(32, 50, 45, 0.08);
  box-sizing: border-box;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
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
  grid-template-columns: minmax(320px, 0.88fr) minmax(0, 1.12fr);
  gap: 20px;
}

.tester-form,
.result-card {
  min-height: 0;
  padding: 18px;
  border-radius: 16px;
  background: #f7faf8;
  border: 1px solid #e5ece6;
}

.input-overview {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.selected-kb-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.selected-label {
  color: #6b7c76;
  font-size: 12px;
}

.selected-empty {
  font-size: 12px;
  color: #9caea8;
}

.error-alert {
  margin-bottom: 12px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.result-card {
  display: flex;
  flex-direction: column;
}

.result-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.result-title {
  font-size: 16px;
  font-weight: 700;
  color: #1b3a31;
}

.result-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.answer-card {
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #dbe8e2;
  background: #ffffff;
}

.answer-label {
  font-size: 12px;
  font-weight: 700;
  color: #6b7c76;
}

.answer-content {
  margin-top: 6px;
  white-space: pre-wrap;
  line-height: 1.7;
  color: #203e35;
  font-size: 13px;
}

.loading-wrap,
.empty-wrap {
  flex: 1;
  min-height: 0;
  display: grid;
  place-items: center;
}

.citation-scroll {
  flex: 1;
  min-height: 0;
}

.citation-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 8px;
}

.citation-item {
  padding: 14px;
  border-radius: 12px;
  border: 1px solid #dfe9e4;
  background: #ffffff;
}

.citation-headline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.headline-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.file-name {
  font-size: 12px;
  color: #567068;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.citation-content {
  margin-top: 10px;
  white-space: pre-wrap;
  line-height: 1.7;
  color: #2b473f;
  font-size: 13px;
  word-break: break-word;
}

@media (max-width: 1080px) {
  .tester-grid {
    grid-template-columns: 1fr;
  }

  .panel-header,
  .result-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .result-meta {
    justify-content: flex-start;
  }
}
</style>
