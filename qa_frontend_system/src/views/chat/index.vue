<template>
  <section class="chat-page">
    <el-a-conversations class="session-sidebar">
      <template #header>
        <div class="session-header">
          <h1 class="title">💬 聊天记录</h1>
          <el-button type="primary" size="small" @click="handleCreateSession">
            + 新聊天
          </el-button>
        </div>
      </template>

      <template #scroll>
        <div class="session-list">
          <button
            v-for="session in sessions"
            :key="session.id"
            type="button"
            :class="['session-item', { active: session.id === activeSessionId }]"
            @click="handleSelectSession({ key: session.id })"
          >
            <div class="session-info">
              <div class="session-title">{{ session.title }}</div>
              <div class="session-time">{{ formatTime(session.updated_at) }}</div>
            </div>
            <div class="session-actions" @click.stop>
              <el-tooltip content="重命名" placement="top">
                <el-button
                  link
                  size="small"
                  class="action-btn"
                  @click="handleRenameSession(session)"
                >✏️</el-button>
              </el-tooltip>
              <el-tooltip content="删除" placement="top">
                <el-button
                  link
                  size="small"
                  class="action-btn action-delete"
                  @click="handleDeleteSession(session.id)"
                >🗑️</el-button>
              </el-tooltip>
            </div>
          </button>
        </div>
      </template>
    </el-a-conversations>

    <div class="chat-main">
      <div class="message-container" ref="messageContainerRef">
        <div v-if="!messages.length && !streamingContent" class="empty-state">
          <div class="empty-content">
            <div class="empty-icon">🤖</div>
            <h3>有什么可以帮忙的？</h3>
            <p>基于知识库的智能问答助手</p>
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
                {{ message.role === 'user' ? '我' : '湖' }}
              </div>
            </template>

            <template #header>
              <div class="message-header">
                <template v-if="message.role === 'assistant'">
                  <span class="sender-name">湖小师</span>
                  <el-tag v-if="message.model_used" size="small" type="info" effect="plain">
                    {{ message.model_used }}
                  </el-tag>
                  <el-tag v-if="message.intent" size="small" :type="intentTagType(message.intent)" effect="light">
                    {{ intentLabel(message.intent) }}
                  </el-tag>
                </template>
                <span class="message-time">{{ formatTime(message.created_at) }}</span>
              </div>
            </template>

            <template v-if="message.role === 'assistant'" #footer>
              <div v-if="message.generated_sql" class="message-sql-block">
                <div class="sql-title">📊 执行的 SQL</div>
                <pre class="sql-code">{{ message.generated_sql }}</pre>
                <div v-if="parseSqlResult(message.sql_result_json)" class="sql-result-table">
                  <el-table
                    :data="parseSqlResult(message.sql_result_json)!.rows"
                    size="small"
                    max-height="260"
                    stripe
                    border
                  >
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
                  涉及文档 ({{ getMessageDocuments(message).length }})
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
                  引用 {{ message.retrieved_count }} 条片段
                </div>
              </div>
            </template>
          </el-a-bubble>

          <el-a-bubble
            v-if="streamingContent || streamingStatus"
            :key="-1"
            placement="start"
            :content="streamingContent || '...'"
            :is-markdown="true"
            :typing="!!streamingContent"
            shape="corner"
            class="message-bubble assistant streaming"
          >
            <template #avatar>
              <div class="avatar assistant-avatar">湖</div>
            </template>
            <template #header>
              <div class="message-header">
                <span class="sender-name">湖小师</span>
                <el-tag v-if="streamingIntent" size="small" :type="intentTagType(streamingIntent)" effect="light">
                  {{ intentLabel(streamingIntent) }}
                </el-tag>
                <el-tag v-if="streamingStatus" size="small" type="primary" effect="plain" class="status-tag">
                  <span class="status-dot" /> {{ streamingStatus }}
                </el-tag>
              </div>
            </template>
            <template v-if="streamingSql" #footer>
              <div class="message-sql-block">
                <div class="sql-title">📊 执行的 SQL</div>
                <pre class="sql-code">{{ streamingSql }}</pre>
                <div v-if="streamingSqlResult" class="sql-result-table">
                  <el-table
                    :data="streamingSqlResult.rows"
                    size="small"
                    max-height="260"
                    stripe
                    border
                  >
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

      <footer class="chat-footer">
        <el-a-sender
          :model-value="composerValue"
          :loading="streaming"
          placeholder="输入问题并发送... (Enter 发送，Shift + Enter 换行)"
          :enter-break="false"
          @update:modelValue="handleComposerChange"
          @send="handleSend"
          @cancel="handleStop"
          class="chat-sender"
        >
          <template #actions>
            <span class="char-count">{{ composerValue.length }}/4000</span>
          </template>
        </el-a-sender>
      </footer>
    </div>
  </section>
