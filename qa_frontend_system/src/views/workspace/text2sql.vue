<template>
  <div class="text2sql-page">
    <section class="panel-card query-panel">
      <div class="panel-header">
        <div>
          <div class="panel-title">Text2SQL 智能查询</div>
          <div class="panel-subtitle">支持多轮对话：可在上一问基础上追问，系统会结合上下文理解。</div>
        </div>
      </div>

      <el-alert
        v-if="!canRunQuery"
        title="当前账号没有 text2sql.query.run 权限，无法执行查询。"
        type="warning"
        :closable="false"
        show-icon
        class="block-alert"
      />

      <el-form label-position="top">
        <el-form-item label="问题">
          <el-input
            v-model="question"
            type="textarea"
            :rows="5"
            resize="none"
            placeholder="示例：统计近30天每个学院新增知识库数量，并按数量降序排列。可继续追问：再按月份分组。"
          />
        </el-form-item>

        <div class="form-actions">
          <el-button :disabled="loading || debugLoading" @click="handleClear">清空输入</el-button>
          <el-button
            type="primary"
            :loading="loading"
            :disabled="!canRunQuery || debugLoading"
            @click="handleRun"
          >
            执行查询
          </el-button>
          <el-button
            :loading="debugLoading"
            :disabled="!canRunQuery || loading"
            @click="handleDebug"
          >
            仅生成 SQL
          </el-button>
        </div>
      </el-form>

      <div
        v-if="debugLoading || debugStreamGeneratedSql"
        class="result-block stream-progress"
      >
        <div class="block-title">仅生成 SQL · 执行过程</div>
        <div class="progress-line">
          <span class="progress-label">阶段：</span>
          <span>{{ debugStreamStatus || '--' }}</span>
        </div>
        <div class="progress-line">
          <span class="progress-label">已选表：</span>
          <span>{{ debugStreamSelectedTables.join(', ') || '--' }}</span>
        </div>
        <div class="progress-line">
          <span class="progress-label">生成 SQL：</span>
        </div>
        <pre class="block-pre progress-sql">{{ debugStreamGeneratedSql || '--' }}</pre>
      </div>

      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        :closable="false"
        show-icon
        class="block-alert"
      />
    </section>

    <section class="panel-card result-panel">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="对话" name="result">
          <div class="conversation-toolbar">
            <span class="conv-hint">
              {{ conversation.length ? `共 ${conversation.length} 轮对话` : '开始你的多轮提问' }}
            </span>
            <el-button text :disabled="!conversation.length || loading" @click="handleNewConversation">
              新对话
            </el-button>
          </div>

          <div ref="threadRef" class="chat-thread">
            <template v-if="conversation.length">
              <div v-for="turn in conversation" :key="turn.id" class="chat-turn">
                <div class="msg user-msg">
                  <div class="bubble user-bubble">{{ turn.question }}</div>
                </div>

                <div class="msg ai-msg">
                  <div class="bubble ai-bubble">
                    <template v-if="turn.status === 'streaming'">
                      <div class="stream-line">{{ turn.progressStatus || '正在思考…' }}</div>
                      <div v-if="turn.selectedTables.length" class="stream-line muted">
                        候选表：{{ turn.selectedTables.join(', ') }}
                      </div>
                      <pre v-if="turn.generatedSql" class="block-pre">{{ turn.generatedSql }}</pre>
                      <div v-if="turn.answer" class="answer-text">{{ turn.answer }}</div>
                    </template>

                    <template v-else-if="turn.status === 'clarify'">
                      <el-alert
                        :title="turn.clarification"
                        type="warning"
                        :closable="false"
                        show-icon
                      />
                      <div class="clarify-tip">请在左侧补充更具体的条件后继续提问。</div>
                    </template>

                    <template v-else-if="turn.status === 'error'">
                      <el-alert :title="turn.errorMessage" type="error" :closable="false" show-icon />
                    </template>

                    <template v-else>
                      <div class="result-tags">
                        <el-tag effect="plain">行数 {{ turn.rowCount }}</el-tag>
                        <el-tag effect="plain" type="success">修复 {{ turn.repaired ? '是' : '否' }}</el-tag>
                      </div>

                      <div class="mini-title">SQL</div>
                      <pre class="block-pre">{{ turn.sql || '--' }}</pre>

                      <div class="mini-title">答案摘要</div>
                      <div class="answer-text">{{ turn.answer || '--' }}</div>

                      <el-table
                        v-if="turn.rows.length"
                        :data="turn.rows"
                        stripe
                        border
                        class="result-table"
                        max-height="320"
                      >
                        <el-table-column
                          v-for="col in columnsOf(turn)"
                          :key="col"
                          :prop="col"
                          :label="col"
                          min-width="140"
                          show-overflow-tooltip
                        />
                      </el-table>

                      <div v-if="turn.logId" class="feedback-row">
                        <span class="feedback-label">满意吗？（评 5 星“非常满意”后将作为示例帮助系统改进）</span>
                        <el-rate
                          v-model="turn.feedbackScore"
                          :disabled="turn.feedbackSubmitting || turn.feedbackSubmitted"
                          @change="(score: number) => handleFeedback(turn, score)"
                        />
                        <span v-if="turn.feedbackSubmitted" class="feedback-done">已记录，感谢反馈！</span>
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </template>
            <el-empty v-else description="尚未开始对话。输入问题并点击“执行查询”。" />
          </div>
        </el-tab-pane>

        <el-tab-pane label="调试信息" name="debug">
          <template v-if="debugResult">
            <div class="result-block">
              <div class="block-title">生成 SQL</div>
              <pre class="block-pre">{{ debugResult.sql || '--' }}</pre>
            </div>
            <div class="debug-grid">
              <div>
                <div class="kv-label">校验结果</div>
                <div>{{ debugResult.validation_passed ? '通过' : '失败' }}</div>
              </div>
              <div>
                <div class="kv-label">路由模式</div>
                <div>{{ debugResult.route_mode || '--' }}</div>
              </div>
              <div>
                <div class="kv-label">候选表</div>
                <div>{{ debugResult.route_tables.join(', ') || '--' }}</div>
              </div>
              <div>
                <div class="kv-label">关系保护</div>
                <div>{{ debugResult.relation_guard_used ? '已启用' : '未启用' }}</div>
              </div>
            </div>
            <el-alert
              v-if="debugResult.validation_message"
              :title="debugResult.validation_message"
              :type="debugResult.validation_passed ? 'success' : 'warning'"
              :closable="false"
              show-icon
              class="block-alert"
            />
          </template>
          <el-empty v-else description="尚未执行调试生成。" />
        </el-tab-pane>

        <el-tab-pane label="查询日志" name="logs">
          <template v-if="canViewLogs">
            <el-table :data="logs" border stripe max-height="420">
              <el-table-column prop="created_at" label="时间" width="170" />
              <el-table-column prop="status" label="状态" width="90" />
              <el-table-column prop="question" label="问题" min-width="260" show-overflow-tooltip />
              <el-table-column prop="feedback_score" label="评分" width="80" />
              <el-table-column prop="row_count" label="行数" width="90" />
              <el-table-column prop="duration_ms" label="耗时(ms)" width="100" />
            </el-table>
            <el-empty v-if="!logs.length" description="暂无日志。" />
          </template>
          <el-empty v-else description="当前账号没有 text2sql.log.view 权限。" />
        </el-tab-pane>
      </el-tabs>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  debugText2SQLQueryStream,
  listText2SQLLogs,
  runText2SQLQueryStream,
  submitText2SQLFeedback,
  type Text2SQLDebugGenerateResponse,
  type Text2SQLFieldInferenceItem,
  type Text2SQLQueryLogItem,
  type Text2SQLStreamGeneratedSqlData,
  type Text2SQLStreamSelectedTablesData,
  type Text2SQLStreamSqlResultData,
  type Text2SQLStreamStatusData,
  type Text2SQLTurn,
} from '../../api/text2sql'

