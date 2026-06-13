import axios from 'axios'

const apiClient = axios.create({
    baseURL: import.meta.env.VITE_API_URL || '',
    headers: { 'Content-Type': 'application/json' },
})

/** Key used to store auth data in localStorage. */
const AUTH_STORAGE_KEY = 'vk_admin_auth'

// ── Request interceptor — inject Authorization header ──────────────
apiClient.interceptors.request.use((config) => {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    if (raw) {
        try {
            const { method, payload } = JSON.parse(raw)
            config.headers.Authorization = `${method} ${JSON.stringify(payload)}`
        } catch {
            localStorage.removeItem(AUTH_STORAGE_KEY)
        }
    }
    return config
})

// ── Response interceptor — handle 401 (session expired) ───────────
apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem(AUTH_STORAGE_KEY)
            window.location.hash = '#/login'
        }
        return Promise.reject(error)
    },
)

export { AUTH_STORAGE_KEY }
export default apiClient
