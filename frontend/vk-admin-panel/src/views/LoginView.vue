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

// ── VK OAuth ────────────────────────────────────────────────────────
const VK_CLIENT_ID = import.meta.env.VITE_VK_CLIENT_ID || ''
const REDIRECT_URI = window.location.origin + window.location.pathname

function startVkOAuth() {
  const url = new URL('https://oauth.vk.com/authorize')
  url.searchParams.set('client_id', VK_CLIENT_ID)
  url.searchParams.set('redirect_uri', REDIRECT_URI)
  url.searchParams.set('response_type', 'code')
  url.searchParams.set('scope', '') // no special permissions needed
  window.location.href = url.toString()
}

// Handle OAuth callback — parse ?code=XXX from URL
async function handleOAuthCallback() {
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  if (!code) return

  // Clean URL (remove ?code=...)
  const cleanUrl = window.location.origin + window.location.pathname
  window.history.replaceState({}, '', cleanUrl)

  await auth.loginVk(code, REDIRECT_URI)
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
