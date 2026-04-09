import request from '../utils/request'

// ─── Types ────────────────────────────────────────────────────

export interface Permission {
  code: string
  name: string
  description: string
  module: string
}

export interface Role {
  id: number
  name: string
  description: string | null
  is_system: boolean
  created_at: string
  permissions: string[]
}

export interface AdminUser {
  id: number
  username: string
  email: string
  is_active: boolean
  is_admin: boolean
  created_at: string
  roles: Role[]
}

export interface KBAccessInfo {
  kb_id: number
  accessible_role_ids: number[]
}

// ─── Permission APIs ──────────────────────────────────────────

export const listPermissions = () =>
  request.get<any, Permission[]>('/admin/permissions')

// ─── Role APIs ────────────────────────────────────────────────

export const listRoles = () =>
  request.get<any, Role[]>('/admin/roles')

export const createRole = (data: { name: string; description?: string }) =>
  request.post<any, Role>('/admin/roles', data)

export const updateRole = (roleId: number, data: { name: string; description?: string }) =>
  request.put<any, Role>(`/admin/roles/${roleId}`, data)

export const deleteRole = (roleId: number) =>
  request.delete<any, null>(`/admin/roles/${roleId}`)

export const setRolePermissions = (roleId: number, permissionCodes: string[]) =>
  request.put<any, null>(`/admin/roles/${roleId}/permissions`, { permission_codes: permissionCodes })

// ─── User Management APIs ─────────────────────────────────────

export const listAdminUsers = () =>
  request.get<any, AdminUser[]>('/admin/users')

export const setUserRoles = (userId: number, roleIds: number[]) =>
  request.put<any, null>(`/admin/users/${userId}/roles`, { role_ids: roleIds })

export const setUserAdmin = (userId: number, isAdmin: boolean) =>
  request.put<any, null>(`/admin/users/${userId}/admin?is_admin=${isAdmin}`)

// ─── KB Access Control APIs ───────────────────────────────────

export const getAllKBAccess = () =>
  request.get<any, KBAccessInfo[]>('/admin/kb/access/all')

export const setKBAccess = (kbId: number, roleIds: number[]) =>
  request.put<any, null>(`/admin/kb/${kbId}/access`, { role_ids: roleIds })

export const getKBAccess = (kbId: number) =>
  request.get<any, KBAccessInfo>(`/admin/kb/${kbId}/access`)

// ─── Model Config Types ───────────────────────────────────────

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

// ─── Model Config APIs ────────────────────────────────────────

export const listModelConfigs = (modelType?: string) =>
  request.get<any, ModelConfig[]>('/admin/models', { params: modelType ? { model_type: modelType } : {} })

export const getModelConfig = (configId: number) =>
  request.get<any, ModelConfig>(`/admin/models/${configId}`)

export const createModelConfig = (data: ModelConfigCreate) =>
  request.post<any, ModelConfig>('/admin/models', data)

export const updateModelConfig = (configId: number, data: ModelConfigUpdate) =>
  request.put<any, ModelConfig>(`/admin/models/${configId}`, data)

export const deleteModelConfig = (configId: number) =>
  request.delete<any, null>(`/admin/models/${configId}`)

export const activateModelConfig = (configId: number) =>
  request.post<any, ModelActivateResponse>(`/admin/models/${configId}/activate`)

export const listModelProviders = () =>
  request.get<any, ModelProviderInfo[]>('/admin/models/providers')

export const rebuildAllKnowledgeBases = () =>
  request.post<any, { total_kbs: number; total_files: number }>('/admin/models/rebuild-all-kbs')
