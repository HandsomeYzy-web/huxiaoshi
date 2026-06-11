import request from '../utils/request'

export interface ModelConfig {
  id: number
  model_type: string
  provider: string
  name: string
  model_name: string
  api_base_url: string
  api_key_masked: string
  is_active: boolean
  extra_params: string | null
  created_at: string
  updated_at: string
}

export interface ModelConfigCreate {
  model_type: string
  provider: string
  name: string
  model_name: string
  api_base_url: string
  api_key: string
  is_active?: boolean
  extra_params?: string
}

export interface ModelConfigUpdate {
  name?: string
  model_name?: string
  api_base_url?: string
  api_key?: string
  is_active?: boolean
  extra_params?: string
}

export interface ModelProviderInfo {
  provider: string
  display_name: string
  supported_types: string[]
}

export interface ModelActivateResponse {
  config: ModelConfig
  warning: string | null
  needs_rebuild: boolean
}

// ─── 模型配置 ────────────────────────────────────────────────

export const listModelConfigs = (modelType?: string) =>
  request.get<any, ModelConfig[]>('/models', { params: modelType ? { model_type: modelType } : {} })

export const getModelConfig = (configId: number) =>
  request.get<any, ModelConfig>(`/models/${configId}`)

export const createModelConfig = (data: ModelConfigCreate) =>
  request.post<any, ModelConfig>('/models', data)

export const updateModelConfig = (configId: number, data: ModelConfigUpdate) =>
  request.put<any, ModelConfig>(`/models/${configId}`, data)

export const deleteModelConfig = (configId: number) =>
  request.delete<any, null>(`/models/${configId}`)

export const activateModelConfig = (configId: number) =>
  request.post<any, ModelActivateResponse>(`/models/${configId}/activate`)

export const listModelProviders = () =>
  request.get<any, ModelProviderInfo[]>('/models/providers')

export const rebuildAllKnowledgeBases = () =>
  request.post<any, { total_kbs: number; total_files: number }>('/models/rebuild-all-kbs')
