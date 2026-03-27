import request from '../utils/request'

export interface QaAskPayload {
  kb_id: number
  question: string
  top_k?: number
}

export interface CitationItem {
  chunk_id: number
  file_id: number
  file_name: string
  score: number
  content: string
}

export interface QaAskResponse {
  answer: string
  citations: CitationItem[]
  retrieved_count: number
  model_used: string | null
}

export const askKnowledgeBase = (data: QaAskPayload) =>
  request.post<any, QaAskResponse>('/qa/ask', data)
