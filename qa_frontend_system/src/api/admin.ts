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
