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

export interface ChunkItem {
  id: number
  kb_id: number
  file_id: number
  chunk_index: number
  content: string
  char_count: number
  created_at: string
}

export interface ChunkPageResponse {
  items: ChunkItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export const getFilesByKnowledgeBase = (kbId: number, params?: { page?: number; page_size?: number }) =>
  request.get<any, FilePageResponse>(`/file/kb/${kbId}`, { params })

export const uploadKnowledgeFiles = (formData: FormData) =>
  request.post<any, UploadResult[]>('/file/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })

export const updateFileStrategy = (fileId: number, data: FileStrategyPayload) =>
  request.put<any, KnowledgeFile>(`/file/${fileId}/strategy`, data)

export const deleteFile = (fileId: number) =>
  request.delete<any, null>(`/file/${fileId}`)

export const getFileChunks = (fileId: number, params?: { page?: number; page_size?: number }) =>
  request.get<any, ChunkPageResponse>(`/file/${fileId}/chunks`, { params })

export const renameFile = (fileId: number, newName: string) =>
  request.put<any, KnowledgeFile>(`/file/${fileId}/rename`, { new_name: newName })
