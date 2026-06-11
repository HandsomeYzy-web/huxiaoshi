<template>
  <div class="message-container">
    <div v-if="!messages.length && !streamingContent && !streaming" class="empty-state">
      <div class="empty-content">
        <div class="empty-emblem">
          <span class="emblem-char">识</span>
        </div>
        <h3>你好，我是湖小识</h3>
        <p>基于学院知识库的内容、检索结果与数据查询能力，为你提供可靠的解答。</p>

        <div class="capability-cards">
          <div class="capability-card">
            <el-icon class="capability-icon"><Reading /></el-icon>
            <div class="capability-name">知识库问答</div>
            <div class="capability-desc">理解你的提问，结合馆藏资料作答</div>
          </div>
          <div class="capability-card">
            <el-icon class="capability-icon"><Document /></el-icon>
            <div class="capability-name">文档检索溯源</div>
            <div class="capability-desc">标注引用来源，回答有据可查</div>
          </div>
          <div class="capability-card">
            <el-icon class="capability-icon"><DataAnalysis /></el-icon>
            <div class="capability-name">数据智能查询</div>
            <div class="capability-desc">用自然语言查询结构化数据</div>
          </div>
        </div>

        <p class="empty-hint">在下方输入框中提出你的第一个问题吧</p>
      </div>
    </div>

    <el-a-bubble-list v-else ref="bubbleListRef" class="message-list">
      <el-a-bubble
        v-for="message in messages"
        :key="message.id"
        :placement="message.role === 'user' ? 'end' : 'start'"
        :content="message.content"
        :is-markdown="message.role === 'assistant'"
        shape="corner"
        :class="['message-bubble', message.role]"
      >
        <template #avatar>
          <div :class="['avatar', message.role === 'user' ? 'user-avatar' : 'assistant-avatar']">
            {{ message.role === 'user' ? '我' : '识' }}
          </div>
        </template>

        <template #header>
          <div class="message-header">
            <template v-if="message.role === 'assistant'">
              <span class="sender-name">湖小识</span>
              <el-tag v-if="message.model_used" size="small" class="model-tag" effect="plain">
                {{ message.model_used }}
              </el-tag>
            </template>
            <span class="message-time">{{ formatTime(message.created_at) }}</span>
          </div>
        </template>

        <template v-if="message.role === 'assistant'" #footer>
          <div v-if="parseSqlResult(message.sql_result_json)" class="message-sql-block">
            <div class="sql-title">
              <el-icon><DataAnalysis /></el-icon>
              查询结果
            </div>
            <div class="sql-result-table">
              <el-table :data="parseSqlResult(message.sql_result_json)!.rows" size="small" max-height="260" stripe border>
                <el-table-column
                  v-for="col in parseSqlResult(message.sql_result_json)!.columns"
                  :key="col"
                  :prop="col"
                  :label="col"
                  min-width="120"
                  show-overflow-tooltip
                />
              </el-table>
            </div>
          </div>
          <div v-if="getMessageDocuments(message).length" class="message-documents">
            <div class="documents-title">
              <el-icon><Document /></el-icon>
              关联文档（{{ getMessageDocuments(message).length }}）
            </div>
            <div class="documents-list">
              <el-tag
                v-for="doc in getMessageDocuments(message)"
                :key="`${message.id}-${doc.kb_id}-${doc.file_id}`"
                class="doc-tag"
                effect="light"
                size="small"
              >
                {{ doc.kb_name }} / {{ doc.file_name }}
              </el-tag>
            </div>
            <div v-if="message.retrieved_count" class="retrieved-info">
              共引用 {{ message.retrieved_count }} 个片段
            </div>
          </div>
        </template>
      </el-a-bubble>

      <el-a-bubble
        v-if="streaming || streamingContent || streamingStatus"
        ref="streamingBubbleRef"
        :key="-1"
        placement="start"
        :content="streamingContent"
        :is-markdown="true"
        :loading="streaming && !streamingContent && !streamingStatus && !streamingSqlResult"
        :typing="streaming"
        :typing-over="false"
        shape="corner"
        class="message-bubble assistant streaming"
      >
        <template #avatar>
          <div class="avatar assistant-avatar">识</div>
        </template>
        <template #header>
          <div class="message-header">
            <span class="sender-name">湖小识</span>
            <el-tag v-if="streamingStatus" size="small" class="status-tag" effect="plain">
              <span class="status-dot" /> {{ streamingStatus }}
            </el-tag>
          </div>
        </template>
        <template v-if="streamingSqlResult" #footer>
          <div class="message-sql-block">
            <div class="sql-title">
              <el-icon><DataAnalysis /></el-icon>
              查询结果
            </div>
            <div class="sql-result-table">
              <el-table :data="streamingSqlResult.rows" size="small" max-height="260" stripe border>
                <el-table-column
                  v-for="col in streamingSqlResult.columns"
                  :key="col"
                  :prop="col"
                  :label="col"
                  min-width="120"
                  show-overflow-tooltip
                />
              </el-table>
            </div>
          </div>
        </template>
      </el-a-bubble>
    </el-a-bubble-list>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { DataAnalysis, Document, Reading } from '@element-plus/icons-vue'

