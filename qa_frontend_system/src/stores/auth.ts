import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { canAccessPermission } from '../access/control'
import { getMe, login as apiLogin, register as apiRegister } from '../api/auth'
import type { LoginRequest, RegisterRequest, UserInfo } from '../api/auth'
import type { PermissionTreeNode } from '../api/admin'

const TOKEN_KEY = 'qa_access_token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<UserInfo | null>(null)
  const permissionTree = ref<PermissionTreeNode[]>([])
  const initialized = ref(false)

  const isLoggedIn = computed(() => !!token.value)
  const permissions = computed<string[]>(() => user.value?.permissions ?? [])
  const permissionSet = computed(() => new Set(permissions.value))

  function hasPermission(code: string): boolean {
    return canAccessPermission({ permissions: permissionSet.value }, code)
  }

  function setToken(value: string) {
    token.value = value
    localStorage.setItem(TOKEN_KEY, value)
  }

  function clearState() {
    token.value = null
    user.value = null
    permissionTree.value = []
    initialized.value = false
    localStorage.removeItem(TOKEN_KEY)
  }

  async function login(data: LoginRequest) {
    const res = await apiLogin(data)
    setToken(res.access_token)
    await init(true)
  }

  async function register(data: RegisterRequest) {
    await apiRegister(data)
  }

  async function fetchMe() {
    user.value = await getMe()
    permissionTree.value = user.value?.permission_tree ?? []
  }

  async function init(force = false) {
    if (!token.value) return
    if (initialized.value && !force) return
    try {
      await fetchMe()
      initialized.value = true
    } catch {
      clearState()
    }
  }

  function logout() {
    clearState()
  }

  return {
    token,
    user,
    permissionTree,
    isLoggedIn,
    permissions,
    permissionSet,
    hasPermission,
    setToken,
    login,
    register,
    fetchMe,
    init,
    logout,
  }
})
