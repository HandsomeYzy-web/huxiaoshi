export interface AccessContext {
  permissions?: Iterable<string>
}

export interface AppRouteAccessMeta {
  title?: string
  public?: boolean
  permission?: string
  section?: string
}

export function toCodeSet(codes: Iterable<string> = []) {
  return new Set(codes)
}

export function canAccessPermission(context: AccessContext, code?: string | null) {
  if (!code) return true
  return toCodeSet(context.permissions).has(code)
}

export function canAccessRoute(context: AccessContext, meta: AppRouteAccessMeta = {}) {
  if (meta.public) return true
  return canAccessPermission(context, meta.permission)
}

export function getSectionLabel(path: string) {
  if (path.startsWith('/workspace')) return '工作区'
  if (path.startsWith('/admin')) return '权限与配置'
  if (path.startsWith('/chat')) return '智能问答'
  return '导航'
}
