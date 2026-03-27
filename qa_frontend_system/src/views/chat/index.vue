<template>
  <section class="chat-page">
    <aside class="session-panel">
      <div class="session-panel-header">
        <div>
          <div class="eyebrow">Conversation</div>
          <h1>聊天记录</h1>
        </div>
        <el-button type="primary" @click="handleCreateSession">新增对话</el-button>
      </div>

      <div class="session-list">
        <button
          v-for="session in sessions"
          :key="session.id"
          type="button"
          :class="['session-item', { active: session.id === activeSessionId }]"
          @click="handleSelectSession(session.id)"
        >
          <div class="session-title">{{ session.title }}</div>
          <div class="session-time">{{ formatTime(session.updated_at) }}</div>
        </button>
      </div>
    </aside>

    <div class="chat-main">
      <header class="chat-main-header">
        <div>
          <div class="header-title">{{ activeSession?.title || '新对话' }}</div>
          <div class="header-subtitle">{{ modelSummary }}</div>
        </div>
      </header>

      <div class="chat-body">
        <main class="conversation-panel">
          <div v-if="!messages.length" class="empty-state">
            <h3>开始一段新对话</h3>
            <p>输入问题后，系统会基于全部知识库检索并生成回答。</p>
          </div>

          <div v-else class="message-list">
            <article v-for="message in messages" :key="message.id" :class="['message-card', message.role]">
              <div class="message-role">{{ message.role === 'user' ? '你' : '助手' }}</div>
              <div class="message-content">{{ message.content }}</div>
            </article>
          </div>

          <footer class="composer">
            <el-input
              v-model="question"
              type="textarea"
              :rows="4"
              resize="none"
              maxlength="4000"
              show-word-limit
              placeholder="输入问题并发送"
              @keydown.enter.exact.prevent="handleSend"
            />
            <div class="composer-actions">
              <span class="composer-tip">Enter 发送，Shift + Enter 换行</span>
              <el-button type="primary" :loading="sending" @click="handleSend">发送</el-button>
            </div>
          </footer>
        </main>

        <aside class="meta-panel">
          <section class="meta-card">
            <div class="meta-title">模型回复</div>
            <div class="meta-body">
              {{ latestAssistant?.content || '当前会话还没有模型回复。' }}
            </div>
          </section>

          <section class="meta-card">
            <div class="meta-title">当前会话涉及文档</div>
            <div v-if="documents.length" class="document-list">
              <article v-for="doc in documents" :key="`${doc.kb_id}-${doc.file_id}`" class="document-item">
                <div class="document-kb">{{ doc.kb_name }}</div>
                <div class="document-name">{{ doc.file_name }}</div>
              </article>
            </div>
            <el-empty v-else description="暂无文档" />
          </section>
        </aside>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  appendChatMessage,
  createChatSession,
  getChatSessionDetail,
  listChatSessions,
  type ChatDocumentItem,
  type ChatMessage,
  type ChatSessionSummary
} from '../../api/chat'

const sessions = ref<ChatSessionSummary[]>([])
const activeSessionId = ref<number | null>(null)
const messages = ref<ChatMessage[]>([])
const documents = ref<ChatDocumentItem[]>([])
const question = ref('')
const sending = ref(false)

const activeSession = computed(() =>
  sessions.value.find(item => item.id === activeSessionId.value) || null
)

const latestAssistant = computed(() =>
  [...messages.value].reverse().find(item => item.role === 'assistant') || null
)

const modelSummary = computed(() => {
  if (!latestAssistant.value) {
    return '当前对话尚未生成回复'
  }
  return latestAssistant.value.model_used || '未配置生成模型'
})

const formatTime = (value: string) =>
  new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })

const loadSessions = async () => {
  sessions.value = await listChatSessions()
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
}

const loadSessionDetail = async (sessionId: number) => {
  const detail = await getChatSessionDetail(sessionId)
  activeSessionId.value = detail.session.id
  messages.value = detail.messages
  documents.value = detail.involved_documents
  sessions.value = sessions.value.map(item => (item.id === detail.session.id ? detail.session : item))
}

const handleCreateSession = async () => {
  const session = await createChatSession()
  sessions.value = [session, ...sessions.value]
  activeSessionId.value = session.id
  messages.value = []
  documents.value = []
  question.value = ''
}

const handleSelectSession = async (sessionId: number) => {
  if (sessionId === activeSessionId.value) return
  await loadSessionDetail(sessionId)
}

