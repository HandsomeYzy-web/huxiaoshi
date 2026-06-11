import request from '../utils/request'

/** 问答模式：auto=智能判断，docs=查文档（RAG），data=查数据（text2SQL），file=上传表格分析 */
export type ChatMode = 'auto' | 'docs' | 'data' | 'file'

export interface ChatUploadInfo {
  upload_id: string
  file_name: string
  row_count: number
  columns: string[]
  expires_in_seconds: number
}

export interface ChatCitation {
  chunk_id: number
  kb_id: number
  kb_name: string
  file_id: number
  file_name: string
  score: number
  content: string
}

export interface ChatMessage {
  id: number
  session_id: number
  role: 'user' | 'assistant'
  content: string
  model_used?: string | null
  retrieved_count?: number
  citations?: ChatCitation[]
  sql_result_json?: string | null
  created_at: string
}

export interface ChatDocumentItem {
  kb_id: number
  kb_name: string
  file_id: number
  file_name: string
}

export interface ChatSessionSummary {
  id: number
  title: string
  updated_at: string
  created_at: string
}

export interface ChatSessionDetail {
  session: ChatSessionSummary
  messages: ChatMessage[]
  involved_documents: ChatDocumentItem[]
}

export interface ChatMessageCreateResponse {
  session: ChatSessionSummary
  user_message: ChatMessage
  assistant_message: ChatMessage
  involved_documents: ChatDocumentItem[]
}

export interface StreamEvent {
  event: 'user_message' | 'session_info' | 'status' | 'citations' | 'sql_result' | 'delta' | 'done' | 'error'
  data: any
}

export interface StatusData {
  step: string
  message: string
}

export interface SqlResultData {
  columns: string[]
  rows: Record<string, any>[]
}

export interface StreamHandlers {
  onUserMessage?: (message: { id: number; content: string; created_at: string }) => void
  onSessionInfo?: (session: { id: number; title: string; updated_at: string }) => void
  onStatus?: (data: StatusData) => void
  onCitations?: (citations: ChatCitation[]) => void
  onSqlResult?: (data: SqlResultData) => void
  onDelta?: (content: string) => void
  onDone?: (message: { id: number; content: string; model_used: string | null; retrieved_count: number; created_at: string }) => void
  onError?: (error: { message: string }) => void
}

const dispatchStreamEvent = (event: string | null, payload: any, handlers: StreamHandlers) => {
  switch (event) {
    case 'user_message':
      handlers.onUserMessage?.(payload)
      break
    case 'session_info':
      handlers.onSessionInfo?.(payload)
      break
    case 'status':
      handlers.onStatus?.(payload)
      break
    case 'citations':
      handlers.onCitations?.(payload)
      break
    case 'sql_result':
      handlers.onSqlResult?.(payload)
      break
    case 'delta':
      handlers.onDelta?.(payload.content)
      break
    case 'done':
      handlers.onDone?.(payload)
      break
    case 'error':
      handlers.onError?.(payload)
      break
  }
}

const parseSseFrame = (frame: string, handlers: StreamHandlers) => {
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
    dispatchStreamEvent(event, JSON.parse(dataText), handlers)
  } catch (error) {
    console.error('解析 SSE 数据失败:', error, dataText)
  }
}

export const listChatSessions = () =>
  request.get<any, ChatSessionSummary[]>('/chat/sessions')

export const createChatSession = (title = '新对话') =>
  request.post<any, ChatSessionSummary>('/chat/sessions', { title })

export const getChatSessionDetail = (sessionId: number) =>
  request.get<any, ChatSessionDetail>(`/chat/sessions/${sessionId}`)

export interface ChatSendOptions {
  mode?: ChatMode
  uploadId?: string | null
}

export const appendChatMessage = (sessionId: number, question: string, options: ChatSendOptions = {}) =>
  request.post<any, ChatMessageCreateResponse>(`/chat/sessions/${sessionId}/messages`, {
    question,
    mode: options.mode ?? 'auto',
    upload_id: options.uploadId ?? null,
  })

export const appendChatMessageStream = (
  sessionId: number,
  question: string,
  handlers: StreamHandlers,
  options: ChatSendOptions = {},
): (() => void) => {
  const abortController = new AbortController()

  const fetchStream = async () => {
    try {
      const response = await fetch(`/api/v1/chat/sessions/${sessionId}/messages/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({
          question,
          mode: options.mode ?? 'auto',
          upload_id: options.uploadId ?? null,
        }),
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
          parseSseFrame(frame, handlers)
        }
      }

      if (buffer.trim()) {
        parseSseFrame(buffer, handlers)
      }
    } catch (error: any) {
      if (error.name === 'AbortError') return
      handlers.onError?.({ message: error.message || '网络请求失败' })
    }
  }

  void fetchStream()

  return () => abortController.abort()
}

export const deleteChatSession = (sessionId: number) =>
  request.delete<any, null>(`/chat/sessions/${sessionId}`)

export const renameChatSession = (sessionId: number, title: string) =>
  request.patch<any, ChatSessionSummary>(`/chat/sessions/${sessionId}`, { title })

/** 上传表格用于聊天数据分析（短期存储，分析完成后后端自动删除） */
export const uploadChatTable = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post<any, ChatUploadInfo>('/chat/uploads', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 手动删除聊天上传的表格（用户移除文件时调用） */
export const deleteChatUpload = (uploadId: string) =>
  request.delete<any, null>(`/chat/uploads/${uploadId}`)
