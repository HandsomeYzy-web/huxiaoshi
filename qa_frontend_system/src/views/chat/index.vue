<template>
  <section class="chat-page">
    <ChatSessionSidebar
      :sessions="sessions"
      :active-session-id="activeSessionId"
      @create="handleCreateSession"
      @select="handleSelectSession"
      @rename="handleRenameSession"
      @delete="handleDeleteSession"
    />

    <div class="chat-main">
      <ChatConversation
        ref="conversationRef"
        :messages="messages"
        :streaming="streaming"
        :streaming-content="streamingContent"
        :streaming-status="streamingStatus"
        :streaming-sql-result="streamingSqlResult"
      />

      <footer class="chat-footer">
        <el-a-sender
          :model-value="composerValue"
          :loading="streaming"
          placeholder="输入问题后发送。Enter 发送，Shift + Enter 换行"
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
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import {
  appendChatMessageStream,
  createChatSession,
  deleteChatSession,
  getChatSessionDetail,
  listChatSessions,
  renameChatSession,
  type ChatCitation,
  type ChatMessage,
  type ChatSessionSummary,
  type SqlResultData,
} from '../../api/chat'
import ChatConversation from '../../components/chat/ChatConversation.vue'
import ChatSessionSidebar from '../../components/chat/ChatSessionSidebar.vue'

interface ConversationInstance {
  scrollToBottom: () => Promise<void>
  finishStreamingTyping?: () => Promise<void>
}

const sessions = ref<ChatSessionSummary[]>([])
const activeSessionId = ref<number | null>(null)
const messages = ref<ChatMessage[]>([])
const composerValue = ref('')
const streaming = ref(false)
const streamingCitations = ref<ChatCitation[]>([])
const streamingStatus = ref<string | null>(null)
const streamingSqlResult = ref<SqlResultData | null>(null)
const conversationRef = ref<ConversationInstance | null>(null)
const abortStream = ref<(() => void) | null>(null)
const streamingContent = ref('')

const clearStreamingPayload = () => {
  streamingContent.value = ''
  streamingCitations.value = []
  streamingStatus.value = null
  streamingSqlResult.value = null
}

const scrollToBottom = async () => {
  await conversationRef.value?.scrollToBottom?.()
}

const handleComposerChange = (value: string) => {
  composerValue.value = value
}

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
  } catch {
    ElMessage.error('加载会话列表失败')
  }
}

const loadSessionDetail = async (sessionId: number) => {
  try {
    const detail = await getChatSessionDetail(sessionId)
    activeSessionId.value = detail.session.id
    messages.value = detail.messages
    sessions.value = sessions.value.map(item => (item.id === detail.session.id ? detail.session : item))
    await scrollToBottom()
  } catch {
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
    ElMessage.success('已创建新对话')
  } catch {
    ElMessage.error('创建会话失败')
  }
}

const handleDeleteSession = async (sessionId: number) => {
  try {
    await deleteChatSession(sessionId)
    sessions.value = sessions.value.filter(item => item.id !== sessionId)
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
    ElMessage.error('删除会话失败')
  }
}

const handleRenameSession = async (session: ChatSessionSummary) => {
  const newTitle = window.prompt('请输入新的会话名称', session.title)
  if (!newTitle || newTitle.trim() === session.title) return
  try {
    const updated = await renameChatSession(session.id, newTitle.trim())
    const index = sessions.value.findIndex(item => item.id === session.id)
    if (index !== -1) sessions.value[index] = updated
    ElMessage.success('会话名称已更新')
  } catch {
    ElMessage.error('重命名失败')
  }
}

const handleSelectSession = async (sessionId: number) => {
  if (streaming.value) {
    ElMessage.warning('请等待当前回答完成')
    return
  }
  if (sessionId === activeSessionId.value) return
  await loadSessionDetail(sessionId)
}

const resetStreamingState = () => {
  streaming.value = false
  abortStream.value = null
  clearStreamingPayload()
}

const handleSend = async () => {
  const content = composerValue.value
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/ig, ' ')
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
    } catch {
      ElMessage.error('创建会话失败')
      return
    }
  }

  const tempUserMessage: ChatMessage = {
    id: Date.now(),
    session_id: sessionId,
    role: 'user',
    content,
    created_at: new Date().toISOString(),
  }
  messages.value.push(tempUserMessage)
  composerValue.value = ''
  await scrollToBottom()

  streaming.value = true
  clearStreamingPayload()

  abortStream.value = appendChatMessageStream(sessionId, content, {
    onUserMessage: userMsg => {
      messages.value = messages.value.filter(item => item.id !== tempUserMessage.id)
      messages.value.push({
        id: userMsg.id,
        session_id: sessionId!,
        role: 'user',
        content: userMsg.content,
        created_at: userMsg.created_at,
      })
      void scrollToBottom()
    },
    onSessionInfo: session => {
      sessions.value = [
        {
          id: session.id,
          title: session.title,
          updated_at: session.updated_at,
          created_at: sessions.value.find(item => item.id === session.id)?.created_at || session.updated_at,
        },
        ...sessions.value.filter(item => item.id !== session.id),
      ]
    },
    onStatus: data => {
      streamingStatus.value = data.message
      void scrollToBottom()
    },
    onCitations: citations => {
      streamingCitations.value = citations
    },
    onSqlResult: data => {
      streamingSqlResult.value = data
      void scrollToBottom()
    },
    onDelta: delta => {
      streamingContent.value += delta
    },
    onDone: assistantMsg => {
      // 等打字机队列自然播完再切换到最终消息，避免一次性全部输出
      const finalize = () => {
        void conversationRef.value?.finishStreamingTyping?.()
        abortStream.value = null
        streaming.value = false
        messages.value.push({
          id: assistantMsg.id,
          session_id: sessionId!,
          role: 'assistant',
          content: assistantMsg.content,
          model_used: assistantMsg.model_used,
          retrieved_count: assistantMsg.retrieved_count,
          citations: streamingCitations.value,
          sql_result_json: streamingSqlResult.value ? JSON.stringify(streamingSqlResult.value) : null,
          created_at: assistantMsg.created_at,
        })
        clearStreamingPayload()
        void scrollToBottom()
      }
      finalize()
    },
    onError: error => {
      resetStreamingState()
      ElMessage.error(error.message || '发送失败')
      messages.value = messages.value.filter(item => item.id !== tempUserMessage.id)
    },
  })
}

const handleStop = () => {
  if (abortStream.value) {
    abortStream.value()
    abortStream.value = null
  }
  resetStreamingState()
  ElMessage.info('已停止生成')
}

onMounted(() => {
  void loadSessions()
})

watch(streamingContent, () => {
  void scrollToBottom()
})
</script>

<style scoped>
.chat-page {
  display: flex;
  height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
}

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

@media (max-width: 768px) {
  .chat-page {
    display: block;
  }

  .chat-page :deep(.session-sidebar) {
    display: none;
  }
}
</style>
