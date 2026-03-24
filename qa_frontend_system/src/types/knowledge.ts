// src/types/knowledge.ts

// 1. 创建知识库的请求参数
export interface KBCreateForm {
  name: string
  description?: string
  embedding_model: string
}

// 2. 上传文件后后端返回的单条文件信息
export interface UploadedFile {
  doc_id: string
  file_name: string
}

// 3. 知识库创建成功后的返回格式
export interface KBCreateResponse {
  kb_id: string
}

// 4. 上传文件成功后的返回格式
export interface UploadResponse {
  uploaded_files: UploadedFile[]
}