interface ConversationTurn {
  id: string
  question: string
  status: 'streaming' | 'done' | 'clarify' | 'error'
  progressStatus: string
  selectedTables: string[]
  generatedSql: string
  sql: string
  answer: string
  columns: string[]
  rows: Record<string, unknown>[]
  rowCount: number
  repaired: boolean
  fieldInference: Text2SQLFieldInferenceItem[]
  clarification: string
  logId: number | null
  errorMessage: string
  feedbackScore: number
  feedbackSubmitting: boolean
  feedbackSubmitted: boolean
}

const activeTab = ref<'result' | 'debug' | 'logs'>('result')
const question = ref('')
const loading = ref(false)
const debugLoading = ref(false)
const errorMessage = ref('')

const streamStopper = ref<(() => void) | null>(null)

// 「仅生成 SQL」单次流式状态（独立于对话）
const debugStreamStatus = ref('')
const debugStreamSelectedTables = ref<string[]>([])
const debugStreamGeneratedSql = ref('')
const debugResult = ref<Text2SQLDebugGenerateResponse | null>(null)

const conversation = ref<ConversationTurn[]>([])
const threadRef = ref<HTMLElement | null>(null)

const logs = ref<Text2SQLQueryLogItem[]>([])

const canRunQuery = computed(() => true)
const canViewLogs = computed(() => true)

let turnSeq = 0
const newTurnId = () => `turn-${Date.now()}-${turnSeq++}`

