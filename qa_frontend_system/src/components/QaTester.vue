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

      <div class="result-card">
        <div class="result-header">
          <span>召回片段</span>
          <span class="result-meta">{{ answerData?.retrieved_count ?? 0 }} 条</span>
        </div>

        <div class="scroll-container">
          <el-scrollbar v-if="answerData?.citations?.length" class="citation-scroll">
            <div class="citation-list">
              <div
                v-for="item in answerData.citations"
                :key="`${item.kb_id}-${item.chunk_id}`"
                class="citation-item"
              >
                <div class="citation-headline">
                  <span class="kb-tag">{{ item.kb_name }}</span>
                  <span class="file-name">{{ item.file_name }}</span>
                  <span class="score-tag">Score: {{ item.score.toFixed(4) }}</span>
                </div>
                <div class="citation-content">{{ item.content }}</div>
              </div>
            </div>
          </el-scrollbar>
          <el-empty v-else :image-size="100" description="还没有召回结果" />
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
// 注意：请确保你的 api 路径正确
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
    const res = await retrieveKnowledgeBase({
      kb_ids: selectedKbIds.value,
      question: question.value.trim()
    })
    answerData.value = res
  } catch (error) {
    console.error(error)
  } finally {
    asking.value = false
  }
}
</script>

<style scoped>
/* 1. 强制主容器撑满父级或视口 */
.panel-card {
  height: 100%;           /* 如果父级没高度，这里改写为 height: 80vh; */
  min-height: 500px;      /* 给个保底高度 */
  display: flex;
  flex-direction: column;
  padding: 24px;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.05);
  box-sizing: border-box;
  overflow: hidden;       /* 核心：禁止外层滚动 */
}

.panel-header {
  flex-shrink: 0;
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
  font-size: 13px;
  color: #86909c;
  margin-top: 4px;
}

/* 2. Grid 布局关键：必须设置 min-height: 0 */
.tester-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px;
  min-height: 0;
}

.tester-form {
  background: #f7f8fa;
  padding: 20px;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
}

/* 3. 右侧结果区域：核心约束 */
.result-card {
  display: flex;
  flex-direction: column;
  background: #f7f8fa;
  border-radius: 12px;
  padding: 20px;
  min-height: 0; /* 允许内部元素触发滚动 */
}

.result-header {
  flex-shrink: 0;
  margin-bottom: 16px;
  display: flex;
  justify-content: space-between;
  font-weight: 600;
}

/* 4. 滚动包裹容器：它是 el-scrollbar 的真正支点 */
.scroll-container {
  flex: 1;
  position: relative; /* 为绝对定位或 flex 内部计算提供基准 */
  min-height: 0;
}

.citation-scroll {
  position: absolute; /* 使用绝对定位撑满容器 */
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}

/* 列表样式 */
.citation-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 12px; /* 给滚动条留位 */
}

.citation-item {
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #e5e6eb;
}

.citation-headline {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  align-items: center;
}

.kb-tag {
  background: #e8f3ff;
  color: #165dff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
}

.file-name {
  font-size: 12px;
  color: #4e5969;
}

.score-tag {
  font-size: 12px;
  color: #ff7d00;
  margin-left: auto;
}

.citation-content {
  font-size: 14px;
  line-height: 1.6;
  color: #1d2129;
  white-space: pre-wrap;
  word-break: break-all;
}

.form-actions {
  margin-top: auto; /* 将按钮推到底部 */
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* 响应式适配 */
@media (max-width: 1024px) {
  .tester-grid {
    grid-template-columns: 1fr;
    overflow-y: auto; /* 手机端改为整体滚动 */
  }
  .panel-card {
    height: auto;
  }
  .scroll-container {
    height: 400px; /* 窄屏给个固定高度 */
    position: static;
  }
  .citation-scroll {
    position: static;
  }
}
</style>