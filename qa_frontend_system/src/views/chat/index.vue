<template>
  <section class="chat-page">
    <ChatSessionSidebar
      class="session-sidebar desktop-session-sidebar"
      :sessions="sessions"
      :active-session-id="activeSessionId"
      :creating="creatingSession"
      @create="handleCreateSession"
      @select="handleSelectSession"
      @rename="handleRenameSession"
      @delete="handleDeleteSession"
    />

    <el-a-conversation-popover v-model:collapse="mobileSessionCollapsed">
      <ChatSessionSidebar
        class="session-sidebar mobile-session-sidebar"
        :sessions="sessions"
        :active-session-id="activeSessionId"
        :creating="creatingSession"
        @create="handleMobileCreateSession"
        @select="handleMobileSelectSession"
        @rename="handleMobileRenameSession"
        @delete="handleMobileDeleteSession"
      />
    </el-a-conversation-popover>

    <div class="chat-main">
      <header class="chat-topbar desktop-only">
        <div class="topbar-brand">
          <img class="topbar-emblem" src="/hunnu-emblem.jpg" alt="湖南师范大学校徽" />
          <div class="topbar-text">
            <div class="topbar-title">湖小识 · 智能问答</div>
            <div class="topbar-subtitle">湖南师范大学 · 智慧知识服务平台</div>
          </div>
        </div>
        <router-link to="/" class="topbar-back">
          <el-icon><Back /></el-icon>
          <span>返回工作台</span>
        </router-link>
      </header>

      <header class="chat-toolbar mobile-only">
        <el-button text @click="mobileSessionCollapsed = false">会话列表</el-button>
        <el-button
          type="primary"
          size="small"
          :loading="creatingSession"
          :disabled="creatingSession || streaming"
          @click="handleCreateSession"
        >
          新建对话
        </el-button>
      </header>

      <ChatConversation
        ref="conversationRef"
        :messages="messages"
        :streaming="streaming"
        :streaming-content="streamingContent"
        :streaming-status="streamingStatus"
        :streaming-sql-result="streamingSqlResult"
      />

      <footer class="chat-footer">
        <div class="chat-controls">
          <el-radio-group v-model="chatMode" size="small" class="mode-switch" :disabled="streaming || !!uploadInfo">
            <el-radio-button value="auto">智能</el-radio-button>
            <el-radio-button value="docs">查文档</el-radio-button>
            <el-radio-button value="data">查数据</el-radio-button>
          </el-radio-group>

          <div class="upload-area">
            <input
              ref="fileInputRef"
              type="file"
              accept=".csv,.xlsx,.xls"
              hidden
              @change="handleFileSelected"
            />
            <el-tag
              v-if="uploadInfo"
              class="upload-chip"
              type="warning"
              effect="plain"
              closable
              :disable-transitions="true"
              @close="handleRemoveUpload"
            >
              <el-icon><Document /></el-icon>
              {{ uploadInfo.file_name }}（{{ uploadInfo.row_count }} 行）· 分析后自动删除
            </el-tag>
            <el-button
              v-else
              text
              type="primary"
              size="small"
              :loading="uploading"
              :disabled="streaming"
              @click="triggerFileSelect"
            >
              <el-icon><Upload /></el-icon>
              上传表格分析
            </el-button>
          </div>
        </div>

        <el-a-sender
          :model-value="composerValue"
          :loading="streaming"
          :placeholder="senderPlaceholder"
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
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Back, Document, Upload } from '@element-plus/icons-vue'

import {
  appendChatMessageStream,
  createChatSession,
  deleteChatSession,
  deleteChatUpload,
  getChatSessionDetail,
  listChatSessions,
  renameChatSession,
  uploadChatTable,
  type ChatCitation,
  type ChatMessage,
  type ChatMode,
  type ChatSessionSummary,
  type ChatUploadInfo,
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
const creatingSession = ref(false)
const mobileSessionCollapsed = ref(true)

// 问答模式与表格上传（上传后本次发送走 file 分析链路）
const chatMode = ref<ChatMode>('auto')
const uploadInfo = ref<ChatUploadInfo | null>(null)
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const senderPlaceholder = computed(() => {
  if (uploadInfo.value) return `针对「${uploadInfo.value.file_name}」提出分析问题，例如：统计各类别的数量`
  if (chatMode.value === 'docs') return '查文档模式：从知识库文档中检索并回答'
  if (chatMode.value === 'data') return '查数据模式：用自然语言查询业务数据库'
  return '输入问题后发送。Enter 发送，Shift + Enter 换行'
})

const triggerFileSelect = () => {
  fileInputRef.value?.click()
}

const handleFileSelected = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  uploading.value = true
  try {
    uploadInfo.value = await uploadChatTable(file)
    ElMessage.success('表格已上传，仅用于本次分析，分析完成后自动删除')
  } catch {
    // request 拦截器已提示错误
  } finally {
    uploading.value = false
  }
}

