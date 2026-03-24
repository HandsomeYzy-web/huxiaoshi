// src/api/admin.ts
import request from './request'

// ===== 1. 知识库相关的类型定义 (后续建议移到 src/types/admin.d.ts) =====
export interface KBCreateForm {
  name: string
  description?: string
  embedding_model: string
}

export interface KnowledgeBaseItem {
  id: string
  name: string
  description: string
  embedding_model: string
  created_at: string
}

// ===== 2. 知识库相关的 API 请求方法 =====

/**
 * 获取所有知识库列表
 */
export function getKnowledgeBases() {
  // 注意：因为我们在后端的 main.py 里给 admin_kb 加了前缀 prefix="/api/v1/admin/kb"
  // 并且 request 拦截器已经剥离了 {code, msg, data}，这里直接声明返回 data 的类型 KnowledgeBaseItem[]
  return request.get<any, KnowledgeBaseItem[]>('/api/v1/admin/kb/list')
}

/**
 * 创建新的知识库
 */
export function createKnowledgeBase(data: KBCreateForm) {
  return request.post<any, { kb_id: string }>('/api/v1/admin/kb/', data)
}