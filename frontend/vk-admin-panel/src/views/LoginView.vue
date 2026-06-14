<template>
  <div class="login-page">
    <Card class="login-card">
      <template #title>
        <h2>VK Admin Panel</h2>
      </template>
      <template #content>
        <p class="login-description">
          Панель управления настройками уведомлений LizaAlert Searcher Bot
        </p>

        <ErrorAlert :message="auth.error" closable @close="auth.error = null" />

        <div class="login-buttons">
          <!-- Telegram Login Widget -->
          <div id="tg-login-widget" ref="tgWidgetRef"></div>

          <!-- VK OAuth -->
          <Button
            label="Войти через VK"
            icon="pi pi-vk"
            severity="info"
            :loading="auth.loading"
            @click="startVkOAuth"
          />
        </div>
      </template>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const auth = useAuthStore()
const tgWidgetRef = ref<HTMLDivElement>()

// ── VK ID OAuth 2.0 with PKCE ───────────────────────────────────────
// Docs: https://id.vk.com/about/business/go/docs/ru/vk-id/oauth-flow
const VK_CLIENT_ID = import.meta.env.VITE_VK_CLIENT_ID || ''
const REDIRECT_URI = window.location.origin + window.location.pathname

/**
 * Generate a random string for PKCE code_verifier or state.
 * Uses characters from a-z, A-Z, 0-9, _, - (as per VK ID docs).
 */
function generateRandomString(length: number): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-'
  const array = new Uint8Array(length)
  crypto.getRandomValues(array)
  let result = ''
  for (let i = 0; i < length; i++) {
    result += chars[array[i] % chars.length]
  }
  return result
}

/**
 * SHA-256 hash → base64url encoding (for PKCE code_challenge).
 */