import type { ChatDocumentItem, ChatMessage, SqlResultData } from '../../api/chat'

interface BubbleListInstance {
  scrollToBottom?: () => void
}

interface StreamingBubbleInstance {
  overTyperwriter?: () => void
}

defineProps<{
  messages: ChatMessage[]
  streaming: boolean
  streamingContent: string
  streamingStatus: string | null
  streamingSqlResult: SqlResultData | null
}>()

const bubbleListRef = ref<BubbleListInstance | null>(null)
const streamingBubbleRef = ref<StreamingBubbleInstance | null>(null)

const formatTime = (value: string | Date): string => {
  const date = new Date(value)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()

  if (isToday) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const getMessageDocuments = (message: ChatMessage): ChatDocumentItem[] => {
  if (!message.citations?.length) return []

  const map = new Map<string, ChatDocumentItem>()
  for (const citation of message.citations) {
    const key = `${citation.kb_id}-${citation.file_id}`
    if (!map.has(key)) {
      map.set(key, {
        kb_id: citation.kb_id,
        kb_name: citation.kb_name,
        file_id: citation.file_id,
        file_name: citation.file_name,
      })
    }
  }
  return [...map.values()]
}


const parseSqlResult = (jsonStr?: string | null): SqlResultData | null => {
  if (!jsonStr) return null
  try {
    return JSON.parse(jsonStr)
  } catch {
    return null
  }
}

const scrollToBottom = async () => {
  await nextTick()
  bubbleListRef.value?.scrollToBottom?.()
}

const finishStreamingTyping = async () => {
  streamingBubbleRef.value?.overTyperwriter?.()
  await nextTick()
}

defineExpose({
  finishStreamingTyping,
  scrollToBottom,
})
</script>

<style scoped>
.message-container {
  flex: 1;
  overflow-y: auto;
  padding: 26px 20px 12px;
}

/* ---------- 空状态 ---------- */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
}

.empty-content {
  max-width: 720px;
  text-align: center;
  color: #6d5d52;
}

.empty-emblem {
  width: 84px;
  height: 84px;
  margin: 0 auto 20px;
  border-radius: 26px;
  display: grid;
  place-items: center;
  background: linear-gradient(150deg, #9f2f2f 0%, #7a1c20 100%);
  box-shadow: 0 16px 32px rgba(122, 28, 32, 0.28);
  position: relative;
}

.empty-emblem::after {
  content: '';
  position: absolute;
  inset: 5px;
  border-radius: 21px;
  border: 1px solid rgba(251, 233, 210, 0.4);
}

.emblem-char {
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: 40px;
  font-weight: 700;
  color: #fbe9d2;
}

.empty-content h3 {
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: 26px;
  font-weight: 700;
  color: #4e2f26;
  margin: 0 0 10px;
}

.empty-content p {
  font-size: 14px;
  line-height: 1.7;
  color: #8c6d59;
  margin: 0 auto;
  max-width: 460px;
}

.capability-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin: 28px 0 20px;
}

.capability-card {
  padding: 18px 16px;
  border: 1px solid #ecd9c2;
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(255, 253, 248, 0.95) 0%, rgba(252, 245, 236, 0.95) 100%);
  text-align: center;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.capability-card:hover {
  transform: translateY(-3px);
  border-color: #e0bd95;
  box-shadow: 0 12px 24px rgba(122, 28, 32, 0.1);
}

.capability-icon {
  font-size: 24px;
  color: #9f2f2f;
  margin-bottom: 10px;
}

