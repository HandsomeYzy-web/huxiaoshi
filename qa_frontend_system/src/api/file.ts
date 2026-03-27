import request from '../utils/request'

export interface KnowledgeFile {
  id: number
  kb_id: number
  file_name: string
  file_type: string
  file_size: number
  status: number
  error_msg: string | null
  custom_chunk_size: number | null
  custom_chunk_overlap: number | null
}

export interface FilePageResponse {
  items: KnowledgeFile[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface FileStrategyPayload {
  custom_chunk_size: number
  custom_chunk_overlap: number
}

export interface UploadResult {
  filename: string
  status: 'success' | 'skipped' | 'failed'
  file_id?: number
  reason?: string
}

export const getFilesByKnowledgeBase = (kbId: number, params?: { page?: number; page_size?: number }) =>
  request.get<any, FilePageResponse>(`/file/kb/${kbId}`, { params })

export const uploadKnowledgeFiles = (formData: FormData) =>
  request.post<any, UploadResult[]>('/file/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })

export const updateFileStrategy = (fileId: number, data: FileStrategyPayload) =>
  request.put<any, KnowledgeFile>(`/file/${fileId}/strategy`, data)