async function sha256Base64url(plain: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(plain)
  const hash = await crypto.subtle.digest('SHA-256', data)
  // Convert ArrayBuffer to base64url
  const bytes = new Uint8Array(hash)
  let binary = ''
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

/** Store PKCE verifier + state + device_id in sessionStorage for callback verification. */
const PKCE_STORAGE_KEY = 'vk_oauth_pkce'

/**
 * Generate a UUID v4 for device_id.
 */
function generateUUID(): string {
  const hex = '0123456789abcdef'
  let uuid = ''
  for (let i = 0; i < 36; i++) {
    if (i === 8 || i === 13 || i === 18 || i === 23) {
      uuid += '-'
    } else if (i === 14) {
      uuid += '4'
    } else if (i === 19) {
      uuid += hex[(Math.floor(Math.random() * 4) + 8)]
    } else {
      uuid += hex[Math.floor(Math.random() * 16)]
    }
  }
  return uuid
}

function startVkOAuth() {
  // 1. Generate PKCE code_verifier (random 64-byte string)
  const codeVerifier = generateRandomString(64)

  // 2. Generate state (random 32+ byte string)
  const state = generateRandomString(32)

  // 3. Compute code_challenge = base64url(SHA256(code_verifier))
  sha256Base64url(codeVerifier).then((codeChallenge) => {
    // Save verifier + state for the callback (device_id will come from VK ID response)
    sessionStorage.setItem(
      PKCE_STORAGE_KEY,
      JSON.stringify({ code_verifier: codeVerifier, state }),
    )

    // 4. Redirect to VK ID authorization endpoint
    //    Per docs: device_id is NOT passed to /authorize — VK ID generates it
    //    and returns it in the callback payload (Step 3-4).
    const url = new URL('https://id.vk.com/authorize')
    url.searchParams.set('response_type', 'code')
    url.searchParams.set('client_id', VK_CLIENT_ID)
    url.searchParams.set('redirect_uri', REDIRECT_URI)
    url.searchParams.set('state', state)
    url.searchParams.set('code_challenge', codeChallenge)
    url.searchParams.set('code_challenge_method', 's256')
    // scope: space-separated list; default 'vkid.personal_info' is enough
    window.location.href = url.toString()
  })
}

/**
 * Parse VK ID OAuth callback.
 *
 * VK ID can return params in two formats:
 * 1. Direct query params: ?code=...&device_id=...&state=...&type=code_v2
 * 2. Payload JSON: ?payload={"code":"...","state":"...","type":"code_v2","device_id":"..."}
 *
 * We must SAVE the device_id from the response and use it in the token exchange (Step 4-5).
 *
 * Reference: https://id.vk.com/about/business/go/docs/ru/vk-id/oauth-flow
 */
async function handleOAuthCallback() {
  const params = new URLSearchParams(window.location.search)

  let code: string | null
  let state: string | null
  let type: string | null
  let device_id: string | null

  // Try format 1: payload JSON
  const payloadRaw = params.get('payload')
  if (payloadRaw) {
    try {
      const payload = JSON.parse(payloadRaw)
      code = payload.code || null
      state = payload.state || null
      type = payload.type || null
      device_id = payload.device_id || null
    } catch {
      return
    }
  } else {
    // Try format 2: direct query params
    code = params.get('code')
    state = params.get('state')
    type = params.get('type')
    device_id = params.get('device_id')
  }

  if (!code || type !== 'code_v2') return

  // Clean URL (remove query params)
  const cleanUrl = window.location.origin + window.location.pathname + window.location.hash
  window.history.replaceState({}, '', cleanUrl)

  // Restore PKCE verifier from sessionStorage and verify state
  const storedRaw = sessionStorage.getItem(PKCE_STORAGE_KEY)
  if (!storedRaw) {
    auth.error = 'Missing PKCE state — please try again'
    return
  }
  const stored = JSON.parse(storedRaw)
  sessionStorage.removeItem(PKCE_STORAGE_KEY)

  // Verify state to prevent CSRF
  if (stored.state !== state) {
    auth.error = 'State mismatch — possible CSRF attack'
    return
  }

  // Save device_id from VK ID response (Step 4: "Save the received device_id")
  // and use it in the token exchange request (Step 5)
  await auth.loginVk({
    code,
    code_verifier: stored.code_verifier,
    device_id: device_id || '',
    redirect_uri: REDIRECT_URI,
  })
  if (auth.isAuthenticated) {
    router.push('/')
  }
}

// ── Telegram Login Widget ───────────────────────────────────────────
function loadTgWidget() {
  if (!tgWidgetRef.value) return

  const script = document.createElement('script')
  script.src = 'https://telegram.org/js/telegram-widget.js?22'
  script.setAttribute('data-telegram-login', import.meta.env.VITE_TG_BOT_NAME || '')
  script.setAttribute('data-size', 'large')
  script.setAttribute('data-onauth', 'onTelegramAuth(user)')
  script.setAttribute('data-request-access', 'write')
  tgWidgetRef.value.appendChild(script)
}

// Telegram callback (global function)
;(window as any).onTelegramAuth = async (user: Record<string, unknown>) => {
  await auth.loginTg(user)
  if (auth.isAuthenticated) {
    router.push('/')
  }
}

// ── VK Mini Apps Auto-Login ────────────────────────────────────────
/**
 * Detect VK Mini Apps launch params in the URL and auto-authenticate.
 *
 * VK passes launch params as URL fragment (hash) when opening a Mini App:
 * #vk_user_id=123&vk_app_id=456&sign=abc&...
 *
 * The backend verifies the HMAC-SHA256 signature before trusting vk_user_id.
 */
function detectVkMiniAppLaunchParams(): Record<string, string> | null {
  const hash = window.location.hash.replace(/^#/, '')
  if (!hash || !hash.includes('vk_user_id=')) return null

  const params: Record<string, string> = {}
  for (const part of hash.split('&')) {
    const eqIdx = part.indexOf('=')
    if (eqIdx === -1) continue
    params[decodeURIComponent(part.slice(0, eqIdx))] = decodeURIComponent(part.slice(eqIdx + 1))
  }

  // Must have vk_user_id and sign to be valid Mini Apps launch params
  if (!params['vk_user_id'] || !params['sign']) return null

  return params
}

// ── Lifecycle ───────────────────────────────────────────────────────
onMounted(async () => {
  // Check for VK OAuth callback first
  await handleOAuthCallback()

  // If already authenticated, redirect
  auth.init()
  if (auth.isAuthenticated) {
    router.push('/')
    return
  }

  // Try VK Mini Apps auto-login (launch params in URL hash)
  const miniAppParams = detectVkMiniAppLaunchParams()
  if (miniAppParams) {
    await auth.loginVkMiniApp(miniAppParams)
    if (auth.isAuthenticated) {
      // Clean the hash from URL after successful auth
      window.history.replaceState({}, '', window.location.pathname)
      router.push('/')
      return
    }
  }

  // Load TG widget
  loadTgWidget()
})

// Redirect on successful auth
watch(() => auth.isAuthenticated, (val) => {
  if (val) router.push('/')
})
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--p-surface-50);
}
.login-card {
  width: 100%;
  max-width: 400px;
}
.login-description {
  color: var(--p-text-muted-color);
  margin-bottom: 1.5rem;
}
.login-buttons {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}
</style>