const handleSend = async () => {
  const content = question.value.trim()
  if (!content) {
    ElMessage.warning('请输入问题')
    return
  }

  let sessionId = activeSessionId.value
  if (!sessionId) {
    const created = await createChatSession()
    sessions.value = [created, ...sessions.value]
    sessionId = created.id
    activeSessionId.value = sessionId
  }

  sending.value = true
  try {
    const response = await appendChatMessage(sessionId, content)
    question.value = ''
    messages.value = [...messages.value, response.user_message, response.assistant_message]
    documents.value = response.involved_documents
    sessions.value = [
      response.session,
      ...sessions.value.filter(item => item.id !== response.session.id)
    ]
    activeSessionId.value = response.session.id
  } finally {
    sending.value = false
  }
}

onMounted(() => {
  loadSessions()
})
</script>

<style scoped>
.chat-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  background:
    radial-gradient(circle at top left, rgba(230, 187, 80, 0.18), transparent 24%),
    linear-gradient(180deg, #f7f2e7 0%, #eef3ef 100%);
}

.session-panel {
  padding: 24px 18px;
  background: linear-gradient(180deg, #17302a 0%, #1f433d 100%);
  color: #f7f7ef;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 18px;
}

.session-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.eyebrow {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #f2d98d;
}

h1 {
  margin: 8px 0 0;
  font-size: 28px;
}

.session-list {
  overflow: auto;
  display: grid;
  gap: 10px;
}

.session-item {
  width: 100%;
  padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.session-item.active {
  background: linear-gradient(135deg, #f2d98d 0%, #eef3cf 100%);
  color: #16312a;
}

.session-title {
  font-weight: 700;
  line-height: 1.5;
}

.session-time {
  margin-top: 6px;
  font-size: 12px;
  opacity: 0.7;
}

.chat-main {
  padding: 24px;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 18px;
}

.chat-main-header {
  padding: 20px 24px;
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(22, 49, 42, 0.08);
}

.header-title {
  font-size: 30px;
  font-weight: 800;
  color: #17312a;
}

.header-subtitle {
  margin-top: 8px;
  color: #62736c;
}

.chat-body {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 18px;
}

.conversation-panel,
.meta-card {
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(22, 49, 42, 0.08);
  box-shadow: 0 18px 46px rgba(27, 47, 41, 0.08);
}

.conversation-panel {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  padding: 20px;
}

.message-list {
  min-height: 0;
  overflow: auto;
  display: grid;
  gap: 14px;
  padding-right: 6px;
}

.empty-state {
  display: grid;
  place-items: center;
  text-align: center;
  color: #62746e;
}

.message-card {
  max-width: 84%;
  padding: 16px 18px;
  border-radius: 24px;
}

.message-card.user {
  margin-left: auto;
  background: linear-gradient(135deg, #183c36 0%, #2f6159 100%);
  color: #f7faf7;
}

.message-card.assistant {
  background: linear-gradient(180deg, #fffefb 0%, #f5f7f2 100%);
  border: 1px solid #e7ece4;
}

.message-role {
  font-size: 12px;
  color: #6d7d77;
}

.message-card.user .message-role {
  color: rgba(247, 250, 247, 0.72);
}

.message-content {
  margin-top: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.8;
}

.composer {
  display: grid;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid #e9eee7;
}

.composer-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.composer-tip {
  font-size: 12px;
  color: #6c7d76;
}

.meta-panel {
  display: grid;
  gap: 18px;
}

.meta-card {
  padding: 18px;
}

.meta-title {
  font-size: 14px;
  font-weight: 700;
  color: #1a342d;
}

.meta-body {
  margin-top: 12px;
  white-space: pre-wrap;
  line-height: 1.8;
  color: #304942;
  max-height: 320px;
  overflow: auto;
}

.document-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
  max-height: 360px;
  overflow: auto;
}

.document-item {
  padding: 12px 14px;
  border-radius: 18px;
  background: #f8faf6;
  border: 1px solid #e9eee6;
}

.document-kb {
  font-size: 12px;
  color: #6a7c75;
}

.document-name {
  margin-top: 6px;
  font-weight: 700;
  color: #17302a;
  word-break: break-word;
}

@media (max-width: 1100px) {
  .chat-page {
    grid-template-columns: 1fr;
  }

  .chat-body {
    grid-template-columns: 1fr;
  }
}
</style>