.capability-name {
  font-size: 15px;
  font-weight: 600;
  color: #4e2f26;
  margin-bottom: 6px;
}

.capability-desc {
  font-size: 12px;
  line-height: 1.6;
  color: #9a8470;
}

.empty-hint {
  font-size: 13px;
  color: #b09a86 !important;
}

/* ---------- 消息列表 ---------- */
.message-list {
  max-width: 880px;
  margin: 0 auto;
}

.message-bubble {
  margin-bottom: 20px;
}

.message-bubble.user :deep(.el-a-bubble-content) {
  background: linear-gradient(135deg, #9f2f2f 0%, #7a1c20 100%);
  color: #fdf3e8;
  border-radius: 16px 16px 4px 16px;
  box-shadow: 0 8px 18px rgba(122, 28, 32, 0.22);
}

.message-bubble.user :deep(.el-a-bubble-content-text) {
  color: #fdf3e8;
}

.message-bubble.assistant :deep(.el-a-bubble-content) {
  background:
    linear-gradient(180deg, rgba(255, 253, 249, 0.98) 0%, rgba(253, 248, 240, 0.98) 100%);
  border: 1px solid #ecdfce;
  border-radius: 16px 16px 16px 4px;
  box-shadow: 0 6px 18px rgba(83, 38, 18, 0.07);
  color: #3c2f26;
}

.message-bubble.streaming :deep(.el-a-bubble-content) {
  border-color: #e0bd95;
  box-shadow: 0 0 0 3px rgba(201, 138, 58, 0.14), 0 6px 18px rgba(83, 38, 18, 0.08);
}

.avatar {
  width: 40px;
  height: 40px;
  border-radius: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: 18px;
  font-weight: 700;
}

.user-avatar {
  background: linear-gradient(135deg, #c98a3a 0%, #a9702a 100%);
  color: #fff7ea;
  box-shadow: 0 6px 14px rgba(169, 112, 42, 0.28);
}

.assistant-avatar {
  background: linear-gradient(150deg, #9f2f2f 0%, #7a1c20 100%);
  color: #fbe9d2;
  box-shadow: 0 6px 14px rgba(122, 28, 32, 0.28);
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
  font-size: 12px;
}

.sender-name {
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-weight: 700;
  font-size: 13px;
  color: #7a1c20;
}

.message-time {
  color: #a3917f;
}

.model-tag {
  --el-tag-bg-color: rgba(201, 138, 58, 0.1);
  --el-tag-border-color: rgba(201, 138, 58, 0.3);
  --el-tag-text-color: #a9702a;
}

/* ---------- 关联文档 ---------- */
.message-documents {
  margin-top: 14px;
  padding: 14px;
  background: rgba(250, 242, 232, 0.7);
  border: 1px solid #ecdfce;
  border-radius: 12px;
}

.documents-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #7a5c47;
  margin-bottom: 10px;
}

.documents-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.doc-tag {
  --el-tag-bg-color: rgba(159, 47, 47, 0.06);
  --el-tag-border-color: rgba(159, 47, 47, 0.2);
  --el-tag-text-color: #8a3a2f;
}

.retrieved-info {
  margin-top: 10px;
  font-size: 11px;
  color: #a9702a;
}

/* ---------- SQL 结果 ---------- */
.message-sql-block {
  margin-top: 14px;
  padding: 14px;
  background: rgba(252, 246, 238, 0.8);
  border-radius: 12px;
  border: 1px solid #ecdfce;
}

.sql-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #7a5c47;
  margin-bottom: 10px;
}

.sql-result-table {
  margin-top: 8px;
}

.sql-result-table :deep(.el-table) {
  font-size: 12px;
  --el-table-border-color: #ecdfce;
  --el-table-header-bg-color: #f7eddf;
  --el-table-header-text-color: #6d5340;
  --el-table-row-hover-bg-color: #fbf2e6;
  border-radius: 8px;
}

/* ---------- 状态提示 ---------- */
.status-tag {
  --el-tag-bg-color: rgba(159, 47, 47, 0.08);
  --el-tag-border-color: rgba(159, 47, 47, 0.24);
  --el-tag-text-color: #9f2f2f;
  animation: pulse 1.5s ease-in-out infinite;
}

.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #9f2f2f;
  margin-right: 4px;
  animation: blink 1s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

@media (max-width: 768px) {
  .capability-cards {
    grid-template-columns: 1fr;
  }
}
</style>
