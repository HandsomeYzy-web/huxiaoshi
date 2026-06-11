import request from '../utils/request'

const TEXT2SQL_LONG_RUNNING_TIMEOUT_MS = 0

export type Text2SQLDbType = 'mysql' | 'sqlserver'

export interface Text2SQLConnectionPayload {
  db_type: Text2SQLDbType
  host: string
  port: number
  username: string
  password?: string | null
  database: string
  charset: string
}

export interface Text2SQLConnectionResponse {
  configured: boolean
  db_type: Text2SQLDbType | null
  host: string
  port: number
  username: string
  database: string
  charset: string
  has_password: boolean
}

export interface Text2SQLConnectionTestResponse {
  ok: boolean
  message: string
}

export interface Text2SQLColumnInfo {
  name: string
  type: string
  comment: string
}

export interface Text2SQLTableInfo {
  table_name: string
  table_comment: string
  columns: Text2SQLColumnInfo[]
}

export interface Text2SQLSchemaResponse {
  tables: Text2SQLTableInfo[]
}

export interface Text2SQLTableOption {
  table_name: string
  table_comment: string
}

export interface Text2SQLTableOptionsResponse {
  tables: Text2SQLTableOption[]
}

export interface Text2SQLConfigResponse {
  selected_tables: string[]
  prompt_hint: string
}

export interface UpdateText2SQLConfigRequest {
  selected_tables: string[]
  prompt_hint: string
}

export interface Text2SQLTableFieldItem {
  name: string
  type: string
  comment: string
  query_enabled: boolean
}

export interface Text2SQLTableFieldsResponse {
  table_name: string
  table_comment: string
  fields: Text2SQLTableFieldItem[]
}

export interface UpdateText2SQLTableFieldItem {
  name: string
  query_enabled: boolean
}

export interface UpdateText2SQLTableFieldsRequest {
  fields: UpdateText2SQLTableFieldItem[]
}

