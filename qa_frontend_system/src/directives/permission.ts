import type { Directive } from 'vue'

import { useAuthStore } from '../stores/auth'

function removeElement(el: HTMLElement) {
  if (el.parentNode) {
    el.parentNode.removeChild(el)
  }
}

/**
 * v-permission 指令：检查当前用户是否拥有指定权限码
 * 用法：v-permission="'kb.create'" 或 v-permission="['kb.create', 'kb.update']"
 */
export const permissionDirective: Directive<HTMLElement, string | string[]> = {
  mounted(el, binding) {
    const authStore = useAuthStore()
    const value = binding.value
    if (!value) {
      removeElement(el)
      return
    }

    const allowed = Array.isArray(value)
      ? value.some(code => authStore.hasPermission(code))
      : authStore.hasPermission(value)

    if (!allowed) removeElement(el)
  },
}
