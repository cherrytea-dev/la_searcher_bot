<template>
  <aside class="app-sidebar">
    <div class="sidebar-header">
      <h2>VK Admin Panel</h2>
    </div>
    <nav>
      <ul>
        <li v-for="item in menuItems" :key="item.path">
          <router-link :to="item.path" class="sidebar-link">
            <span class="sidebar-icon">{{ item.icon }}</span>
            {{ item.label }}
          </router-link>
        </li>
      </ul>
    </nav>
    <div class="sidebar-footer">
      <Button
        label="Выйти"
        icon="pi pi-sign-out"
        severity="secondary"
        size="small"
        @click="handleLogout"
      />
    </div>
  </aside>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const auth = useAuthStore()

const menuItems = [
  { path: '/', label: 'Главная', icon: '🏠' },
  { path: '/notifications', label: 'Уведомления', icon: '🔔' },
  { path: '/regions', label: 'Регионы', icon: '📍' },
  { path: '/coordinates', label: 'Координаты', icon: '📌' },
  { path: '/radius', label: 'Радиус', icon: '📏' },
  { path: '/age', label: 'Возраст', icon: '🎂' },
  { path: '/topic-types', label: 'Типы поисков', icon: '🏷️' },
  { path: '/follow-mode', label: 'Режим отслеживания', icon: '👁️' },
  { path: '/searches', label: 'Активные поиски', icon: '🔍' },
]

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-sidebar {
  position: fixed;
  left: 0;
  top: 0;
  width: 250px;
  height: 100vh;
  background: var(--p-surface-800);
  color: white;
  display: flex;
  flex-direction: column;
  z-index: 100;
}
.sidebar-header {
  padding: 1.25rem;
  border-bottom: 1px solid var(--p-surface-600);
}
.sidebar-header h2 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
}
nav {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem 0;
}
ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
.sidebar-link {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.25rem;
  color: var(--p-surface-200);
  text-decoration: none;
  transition: background 0.2s;
}
.sidebar-link:hover,
.sidebar-link.router-link-active {
  background: var(--p-surface-700);
  color: white;
}
.sidebar-icon {
  font-size: 1.1rem;
  width: 1.5rem;
  text-align: center;
}
.sidebar-footer {
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--p-surface-600);
}
</style>
