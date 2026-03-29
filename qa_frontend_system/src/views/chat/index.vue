<template>
  <section class="chat-page">
    <el-a-conversations class="session-shell">
      <template #header>
        <div class="session-panel-header">
          <div>
            <div class="eyebrow">Conversation</div>
            <h1 class="title">聊天记录</h1>
          </div>
          <el-button type="primary" @click="handleCreateSession">新建对话</el-button>
        </div>
      </template>
      <template #scroll>
        <div class="session-list">
          <button v-for="session in sessions" :key="session.id" type="button" :class="['session-item', { active: session.id === activeSessionId }]" @click="handleSelectSession(session.id)"
          >
            <div class="session-title">{{ session.title }}</div>
            <div class="session-time">{{ formatTime(session.updated_at) }}</div>
          </button>
        </div>
      </template>
    </el-a-conversations>

    <div class="chat-main">
      <header class="chat-main-header">
        <div>
          <div class="header-title">{{ activeSession?.title || '新对话' }}</div>
          <div class="header-subtitle">{{ modelSummary }}</div>
        </div>
      </header>

      <main class="conversation-panel">
        <div v-if="!messages.length" class="empty-state">
          <h3>开始一段新对话</h3>
          <p>输入问题后，系统会基于全部知识库检索并生成回答。</p>
        </div>

        <el-a-bubble-list v-else ref="bubbleListRef" class="message-list">
          <div
            v-for="message in messages"
            :key="message.id"
            :class="['bubble-shell', message.role]"
          >
            <el-a-bubble
              :placement="message.role === 'user' ? 'end' : 'start'"
              :content="message.content"
              :is-markdown="message.role === 'assistant'"
              shape="corner"
            >
              <template #header>
                <div class="message-role">
                  {{ message.role === 'user' ? '我' : 'AI 助手' }}
                </div>
              </template>

              <template v-if="message.role === 'assistant' && getMessageDocuments(message).length" #footer>
                <div class="message-documents">
                  <div class="message-documents-title">涉及文档</div>
                  <div class="message-documents-list">
                    <article
                      v-for="doc in getMessageDocuments(message)"
                      :key="`${message.id}-${doc.kb_id}-${doc.file_id}`"
                      class="document-item"
                    >
                      <div class="document-kb">{{ doc.kb_name }}</div>
                      <div class="document-name">{{ doc.file_name }}</div>
                    </article>
                  </div>
                </div>
              </template>
            </el-a-bubble>
          </div>
        </el-a-bubble-list>

        <footer class="composer">
          <el-a-sender
            :model-value="composerValue"
            :loading="sending"
            placeholder="输入问题并发送"
            :enter-break="false"
            @update:modelValue="handleComposerChange"
            @send="handleSenderSend"
          />
          <div class="composer-tip">Enter 发送，Shift + Enter 换行</div>
        </footer>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ElABubble, ElABubbleList, ElAConversations, ElASender } from 'element-ai-vue'

import {
  appendChatMessage,
  createChatSession,
  getChatSessionDetail,
  listChatSessions,
  type ChatDocumentItem,
  type ChatMessage,
  type ChatSessionSummary
} from '../../api/chat'

type BubbleListInstance = {
  scrollToBottom?: () => void
}

const sessions = ref<ChatSessionSummary[]>([])
const activeSessionId = ref<number | null>(null)
const messages = ref<ChatMessage[]>([])
const composerValue = ref('')
const sending = ref(false)
const bubbleListRef = ref<BubbleListInstance | null>(null)

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

const getMessageDocuments = (message: ChatMessage): ChatDocumentItem[] => {
  if (!message.citations?.length) {
    return []
  }

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

const scrollMessagesToBottom = async () => {
  await nextTick()
  bubbleListRef.value?.scrollToBottom?.()
}

const handleComposerChange = (value: string) => {
  composerValue.value = value
}

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
  sessions.value = sessions.value.map(item => (item.id === detail.session.id ? detail.session : item))
  await scrollMessagesToBottom()
}