</template>

<script setup lang="ts">
// 修复点 1：删除了这里多余的 computed 引入
import { nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ElABubble, ElABubbleList, ElAConversations, ElASender } from 'element-ai-vue'
import { Document } from '@element-plus/icons-vue'

import {
  appendChatMessageStream,
  createChatSession,
  getChatSessionDetail,
  listChatSessions,
  deleteChatSession,
  renameChatSession,
  type ChatCitation,
  type ChatDocumentItem,
  type ChatMessage,
  type ChatSessionSummary,
  type SqlResultData,
} from '../../api/chat'

// ============ 类型定义 ============
// 修复点 2：删除了这里无用的 ConversationItem 接口
interface BubbleListInstance {
  scrollToBottom?: () => void
  scrollToTop?: () => void
}

// ============ 状态 ============
const sessions = ref<ChatSessionSummary[]>([])
const activeSessionId = ref<number | null>(null)
const messages = ref<ChatMessage[]>([])
const composerValue = ref('')
const streaming = ref(false)
const streamingContent = ref('')
const streamingCitations = ref<ChatCitation[]>([])
const streamingIntent = ref<string | null>(null)
const streamingStatus = ref<string | null>(null)
const streamingSql = ref<string | null>(null)
const streamingSqlResult = ref<SqlResultData | null>(null)
const messageContainerRef = ref<HTMLDivElement | null>(null)
const bubbleListRef = ref<BubbleListInstance | null>(null)
const abortStream = ref<(() => void) | null>(null)

// ============ 方法 ============
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
    minute: '2-digit'
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
        file_name: citation.file_name
      })
    }
  }
  return [...map.values()]
}

// 意图相关辅助函数
const intentLabel = (intent?: string | null): string => {
  const map: Record<string, string> = {
    casual_chat: '💬 闲聊',
    data_query: '📊 查数据',
    doc_search: '📄 查文档',
  }
  return map[intent || ''] || intent || ''
}

const intentTagType = (intent?: string | null): string => {
  const map: Record<string, string> = {
    casual_chat: 'info',
    data_query: 'warning',
    doc_search: 'success',
  }
  return map[intent || ''] || 'info'
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

const handleComposerChange = (value: string) => {
  composerValue.value = value
}

// ============ 会话操作 ============
const loadSessions = async () => {
  try {
    const data = await listChatSessions()
    sessions.value = data
    if (!sessions.value.length) {
      const created = await createChatSession()
      sessions.value = [created]
    }
    if (!activeSessionId.value && sessions.value.length) {
      activeSessionId.value = sessions.value[0].id
    }
    if (activeSessionId.value) {
      await loadSessionDetail(activeSessionId.value)
    }
  } catch (error) {
    ElMessage.error('加载会话列表失败')
  }
}

const loadSessionDetail = async (sessionId: number) => {
  try {
    const detail = await getChatSessionDetail(sessionId)
    activeSessionId.value = detail.session.id
    messages.value = detail.messages
    sessions.value = sessions.value.map(item =>
      item.id === detail.session.id ? detail.session : item
    )
    await scrollToBottom()
  } catch (error) {
    ElMessage.error('加载会话详情失败')
  }
}

const handleCreateSession = async () => {
  try {
    const session = await createChatSession()
    sessions.value = [session, ...sessions.value]
    activeSessionId.value = session.id
    messages.value = []
    composerValue.value = ''
    ElMessage.success('创建会话成功')
  } catch (error) {
    ElMessage.error('创建会话失败')
  }
}

const handleDeleteSession = async (sessionId: number) => {
  try {
    await deleteChatSession(sessionId)
    sessions.value = sessions.value.filter(s => s.id !== sessionId)
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = sessions.value[0]?.id ?? null
      if (activeSessionId.value) {
        await loadSessionDetail(activeSessionId.value)
      } else {
        messages.value = []
      }
    }
    ElMessage.success('会话已删除')
  } catch {
    ElMessage.error('删除失败')
  }
}

