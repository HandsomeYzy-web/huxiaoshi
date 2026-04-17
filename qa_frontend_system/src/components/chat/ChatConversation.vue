<template>
  <div class="message-container">
    <div v-if="!messages.length && !streamingContent && !streaming" class="empty-state">
      <div class="empty-content">
        <div class="empty-icon">QA</div>
        <h3>开始一个新的问题</h3>
        <p>这里会基于知识库内容、检索结果和数据查询能力给出回答。</p>
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
            {{ message.role === 'user' ? '我' : 'QA' }}
          </div>
        </template>

        <template #header>
          <div class="message-header">
            <template v-if="message.role === 'assistant'">
              <span class="sender-name">湖小识</span>
              <el-tag v-if="message.model_used" size="small" type="info" effect="plain">
                {{ message.model_used }}
              </el-tag>
            </template>
            <span class="message-time">{{ formatTime(message.created_at) }}</span>
          </div>
        </template>

        <template v-if="message.role === 'assistant'" #footer>
          <div v-if="parseSqlResult(message.sql_result_json)" class="message-sql-block">
            <div class="sql-title">查询结果</div>
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
                type="success"
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
          <div class="avatar assistant-avatar">QA</div>
        </template>
        <template #header>
          <div class="message-header">
            <span class="sender-name">湖小识</span>
            <el-tag v-if="streamingStatus" size="small" type="primary" effect="plain" class="status-tag">
              <span class="status-dot" /> {{ streamingStatus }}
            </el-tag>
          </div>
        </template>
        <template v-if="streamingSqlResult" #footer>
          <div class="message-sql-block">
            <div class="sql-title">查询结果</div>
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
import { Document } from '@element-plus/icons-vue'

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
  padding: 20px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.empty-content {
  text-align: center;
  color: #606266;
}

.empty-icon {
  width: 72px;
  height: 72px;
  margin: 0 auto 16px;
  border-radius: 18px;
  display: grid;
  place-items: center;
  font-size: 28px;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, #409eff 0%, #1677ff 100%);
}

.empty-content h3 {
  font-size: 24px;
  font-weight: 500;
  color: #303133;
  margin: 0 0 8px;
}

.empty-content p {
  font-size: 14px;
  color: #909399;
  margin: 0;
}

.message-list {
  max-width: 900px;
  margin: 0 auto;
}

.message-bubble {
  margin-bottom: 16px;
}

.message-bubble.user :deep(.el-a-bubble-content) {
  background: linear-gradient(135deg, #409eff 0%, #1677ff 100%);
  color: #fff;
  border-radius: 12px 12px 4px 12px;
}

.message-bubble.user :deep(.el-a-bubble-content-text) {
  color: #fff;
}

.message-bubble.assistant :deep(.el-a-bubble-content) {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 12px 12px 12px 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.message-bubble.streaming :deep(.el-a-bubble-content) {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1);
}

.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}

.user-avatar {
  background: linear-gradient(135deg, #409eff 0%, #1677ff 100%);
  color: #fff;
}

.assistant-avatar {
  background: linear-gradient(135deg, #67c23a 0%, #4caf50 100%);
  color: #fff;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 12px;
}

.sender-name {
  font-weight: 600;
  color: #606266;
}

.message-time {
  color: #909399;
}

.message-documents {
  margin-top: 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
}

.documents-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
}

.documents-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.retrieved-info {
  margin-top: 8px;
  font-size: 11px;
  color: #67c23a;
}

.message-sql-block {
  margin-top: 12px;
  padding: 12px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.sql-title {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}

.sql-code {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0 0 8px;
}

.sql-result-table {
  margin-top: 8px;
}

.sql-result-table :deep(.el-table) {
  font-size: 12px;
}

.status-tag {
  animation: pulse 1.5s ease-in-out infinite;
}

.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #409eff;
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
</style>