const handleCreateSession = async () => {
  const session = await createChatSession()
  sessions.value = [session, ...sessions.value]
  activeSessionId.value = session.id
  messages.value = []
  composerValue.value = ''
}

const handleSelectSession = async (sessionId: number) => {
  if (sessionId === activeSessionId.value) return
  await loadSessionDetail(sessionId)
}

const handleSenderSend = async (rawContent: string) => {
  const content = rawContent.trim()
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
    composerValue.value = ''
    messages.value = [...messages.value, response.user_message, response.assistant_message]
    sessions.value = [
      response.session,
      ...sessions.value.filter(item => item.id !== response.session.id)
    ]
    activeSessionId.value = response.session.id
    await scrollMessagesToBottom()
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
  grid-template-columns: 320px minmax(0, 1fr);
  background:
    radial-gradient(circle at top left, rgba(230, 187, 80, 0.16), transparent 24%),
    linear-gradient(180deg, #f6f0e4 0%, #ecf3ee 100%);
}

.session-shell {
  height: 100vh;
  padding: 20px;
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
}

.title {
  font-size: 22px;
  font-weight: 800;
}

.session-list {
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
  transition: transform 0.2s ease, background 0.2s ease;
}

.session-item:hover {
  transform: translateY(-1px);
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
  opacity: 0.72;
}

.chat-main {
  padding: 24px;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 18px;
}

.chat-main-header,
.conversation-panel {
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(22, 49, 42, 0.08);
  box-shadow: 0 18px 46px rgba(27, 47, 41, 0.08);
}

.chat-main-header {
  padding: 20px 24px;
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

.conversation-panel {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  padding: 20px;
}

.message-list {
  min-height: 0;
  overflow: auto;
  padding-right: 8px;
}

.bubble-shell + .bubble-shell {
  margin-top: 16px;
}

.empty-state {
  display: grid;
  place-items: center;
  text-align: center;
  color: #62746e;
}

.message-role {
  font-size: 12px;
  font-weight: 600;
  color: #6d7d77;
}

.message-documents {
  display: grid;
  gap: 10px;
  padding-top: 6px;
}

.message-documents-title {
  font-size: 12px;
  font-weight: 700;
  color: #62746e;
}

.message-documents-list {
  display: grid;
  gap: 8px;
}

.document-item {
  padding: 10px 12px;
  border-radius: 16px;
  background: #f7faf6;
  border: 1px solid #e5ece5;
}

.document-kb {
  font-size: 12px;
  color: #6a7c75;
}

.document-name {
  margin-top: 4px;
  font-weight: 700;
  color: #17302a;
  word-break: break-word;
}

.composer {
  display: grid;
  gap: 10px;
  padding-top: 16px;
  border-top: 1px solid #e9eee7;
}

.composer-tip {
  font-size: 12px;
  color: #6c7d76;
  text-align: right;
}

.bubble-shell.user {
  display: flex;
  justify-content: flex-end;
}

.bubble-shell.user :deep(.el-a-bubble__content-text) {
  background: linear-gradient(135deg, #183c36 0%, #2f6159 100%);
  color: #f7faf7;
}

.bubble-shell.user :deep(.el-a-bubble__header) {
  text-align: right;
}

.bubble-shell.assistant :deep(.el-a-bubble__content-text) {
  background: linear-gradient(180deg, #fffefb 0%, #f5f7f2 100%);
  border: 1px solid #e7ece4;
}

.session-shell:deep(.el-a-conversations__header) {
  padding-bottom: 18px;
}

.session-shell:deep(.el-a-conversations__scroll) {
  height: 100%;
  overflow: auto;
}

.message-list:deep(.el-a-bubble-list__content) {
  padding-right: 2px;
}

@media (max-width: 1100px) {
  .chat-page {
    grid-template-columns: 1fr;
  }

  .session-shell {
    height: auto;
  }
}
</style>
