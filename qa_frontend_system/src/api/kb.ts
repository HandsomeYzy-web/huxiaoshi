import request from '../utils/request'

export interface KnowledgeBase {
  id: number
  name: string
  description: string
  default_chunk_size: number
  default_chunk_overlap: number
  retrieval_top_k: number
  retrieval_score_threshold: number
  enable_rerank: boolean
  created_at: string
}

export interface CreateKnowledgeBasePayload {
  name: string
  description?: string
  default_chunk_size: number
  default_chunk_overlap: number
  retrieval_top_k: number
  retrieval_score_threshold: number
  enable_rerank: boolean
}

export interface UpdateKnowledgeBasePayload {
  description?: string
  default_chunk_size?: number
  default_chunk_overlap?: number
  retrieval_top_k?: number
  retrieval_score_threshold?: number
  enable_rerank?: boolean
}

export const getKnowledgeBases = () => request.get<any, KnowledgeBase[]>('/kb')

export const createKnowledgeBase = (data: CreateKnowledgeBasePayload) =>
  request.post<any, KnowledgeBase>('/kb', data)

export const updateKnowledgeBase = (kbId: number, data: UpdateKnowledgeBasePayload) =>
  request.patch<any, KnowledgeBase>(`/kb/${kbId}`, data)

export const deleteKnowledgeBase = (kbId: number) =>
  request.delete<any, null>(`/kb/${kbId}`)
