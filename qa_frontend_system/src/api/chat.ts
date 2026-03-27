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

export const listChatSessions = () =>
  request.get<any, ChatSessionSummary[]>('/chat/sessions')

export const createChatSession = (title = '新对话') =>
  request.post<any, ChatSessionSummary>('/chat/sessions', { title })

export const getChatSessionDetail = (sessionId: number) =>
  request.get<any, ChatSessionDetail>(`/chat/sessions/${sessionId}`)

export const appendChatMessage = (sessionId: number, question: string) =>
  request.post<any, ChatMessageCreateResponse>(`/chat/sessions/${sessionId}/messages`, { question })