const handleRemoveUpload = async () => {
  const current = uploadInfo.value
  uploadInfo.value = null
  if (!current) return
  try {
    await deleteChatUpload(current.upload_id)
  } catch {
    // 文件可能已被后端分析后删除或过期清理，忽略
  }
}

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
  if (creatingSession.value) return
  if (streaming.value) {
    ElMessage.warning('请先等待当前回答完成')
    return
  }

  creatingSession.value = true
  try {
    const session = await createChatSession()
    sessions.value = [session, ...sessions.value.filter(item => item.id !== session.id)]
    activeSessionId.value = session.id
    messages.value = []
    composerValue.value = ''
    clearStreamingPayload()
    mobileSessionCollapsed.value = true
    ElMessage.success('已创建新对话')
  } catch {
    ElMessage.error('创建会话失败')
  } finally {
    creatingSession.value = false
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

const handleMobileCreateSession = async () => {
  await handleCreateSession()
}

const handleMobileSelectSession = async (sessionId: number) => {
  await handleSelectSession(sessionId)
  mobileSessionCollapsed.value = true
}

const handleMobileRenameSession = async (session: ChatSessionSummary) => {
  await handleRenameSession(session)
}

const handleMobileDeleteSession = async (sessionId: number) => {
  await handleDeleteSession(sessionId)
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

  // 上传了表格时本次发送固定走 file 分析链路，否则按用户选择的模式
  const effectiveMode: ChatMode = uploadInfo.value ? 'file' : chatMode.value
  const effectiveUploadId = uploadInfo.value?.upload_id ?? null

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
        if (effectiveMode === 'file') {
          // 后端在分析完成后已删除临时文件，前端同步清掉文件标记
          uploadInfo.value = null
          ElMessage.info('表格分析完成，临时文件已删除')
        }
        void scrollToBottom()
      }
      finalize()
    },
    onError: error => {
      resetStreamingState()
      ElMessage.error(error.message || '发送失败')
      messages.value = messages.value.filter(item => item.id !== tempUserMessage.id)
    },
  }, { mode: effectiveMode, uploadId: effectiveUploadId })
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
  background:
    radial-gradient(circle at 80% 8%, rgba(172, 52, 40, 0.06), transparent 32%),
    radial-gradient(circle at 6% 96%, rgba(201, 138, 58, 0.07), transparent 34%),
    linear-gradient(180deg, #f7f2eb 0%, #f2ece2 100%);
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
}

/* ---------- 顶部品牌栏 ---------- */
.chat-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 28px;
  border-bottom: 1px solid #e9dbc8;
  background:
    linear-gradient(180deg, rgba(255, 251, 246, 0.92) 0%, rgba(249, 241, 230, 0.92) 100%);
  backdrop-filter: blur(6px);
}

.topbar-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.topbar-emblem {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  object-fit: contain;
  flex: 0 0 auto;
  box-shadow: 0 6px 16px rgba(83, 38, 18, 0.18);
}

.topbar-text {
  min-width: 0;
}

.topbar-title {
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: #4e2f26;
  line-height: 1.2;
}

.topbar-subtitle {
  margin-top: 3px;
  font-size: 12px;
  color: #8c6d59;
}

.topbar-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid #e0cfbc;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  color: #7a5c47;
  background: #fffbf6;
  text-decoration: none;
  flex: 0 0 auto;
  transition: color 0.18s ease, border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}

.topbar-back:hover {
  color: #7a1c20;
  border-color: #e0bd95;
  background: #fff6ea;
  box-shadow: 0 6px 14px rgba(122, 28, 32, 0.1);
}

.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: rgba(255, 251, 246, 0.95);
  border-bottom: 1px solid #e9dbc8;
}

.desktop-only {
  display: flex;
}

.mobile-only {
  display: none;
}

/* ---------- 输入区 ---------- */
.chat-footer {
  background:
    linear-gradient(180deg, rgba(249, 241, 230, 0) 0%, rgba(249, 241, 230, 0.6) 22%, rgba(252, 246, 238, 0.95) 100%);
  padding: 12px 20px 20px;
}

.chat-sender {
  max-width: 880px;
  margin: 0 auto;
}

.chat-sender :deep(.el-a-sender-input) {
  background: rgba(255, 253, 249, 0.96);
  border-radius: 16px;
  border: 1px solid #e3d2bd;
  box-shadow: 0 6px 18px rgba(83, 38, 18, 0.06);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.chat-sender :deep(.el-a-sender-input:focus-within) {
  background: #fffdf9;
  border-color: #c98a3a;
  box-shadow: 0 0 0 3px rgba(201, 138, 58, 0.16), 0 8px 20px rgba(83, 38, 18, 0.08);
}

.chat-sender :deep(.el-a-sender-actions .el-button--primary) {
  --el-button-bg-color: #9f2f2f;
  --el-button-border-color: #9f2f2f;
  --el-button-hover-bg-color: #872626;
  --el-button-hover-border-color: #872626;
  --el-button-active-bg-color: #7a1c20;
}

.char-count {
  font-size: 12px;
  color: #a3917f;
  margin-right: 8px;
}

@media (max-width: 768px) {
  .chat-page {
    display: block;
  }

  .desktop-session-sidebar,
  .desktop-only {
    display: none;
  }

  .mobile-only {
    display: flex;
  }
}
</style>
