import request from '../utils/request'

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
  intent?: string | null
  generated_sql?: string | null
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

// 流式响应事件类型
export interface StreamEvent {
  event: 'user_message' | 'session_info' | 'intent' | 'status' | 'citations' | 'sql' | 'sql_result' | 'delta' | 'done' | 'error'
  data: any
}

// 意图分类数据
export interface IntentData {
  intent: 'casual_chat' | 'data_query' | 'doc_search'
  confidence: number
  reason: string
}

// 状态步骤数据
export interface StatusData {
  step: string
  message: string
}

// SQL 查询结果数据
export interface SqlResultData {
  columns: string[]
  rows: Record<string, any>[]
}

// 流式响应处理器
export interface StreamHandlers {
  onUserMessage?: (message: { id: number; content: string; created_at: string }) => void
  onSessionInfo?: (session: { id: number; title: string; updated_at: string }) => void
  onIntent?: (data: IntentData) => void
  onStatus?: (data: StatusData) => void
  onCitations?: (citations: ChatCitation[]) => void
  onSql?: (data: { sql: string }) => void
  onSqlResult?: (data: SqlResultData) => void
  onDelta?: (content: string) => void
  onDone?: (message: { id: number; content: string; model_used: string | null; retrieved_count: number; intent: string; created_at: string }) => void
  onError?: (error: { message: string }) => void
}

export const listChatSessions = () =>
  request.get<any, ChatSessionSummary[]>('/chat/sessions')

export const createChatSession = (title = '新对话') =>
  request.post<any, ChatSessionSummary>('/chat/sessions', { title })

export const getChatSessionDetail = (sessionId: number) =>
  request.get<any, ChatSessionDetail>(`/chat/sessions/${sessionId}`)

export const appendChatMessage = (sessionId: number, question: string) =>
  request.post<any, ChatMessageCreateResponse>(`/chat/sessions/${sessionId}/messages`, { question })

/**
 * 流式发送消息
 * @param sessionId 会话ID
 * @param question 问题内容
 * @param handlers 事件处理器
 * @returns 返回 abort 函数用于取消请求
 */
export const appendChatMessageStream = (
  sessionId: number,
  question: string,
  handlers: StreamHandlers
): (() => void) => {
  const abortController = new AbortController()

  const fetchStream = async () => {
    try {
      const token = localStorage.getItem('qa_access_token')
      const response = await fetch(`/api/v1/chat/sessions/${sessionId}/messages/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ question }),
        signal: abortController.signal,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: '请求失败' }))
        handlers.onError?.({ message: errorData.detail || errorData.message || '请求失败' })
        return
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        handlers.onError?.({ message: '无法读取响应流' })
        return
      }

      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // 处理 SSE 格式的数据
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // 保留不完整的最后一行

        let currentEvent: string | null = null

        for (const line of lines) {
          const trimmedLine = line.trim()
          if (trimmedLine.startsWith('event:')) {
            currentEvent = trimmedLine.slice(6).trim()
          } else if (trimmedLine.startsWith('data:')) {
            const dataStr = trimmedLine.slice(5).trim()
            try {
              const data = JSON.parse(dataStr)

              switch (currentEvent) {
                case 'user_message':
                  handlers.onUserMessage?.(data)
                  break
                case 'session_info':
                  handlers.onSessionInfo?.(data)
                  break
                case 'intent':
                  handlers.onIntent?.(data)
                  break
                case 'status':
                  handlers.onStatus?.(data)
                  break
                case 'citations':
                  handlers.onCitations?.(data)
                  break
                case 'sql':
                  handlers.onSql?.(data)
                  break
                case 'sql_result':
                  handlers.onSqlResult?.(data)
                  break
                case 'delta':
                  handlers.onDelta?.(data.content)
                  break
                case 'done':
                  handlers.onDone?.(data)
                  break
                case 'error':
                  handlers.onError?.(data)
                  break
              }
            } catch (e) {
              console.error('解析 SSE 数据失败:', e, dataStr)
            }
          }
        }
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        return // 用户取消，不视为错误
      }
      handlers.onError?.({ message: error.message || '网络请求失败' })
    }
  }

  fetchStream()

  return () => abortController.abort()
}

export const deleteChatSession = (sessionId: number) =>
  request.delete<any, null>(`/chat/sessions/${sessionId}`)

export const renameChatSession = (sessionId: number, title: string) =>
  request.patch<any, ChatSessionSummary>(`/chat/sessions/${sessionId}`, { title })