const handleRenameSession = async (session: ChatSessionSummary) => {
  const newTitle = window.prompt('请输入新的会话名称', session.title)
  if (!newTitle || newTitle.trim() === session.title) return
  try {
    const updated = await renameChatSession(session.id, newTitle.trim())
    const idx = sessions.value.findIndex(s => s.id === session.id)
    if (idx !== -1) sessions.value[idx] = updated
    ElMessage.success('重命名成功')
  } catch {
    ElMessage.error('重命名失败')
  }
}

const handleSelectSession = async ({ key }: { key: number }) => {
  if (streaming.value) {
    ElMessage.warning('请等待当前回复完成')
    return
  }
  if (key === activeSessionId.value) return
  await loadSessionDetail(key)
}

// ============ 消息发送（流式） ============
const handleSend = async () => {
  // 修复点 3：过滤富文本编辑器带来的 HTML 标签 (<p>等) 和 &nbsp; 空格
  const content = composerValue.value
    .replace(/<[^>]+>/g, '')  // 剥离所有 HTML 标签
    .replace(/&nbsp;/ig, ' ') // 把富文本的空格实体转换为普通空格
    .trim()

  if (!content || streaming.value) {
    if (!content) ElMessage.warning('请输入问题')
    return
  }

  let sessionId = activeSessionId.value
  if (!sessionId) {
    try {
      const created = await createChatSession()
      sessions.value = [created, ...sessions.value]
      sessionId = created.id
      activeSessionId.value = sessionId
    } catch (error) {
      ElMessage.error('创建会话失败')
      return
    }
  }

  // 乐观更新 UI - 添加用户消息
  const tempUserMessage: ChatMessage = {
    id: Date.now(),
    session_id: sessionId,
    role: 'user',
    content: content,
    created_at: new Date().toISOString()
  }
  messages.value.push(tempUserMessage)
  composerValue.value = ''
  await scrollToBottom()

  // 开始流式输出
  streaming.value = true
  streamingContent.value = ''
  streamingCitations.value = []
  streamingIntent.value = null
  streamingStatus.value = null
  streamingSql.value = null
  streamingSqlResult.value = null

  // 调用流式 API
  abortStream.value = appendChatMessageStream(
    sessionId,
    content, // 这里发送给后端的也是清洗后的纯文本
    {
      onUserMessage: (userMsg) => {
        // 替换临时消息为真实用户消息
        messages.value = messages.value.filter(m => m.id !== tempUserMessage.id)
        messages.value.push({
          id: userMsg.id,
          session_id: sessionId!,
          role: 'user',
          content: userMsg.content,
          created_at: userMsg.created_at
        })
        scrollToBottom()
      },

      onSessionInfo: (session) => {
        // 更新会话信息
        sessions.value = [
          {
            id: session.id,
            title: session.title,
            updated_at: session.updated_at,
            created_at: sessions.value.find(s => s.id === session.id)?.created_at || session.updated_at
          },
          ...sessions.value.filter(item => item.id !== session.id)
        ]
      },

      onIntent: (data) => {
        streamingIntent.value = data.intent
      },

      onStatus: (data) => {
        streamingStatus.value = data.message
        scrollToBottom()
      },

      onCitations: (citations) => {
        streamingCitations.value = citations
      },

      onSql: (data) => {
        streamingSql.value = data.sql
        scrollToBottom()
      },

      onSqlResult: (data) => {
        streamingSqlResult.value = data
        scrollToBottom()
      },

      onDelta: (delta) => {
        streamingContent.value += delta
        scrollToBottom()
      },

      onDone: (assistantMsg) => {
        // 流式完成，添加完整助手消息
        streaming.value = false
        const finalMessage: ChatMessage = {
          id: assistantMsg.id,
          session_id: sessionId!,
          role: 'assistant',
          content: assistantMsg.content,
          model_used: assistantMsg.model_used,
          retrieved_count: assistantMsg.retrieved_count,
          citations: streamingCitations.value,
          intent: assistantMsg.intent || streamingIntent.value,
          generated_sql: streamingSql.value,
          sql_result_json: streamingSqlResult.value ? JSON.stringify(streamingSqlResult.value) : null,
          created_at: assistantMsg.created_at
        }
        messages.value.push(finalMessage)
        streamingContent.value = ''
        streamingCitations.value = []
        streamingIntent.value = null
        streamingStatus.value = null
        streamingSql.value = null
        streamingSqlResult.value = null
        scrollToBottom()
      },

      onError: (error) => {
        streaming.value = false
        streamingContent.value = ''
        streamingCitations.value = []
        streamingIntent.value = null
        streamingStatus.value = null
        streamingSql.value = null
        streamingSqlResult.value = null
        ElMessage.error(error.message || '发送失败')
        // 移除临时用户消息
        messages.value = messages.value.filter(m => m.id !== tempUserMessage.id)
      }
    }
  )
}

