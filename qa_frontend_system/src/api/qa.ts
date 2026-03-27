import request from '../utils/request'

export interface QaAskPayload {
  kb_id?: number
  kb_ids?: number[]
  question: string
}

export interface CitationItem {
  chunk_id: number
  kb_id: number
  kb_name: string
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

export const retrieveKnowledgeBase = (data: QaAskPayload) =>
  request.post<any, QaAskResponse>('/qa/retrieve', data)
