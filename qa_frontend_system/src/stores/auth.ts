import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, register as apiRegister, getMe } from '../api/auth'
import type { UserInfo, LoginRequest, RegisterRequest } from '../api/auth'

const TOKEN_KEY = 'qa_access_token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<UserInfo | null>(null)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.is_admin ?? false)
  const permissions = computed<string[]>(() => user.value?.permissions ?? [])

  function hasPermission(code: string): boolean {
    if (isAdmin.value) return true
    return permissions.value.includes(code)
  }

  function setToken(t: string) {
    token.value = t
    localStorage.setItem(TOKEN_KEY, t)
  }

  function clearToken() {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
  }

  async function login(data: LoginRequest) {
    const res = await apiLogin(data)
    setToken(res.access_token)
    await fetchMe()
  }

  async function register(data: RegisterRequest) {
    await apiRegister(data)
  }

  async function fetchMe() {
    try {
      user.value = await getMe()
    } catch {
      clearToken()
    }
  }

  async function init() {
    if (token.value) {
      await fetchMe()
    }
  }

  function logout() {
    clearToken()
  }

  return { token, user, isLoggedIn, isAdmin, permissions, hasPermission, login, register, fetchMe, init, logout }
})