const handleStop = () => {
  if (abortStream.value) {
    abortStream.value()
    abortStream.value = null
  }
  streaming.value = false
  streamingContent.value = ''
  streamingCitations.value = []
  streamingIntent.value = null
  streamingStatus.value = null
  streamingSql.value = null
  streamingSqlResult.value = null
  ElMessage.info('已停止生成')
}

// ============ 生命周期 ============
onMounted(() => {
  loadSessions()
})

// 监听流式内容变化自动滚动
watch(streamingContent, () => {
  scrollToBottom()
})
</script>

<style scoped>
/* ============ 整体布局 ============ */
.chat-page {
  display: flex;
  height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
}

/* ============ 侧边栏 ============ */
.session-sidebar {
  width: 280px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.04);
}

.session-sidebar :deep(.el-a-conversations-header) {
  padding: 0;
}

.session-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #e4e7ed;
}

.title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
}

.session-item {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #303133;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.session-item:hover {
  background: #f5f7fa;
}

.session-item.active {
  background: #ecf5ff;
  font-weight: 500;
  color: #409eff;
}

.session-title {
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-time {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

/* ============ 主聊天区 ============ */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
}

.message-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

/* ============ 空状态 ============ */
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
  font-size: 64px;
  margin-bottom: 16px;
}

.empty-content h3 {
  font-size: 24px;
  font-weight: 500;
  color: #303133;
  margin: 0 0 8px 0;
}

.empty-content p {
  font-size: 14px;
  color: #909399;
  margin: 0;
}

/* ============ 消息列表 ============ */
.message-list {
  max-width: 900px;
  margin: 0 auto;
}

/* 消息气泡通用样式 */
.message-bubble {
  margin-bottom: 16px;
}

/* 用户消息样式 */
.message-bubble.user :deep(.el-a-bubble-content) {
  background: linear-gradient(135deg, #409eff 0%, #1677ff 100%);
  color: #fff;
  border-radius: 12px 12px 4px 12px;
}

.message-bubble.user :deep(.el-a-bubble-content-text) {
  color: #fff;
}

/* 助手消息样式 */
.message-bubble.assistant :deep(.el-a-bubble-content) {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 12px 12px 12px 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

/* 流式消息样式 */
.message-bubble.streaming :deep(.el-a-bubble-content) {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1);
}

/* 头像样式 */
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

/* 头部信息样式 */
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

/* 涉及文档样式 */
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

/* ============ SQL 结果块 ============ */
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
  margin: 0 0 8px 0;
}

.sql-result-table {
  margin-top: 8px;
}

.sql-result-table :deep(.el-table) {
  font-size: 12px;
}

/* ============ 状态标签动画 ============ */
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

/* ============ 底部输入区 ============ */
.chat-footer {
  background: #fff;
  border-top: 1px solid #e4e7ed;
  padding: 16px 20px;
}

.chat-sender {
  max-width: 900px;
  margin: 0 auto;
}

.chat-sender :deep(.el-a-sender-input) {
  background: #f5f7fa;
  border-radius: 12px;
  border: 1px solid #e4e7ed;
}

.chat-sender :deep(.el-a-sender-input:focus-within) {
  background: #fff;
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1);
}

.char-count {
  font-size: 12px;
  color: #909399;
}

/* ============ 响应式 ============ */
@media (max-width: 768px) {
  .session-sidebar {
    display: none;
  }
}
</style>