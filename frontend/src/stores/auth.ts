import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { storageGet, storageGetMigrated, storageRemove, storageSet } from '../lib/safe-storage'

const TOKEN_KEY = 'tg-manage-token'
const LEGACY_TOKEN_KEY = 'tg-signer-token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(storageGetMigrated(TOKEN_KEY, LEGACY_TOKEN_KEY))

  const isAuthenticated = computed(() => !!token.value)

  function setToken(newToken: string) {
    token.value = newToken
    storageSet(TOKEN_KEY, newToken)
    if (storageGet(TOKEN_KEY) === newToken) storageRemove(LEGACY_TOKEN_KEY)
  }

  function clearToken() {
    token.value = null
    storageRemove(TOKEN_KEY)
    storageRemove(LEGACY_TOKEN_KEY)
  }

  function logout() {
    clearToken()
    window.location.href = '/'
  }

  // Check token expiry (client-side only, server validates on each request)
  function isTokenExpired(): boolean {
    if (!token.value) return true
    try {
      const payload = JSON.parse(atob(token.value.split('.')[1]))
      return payload.exp && payload.exp * 1000 < Date.now()
    } catch {
      return false
    }
  }

  return { token, isAuthenticated, setToken, clearToken, logout, isTokenExpired }
})
