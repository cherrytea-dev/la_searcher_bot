import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { AUTH_STORAGE_KEY } from '@/api/client'
import { authTg, authVk, authVkMiniApp } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
    const method = ref<'TG' | 'VK' | 'VK_MINI_APP' | null>(null)
    const userId = ref<number | null>(null)
    const payload = ref<Record<string, unknown> | null>(null)
    const loading = ref(false)
    const error = ref<string | null>(null)

    const isAuthenticated = computed(() => userId.value !== null)

    /** Restore auth state from localStorage on app load. */
    function init() {
        const raw = localStorage.getItem(AUTH_STORAGE_KEY)
        if (!raw) return
        try {
            const stored = JSON.parse(raw)
            method.value = stored.method
            userId.value = stored.user_id
            payload.value = stored.payload
        } catch {
            localStorage.removeItem(AUTH_STORAGE_KEY)
        }
    }

    /** Persist auth state to localStorage. */
    function _persist() {
        localStorage.setItem(
            AUTH_STORAGE_KEY,
            JSON.stringify({
                method: method.value,
                user_id: userId.value,
                payload: payload.value,
            }),
        )
    }

    /** Authenticate via Telegram Login Widget. */
    async function loginTg(tgData: Record<string, unknown>) {
        loading.value = true
        error.value = null
        try {
            const res = await authTg(tgData)
            if (res.ok && res.data) {
                method.value = 'TG'
                userId.value = res.data.user_id
                payload.value = tgData
                _persist()
            } else {
                error.value = res.error || 'Telegram authentication failed'
            }
        } catch (e) {
            error.value = 'Network error during Telegram authentication'
        } finally {
            loading.value = false
        }
    }

    /** Authenticate via VK ID OAuth code exchange (PKCE flow). */
    async function loginVk(params: {
        code: string
        code_verifier: string
        device_id: string
        redirect_uri: string
    }) {
        loading.value = true
        error.value = null
        try {
            const res = await authVk(params)
            if (res.ok && res.data) {
                method.value = 'VK'
                userId.value = res.data.user_id
                // Store internal user_id for re-authentication on subsequent requests.
                // Backend _auth_vk Mode 1 accepts {user_id: int} and verifies user exists.
                payload.value = { user_id: res.data.user_id }
                _persist()
            } else {
                error.value = res.error || 'VK authentication failed'
            }
        } catch (e) {
            error.value = 'Network error during VK authentication'
        } finally {
            loading.value = false
        }
    }

    /**
     * Authenticate via VK Mini Apps launch params.
     * Sends all launch params (vk_user_id, sign, vk_app_id, etc.) to backend
     * which verifies the HMAC-SHA256 signature.
     */
    async function loginVkMiniApp(launchParams: Record<string, string>) {
        loading.value = true
        error.value = null
        try {
            const res = await authVkMiniApp(launchParams)
            if (res.ok && res.data) {
                method.value = 'VK_MINI_APP'
                userId.value = res.data.user_id
                // Store internal user_id for re-authentication on subsequent requests.
                payload.value = { user_id: res.data.user_id }
                _persist()
            } else {
                error.value = res.error || 'VK Mini Apps authentication failed'
            }
        } catch (e) {
            error.value = 'Network error during VK Mini Apps authentication'
        } finally {
            loading.value = false
        }
    }

    /** Log out — clear state and localStorage. */
    function logout() {
        method.value = null
        userId.value = null
        payload.value = null
        error.value = null
        localStorage.removeItem(AUTH_STORAGE_KEY)
    }

    return {
        method,
        userId,
        payload,
        loading,
        error,
        isAuthenticated,
        init,
        loginTg,
        loginVk,
        loginVkMiniApp,
        logout,
    }
})