const columnsOf = (turn: ConversationTurn): string[] => {
  if (turn.columns.length) return turn.columns
  const firstRow = turn.rows[0]
  return firstRow ? Object.keys(firstRow) : []
}

// 仅把成功回答的轮次（含 SQL）回传为上下文，clarify/error/streaming 轮次不进历史。
const buildHistory = (): Text2SQLTurn[] =>
  conversation.value
    .filter((turn) => turn.status === 'done' && turn.sql)
    .map((turn) => ({ question: turn.question, sql: turn.sql, answer: turn.answer }))

const scrollToBottom = async () => {
  await nextTick()
  const el = threadRef.value
  if (el) el.scrollTop = el.scrollHeight
}

const loadLogs = async () => {
  if (!canViewLogs.value) return
  try {
    logs.value = await listText2SQLLogs(20)
  } catch {
    logs.value = []
  }
}

const handleClear = () => {
  question.value = ''
}

const handleNewConversation = () => {
  conversation.value = []
  errorMessage.value = ''
}

const stopActiveStream = () => {
  if (!streamStopper.value) return
  streamStopper.value()
  streamStopper.value = null
}

const handleRun = async () => {
  const q = question.value.trim()
  if (!q) {
    ElMessage.warning('请输入问题')
    return
  }
  if (loading.value || debugLoading.value) return

  const history = buildHistory()
  conversation.value.push({
    id: newTurnId(),
    question: q,
    status: 'streaming',
    progressStatus: '',
    selectedTables: [],
    generatedSql: '',
    sql: '',
    answer: '',
    columns: [],
    rows: [],
    rowCount: 0,
    repaired: false,
    fieldInference: [],
    clarification: '',
    logId: null,
    errorMessage: '',
    feedbackScore: 0,
    feedbackSubmitting: false,
    feedbackSubmitted: false,
  })
  const active = conversation.value[conversation.value.length - 1]

  question.value = ''
  errorMessage.value = ''
  activeTab.value = 'result'
  loading.value = true
  stopActiveStream()
  await scrollToBottom()

  try {
    await new Promise<void>((resolve, reject) => {
      let finished = false
      streamStopper.value = runText2SQLQueryStream(
        { question: q, history },
        {
          onStatus: (data: Text2SQLStreamStatusData) => {
            active.progressStatus = data?.message || ''
            void scrollToBottom()
          },
          onSelectedTables: (data: Text2SQLStreamSelectedTablesData) => {
            active.selectedTables = Array.isArray(data?.selected_tables) ? data.selected_tables : []
          },
          onGeneratedSql: (data: Text2SQLStreamGeneratedSqlData) => {
            active.generatedSql = data?.sql || data?.final_sql || ''
            if (!active.sql) active.sql = active.generatedSql
          },
          onSqlResult: (data: Text2SQLStreamSqlResultData) => {
            active.sql = data?.sql || active.generatedSql || ''
            active.columns = Array.isArray(data?.columns) ? data.columns : []
            active.rows = Array.isArray(data?.rows) ? data.rows : []
            active.rowCount = Number(data?.row_count ?? active.rows.length)
            active.repaired = Boolean(data?.repaired)
            active.fieldInference = Array.isArray(data?.field_inference) ? data.field_inference : []
            void scrollToBottom()
          },
          onAnswerDelta: (content: string) => {
            if (!content) return
            active.answer += content
            void scrollToBottom()
          },
          onDone: (payload) => {
            if (finished) return
            finished = true
            active.sql = payload.sql || active.sql
            active.answer = payload.answer || active.answer
            active.columns = Array.isArray(payload.columns) ? payload.columns : active.columns
            active.rows = Array.isArray(payload.rows) ? payload.rows : active.rows
            active.rowCount = Number(payload.row_count ?? active.rows.length)
            active.repaired = Boolean(payload.repaired)
            active.fieldInference = Array.isArray(payload.field_inference) ? payload.field_inference : []
            active.clarification = String(payload.clarification || '')
            active.logId = payload.log_id ?? null
            active.status = active.clarification ? 'clarify' : 'done'
            streamStopper.value = null
            resolve()
          },
          onError: (error) => {
            if (finished) return
            finished = true
            active.status = 'error'
            active.errorMessage = error?.message || 'Text2SQL 查询失败'
            streamStopper.value = null
            reject(new Error(active.errorMessage))
          },
        },
      )
    })
    await loadLogs()
  } catch {
    // 错误已记录在该轮次气泡上，无需额外处理
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

const handleFeedback = async (turn: ConversationTurn, score: number) => {
  if (!turn.logId || !score) return
  turn.feedbackSubmitting = true
  try {
    await submitText2SQLFeedback({ log_id: turn.logId, score })
    turn.feedbackScore = score
    turn.feedbackSubmitted = true
    ElMessage.success(score >= 5 ? '感谢！该问答将用于改进示例库' : '反馈已记录')
  } catch (error: any) {
    turn.feedbackSubmitted = false
    ElMessage.error(error?.message || '反馈提交失败')
  } finally {
    turn.feedbackSubmitting = false
  }
}

const handleDebug = async () => {
  const q = question.value.trim()
  if (!q) {
    ElMessage.warning('请输入问题')
    return
  }

  debugLoading.value = true
  errorMessage.value = ''
  debugStreamStatus.value = ''
  debugStreamSelectedTables.value = []
  debugStreamGeneratedSql.value = ''
  stopActiveStream()

  try {
    await new Promise<void>((resolve, reject) => {
      let finished = false
      streamStopper.value = debugText2SQLQueryStream(
        { question: q, history: [] },
        {
          onStatus: (data) => {
            debugStreamStatus.value = data?.message || ''
          },
          onSelectedTables: (data) => {
            debugStreamSelectedTables.value = Array.isArray(data?.selected_tables)
              ? data.selected_tables
              : []
          },
          onGeneratedSql: (data) => {
            debugStreamGeneratedSql.value = data?.sql || data?.final_sql || ''
          },
          onDone: (payload) => {
            if (finished) return
            finished = true
            debugResult.value = payload
            activeTab.value = 'debug'
            streamStopper.value = null
            resolve()
          },
          onError: (error) => {
            if (finished) return
            finished = true
            streamStopper.value = null
            reject(new Error(error?.message || '调试 SQL 生成失败'))
          },
        },
      )
    })
  } catch (error: any) {
    errorMessage.value = error?.message || '调试 SQL 生成失败'
  } finally {
    debugLoading.value = false
  }
}

onMounted(async () => {
  await loadLogs()
})

onBeforeUnmount(() => {
  stopActiveStream()
})
</script>

<style scoped>
.text2sql-page {
  display: grid;
  grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.1fr);
  gap: 18px;
  min-height: calc(100vh - 220px);
}

.panel-card {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid #ead8c6;
  background: linear-gradient(180deg, #fffdfb 0%, #f9f2e8 100%);
}

.query-panel,
.result-panel {
  min-width: 0;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.panel-title {
  font-size: 22px;
  font-weight: 700;
  color: #4a2a24;
}

.panel-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: #81695b;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
}

.block-alert {
  margin-top: 12px;
}

.result-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.result-block {
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #eadfce;
  background: #fff;
}

.stream-progress {
  margin-top: 12px;
}

.block-title {
  margin-bottom: 6px;
  font-size: 12px;
  color: #8a6e5c;
}

.mini-title {
  margin: 8px 0 4px;
  font-size: 12px;
  color: #8a6e5c;
}

.block-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 13px;
  color: #3c2a22;
}

.progress-line {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  color: #4a2a24;
  line-height: 1.6;
}

.progress-label {
  min-width: 72px;
  color: #8a6e5c;
}

.progress-sql {
  margin-top: 6px;
}

.answer-text {
  white-space: pre-wrap;
  line-height: 1.7;
  color: #2f241d;
  word-break: break-word;
}

.result-table {
  margin-top: 8px;
}

.conversation-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.conv-hint {
  font-size: 12px;
  color: #8a6e5c;
}

.chat-thread {
  max-height: calc(100vh - 320px);
  overflow-y: auto;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.chat-turn {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.msg {
  display: flex;
}

.user-msg {
  justify-content: flex-end;
}

.ai-msg {
  justify-content: flex-start;
}

.bubble {
  max-width: 92%;
  padding: 12px 14px;
  border-radius: 14px;
  font-size: 14px;
}

.user-bubble {
  background: #4a2a24;
  color: #fff8f1;
  border-bottom-right-radius: 4px;
  white-space: pre-wrap;
  word-break: break-word;
}

.ai-bubble {
  width: 100%;
  background: #fff;
  border: 1px solid #eadfce;
  border-bottom-left-radius: 4px;
  color: #2f241d;
}

.stream-line {
  margin-bottom: 6px;
  color: #4a2a24;
  line-height: 1.6;
}

.stream-line.muted {
  color: #8a6e5c;
  font-size: 13px;
}

.clarify-tip {
  margin-top: 8px;
  font-size: 12px;
  color: #8a6e5c;
}

.feedback-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #eadfce;
}

.feedback-label {
  font-size: 12px;
  color: #8a6e5c;
}

.feedback-done {
  font-size: 12px;
  color: #5a8a4a;
}

.debug-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid #eadfce;
}

.kv-label {
  margin-bottom: 4px;
  font-size: 12px;
  color: #8a6e5c;
}

@media (max-width: 1200px) {
  .text2sql-page {
    grid-template-columns: 1fr;
  }
}
</style>
