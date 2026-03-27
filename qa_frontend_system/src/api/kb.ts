import request from '../utils/request'

export interface KnowledgeBase {
  id: number
  name: string
  description: string
  default_chunk_size: number
  default_chunk_overlap: number
  created_at: string
}

export interface CreateKnowledgeBasePayload {
  name: string
  description?: string
  default_chunk_size: number
  default_chunk_overlap: number
}

export const getKnowledgeBases = () => request.get<any, KnowledgeBase[]>('/kb')

export const createKnowledgeBase = (data: CreateKnowledgeBasePayload) =>
  request.post<any, KnowledgeBase>('/kb', data)