export interface Text2SQLRelationItem {
  id: number
  source_table: string
  source_columns: string[]
  target_table: string
  target_columns: string[]
  relation_type: string
  description: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Text2SQLRelationListResponse {
  items: Text2SQLRelationItem[]
  total: number
  page: number
  page_size: number
}

export interface Text2SQLRelationTableColumnsResponse {
  table_name: string
  table_comment: string
  columns: Text2SQLColumnInfo[]
}

export interface CreateText2SQLRelationRequest {
  source_table: string
  source_columns: string[]
  target_table: string
  target_columns: string[]
  relation_type: string
  description: string
  is_active: boolean
}

export interface UpdateText2SQLRelationRequest extends CreateText2SQLRelationRequest {}

export interface BatchImportText2SQLRelationsRequest {
  relations: CreateText2SQLRelationRequest[]
  overwrite_existing?: boolean
}

export interface Text2SQLRelationBatchImportResponse {
  total: number
  created: number
  updated: number
  skipped: number
  failed: number
  errors: string[]
}

export interface Text2SQLRelationListParams {
  page?: number
  page_size?: number
  keyword?: string
  table_name?: string
}

export interface Text2SQLTurn {
  question: string
  sql: string
  answer: string
}

export interface Text2SQLQueryRequest {
  question: string
  history?: Text2SQLTurn[]
}

export interface Text2SQLFieldInferenceItem {
  column: string
  inferred_meaning: string
  confidence: number
  reason: string
  table_name: string
  table_comment: string
  column_name: string
  column_comment: string
}

export interface Text2SQLQueryResponse {
  sql: string
  columns: string[]
  rows: Record<string, unknown>[]
  answer: string
  row_count: number
  repaired: boolean
  field_inference: Text2SQLFieldInferenceItem[]
  log_id?: number | null
  clarification?: string
}

export interface Text2SQLFeedbackRequest {
  log_id: number
  score: number
}

export interface Text2SQLDebugGenerateResponse {
  sql: string
  validation_passed: boolean
  validation_message: string
  route_mode: string
  route_tables: string[]
  route_pool_tables: string[]
  route_scores: Record<string, number>
  relation_hints: string[]
  relation_guard_used: boolean
}

export interface Text2SQLQueryLogItem {
  id: number
  question: string
  generated_sql: string | null
  final_sql: string | null
  status: string
  error_message: string | null
  relation_guard_used: boolean
  row_count: number | null
  duration_ms: number | null
  repaired: boolean
  feedback_score?: number | null
  created_at: string
}

export interface Text2SQLStreamStatusData {
  step: string
  message: string
}

export interface Text2SQLStreamSelectedTablesData {
  selected_tables: string[]
  route_mode?: string
}

export interface Text2SQLStreamGeneratedSqlData {
  sql: string
  final_sql: string
}

export interface Text2SQLStreamSqlResultData {
  sql: string
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  repaired: boolean
  field_inference: Text2SQLFieldInferenceItem[]
}

export interface Text2SQLStreamHandlers<TDone> {
  onStatus?: (data: Text2SQLStreamStatusData) => void
  onSelectedTables?: (data: Text2SQLStreamSelectedTablesData) => void
  onGeneratedSql?: (data: Text2SQLStreamGeneratedSqlData) => void
  onSqlResult?: (data: Text2SQLStreamSqlResultData) => void
  onAnswerDelta?: (content: string) => void
  onDone?: (data: TDone) => void
  onError?: (error: { message: string }) => void
}

export const getText2SQLConnection = () =>
  request.get<any, Text2SQLConnectionResponse>('/text2sql/connection')

export const saveText2SQLConnection = (data: Text2SQLConnectionPayload) =>
  request.put<any, Text2SQLConnectionResponse>('/text2sql/connection', data)

export const testText2SQLConnection = (data: Text2SQLConnectionPayload) =>
  request.post<any, Text2SQLConnectionTestResponse>('/text2sql/connection/test', data)

export const getText2SQLTableSchema = () =>
  request.get<any, Text2SQLSchemaResponse>('/text2sql/tables/schema')

export const getText2SQLTableOptions = () =>
  request.get<any, Text2SQLTableOptionsResponse>('/text2sql/tables/options')

export const getText2SQLTableConfig = () =>
  request.get<any, Text2SQLConfigResponse>('/text2sql/tables/config')

export const updateText2SQLTableConfig = (data: UpdateText2SQLConfigRequest) =>
  request.put<any, Text2SQLConfigResponse>('/text2sql/tables/config', data)

export const getText2SQLTableFields = (tableName: string) =>
  request.get<any, Text2SQLTableFieldsResponse>(`/text2sql/tables/${encodeURIComponent(tableName)}/fields`)

export const updateText2SQLTableFields = (tableName: string, data: UpdateText2SQLTableFieldsRequest) =>
  request.put<any, Text2SQLTableFieldsResponse>(`/text2sql/tables/${encodeURIComponent(tableName)}/fields`, data)

export const listText2SQLRelations = (params: Text2SQLRelationListParams) =>
  request.get<any, Text2SQLRelationListResponse>('/text2sql/relations', { params })

export const createText2SQLRelation = (data: CreateText2SQLRelationRequest) =>
  request.post<any, Text2SQLRelationItem>('/text2sql/relations', data)

export const updateText2SQLRelation = (relationId: number, data: UpdateText2SQLRelationRequest) =>
  request.put<any, Text2SQLRelationItem>(`/text2sql/relations/${relationId}`, data)

export const deleteText2SQLRelation = (relationId: number) =>
  request.delete<any, boolean>(`/text2sql/relations/${relationId}`)

export const getText2SQLRelationTableColumns = (tableName: string) =>
  request.get<any, Text2SQLRelationTableColumnsResponse>(
    `/text2sql/relations/table/${encodeURIComponent(tableName)}/columns`,
  )

export const batchImportText2SQLRelations = (data: BatchImportText2SQLRelationsRequest) =>
  request.post<any, Text2SQLRelationBatchImportResponse>('/text2sql/relations/batch-import', data)

export const runText2SQLQuery = (data: Text2SQLQueryRequest) =>
  request.post<any, Text2SQLQueryResponse>('/text2sql/query', data, {
    timeout: TEXT2SQL_LONG_RUNNING_TIMEOUT_MS,
  })

export const submitText2SQLFeedback = (data: Text2SQLFeedbackRequest) =>
  request.post<any, boolean>('/text2sql/query/feedback', data)

export const debugText2SQLQuery = (data: Text2SQLQueryRequest) =>
  request.post<any, Text2SQLDebugGenerateResponse>('/text2sql/debug/generate', data, {
    timeout: TEXT2SQL_LONG_RUNNING_TIMEOUT_MS,
  })

const dispatchText2SQLStreamEvent = <TDone>(
  event: string | null,
  payload: unknown,
  handlers: Text2SQLStreamHandlers<TDone>,
) => {
  switch (event) {
    case 'status':
      handlers.onStatus?.(payload as Text2SQLStreamStatusData)
      break
    case 'selected_tables':
      handlers.onSelectedTables?.(payload as Text2SQLStreamSelectedTablesData)
      break
    case 'generated_sql':
      handlers.onGeneratedSql?.(payload as Text2SQLStreamGeneratedSqlData)
      break
    case 'sql_result':
      handlers.onSqlResult?.(payload as Text2SQLStreamSqlResultData)
      break
    case 'answer_delta':
      handlers.onAnswerDelta?.(String((payload as { content?: string })?.content || ''))
      break
    case 'done':
      handlers.onDone?.(payload as TDone)
      break
    case 'error':
      handlers.onError?.(payload as { message: string })
      break
  }
}

const parseText2SQLSseFrame = <TDone>(frame: string, handlers: Text2SQLStreamHandlers<TDone>) => {
  const lines = frame.split(/\r?\n/)
  let event: string | null = null
  const dataLines: string[] = []

  for (const rawLine of lines) {
    if (!rawLine || rawLine.startsWith(':')) continue
    if (rawLine.startsWith('event:')) {
      event = rawLine.slice(6).trim()
      continue
    }
    if (rawLine.startsWith('data:')) {
      dataLines.push(rawLine.slice(5).trimStart())
    }
  }

  if (!event || !dataLines.length) return

  const dataText = dataLines.join('\n')
  try {
    dispatchText2SQLStreamEvent(event, JSON.parse(dataText), handlers)
  } catch (error) {
    console.error('解析 Text2SQL SSE 数据失败:', error, dataText)
  }
}

const runText2SQLStream = <TDone>(
  endpoint: string,
  payload: Text2SQLQueryRequest,
  handlers: Text2SQLStreamHandlers<TDone>,
): (() => void) => {
  const abortController = new AbortController()

  const fetchStream = async () => {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ question: payload.question, history: payload.history ?? [] }),
        signal: abortController.signal,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: '请求失败' }))
        handlers.onError?.({ message: errorData.detail || errorData.message || '请求失败' })
        return
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder('utf-8')

      if (!reader) {
        handlers.onError?.({ message: '无法读取流式响应' })
        return
      }

      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split(/\r?\n\r?\n/)
        buffer = frames.pop() || ''
        for (const frame of frames) {
          parseText2SQLSseFrame(frame, handlers)
        }
      }

      if (buffer.trim()) {
        parseText2SQLSseFrame(buffer, handlers)
      }
    } catch (error: any) {
      if (error?.name === 'AbortError') return
      handlers.onError?.({ message: error?.message || '网络请求失败' })
    }
  }

  void fetchStream()
  return () => abortController.abort()
}

export const runText2SQLQueryStream = (
  payload: Text2SQLQueryRequest,
  handlers: Text2SQLStreamHandlers<Text2SQLQueryResponse>,
): (() => void) => runText2SQLStream('/api/v1/text2sql/query/stream', payload, handlers)

export const debugText2SQLQueryStream = (
  payload: Text2SQLQueryRequest,
  handlers: Text2SQLStreamHandlers<Text2SQLDebugGenerateResponse>,
): (() => void) => runText2SQLStream('/api/v1/text2sql/debug/generate/stream', payload, handlers)

export const listText2SQLLogs = (limit = 20) =>
  request.get<any, Text2SQLQueryLogItem[]>('/text2sql/logs', { params: { limit } })
