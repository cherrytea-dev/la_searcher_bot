<template>
  <header class="app-header">
    <div class="header-title">
      <h1>{{ pageTitle }}</h1>
    </div>
    <div class="header-user" v-if="auth.isAuthenticated">
      <Tag :value="`ID: ${auth.userId}`" severity="info" />
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const route = useRoute()
const auth = useAuthStore()

const pageTitle = computed(() => {
  const titles: Record<string, string> = {
    Login: 'Вход',
    Dashboard: 'Главная',
    Notifications: 'Уведомления',
    Regions: 'Регионы',
    Coordinates: 'Координаты',
    Radius: 'Радиус',
    AgePreferences: 'Возрастные предпочтения',
    TopicTypes: 'Типы поисков',
    FollowMode: 'Режим отслеживания',
    ActiveSearches: 'Активные поиски',
  }
  return titles[route.name as string] || 'VK Admin Panel'
})
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  background: white;
  border-bottom: 1px solid var(--p-surface-200);
}
.header-title h1 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}
.header-user {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
</style>
