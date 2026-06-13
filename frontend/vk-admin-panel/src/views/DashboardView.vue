<template>
  <AppLayout>
    <LoadingSpinner v-if="loading" message="Загрузка настроек..." />
    <ErrorAlert v-else-if="error" :message="error" />

    <template v-else-if="summary">
      <div class="dashboard-grid">
        <Card>
          <template #title>👤 Роль</template>
          <template #content>
            <p class="stat-value">{{ summary.role || 'Не указана' }}</p>
          </template>
        </Card>

        <Card>
          <template #title>📍 Регионы</template>
          <template #content>
            <p class="stat-value">{{ summary.regions.length }} подписок</p>
            <router-link to="/regions" class="action-link">Управлять</router-link>
          </template>
        </Card>

        <Card>
          <template #title>🔔 Уведомления</template>
          <template #content>
            <p class="stat-value">{{ summary.preferences.length }} включено</p>
            <router-link to="/notifications" class="action-link">Настроить</router-link>
          </template>
        </Card>

        <Card>
          <template #title>📌 Координаты</template>
          <template #content>
            <p class="stat-value">{{ summary.coordinates ? 'Установлены' : 'Не установлены' }}</p>
            <router-link to="/coordinates" class="action-link">Изменить</router-link>
          </template>
        </Card>

        <Card>
          <template #title>📏 Радиус</template>
          <template #content>
            <p class="stat-value">{{ summary.radius ? `${summary.radius} км` : 'Не установлен' }}</p>
            <router-link to="/radius" class="action-link">Изменить</router-link>
          </template>
        </Card>

        <Card>
          <template #title>🎂 Возраст</template>
          <template #content>
            <p class="stat-value">{{ summary.age_preferences.length }} периодов</p>
            <router-link to="/age" class="action-link">Настроить</router-link>
          </template>
        </Card>

        <Card>
          <template #title>🏷️ Типы поисков</template>
          <template #content>
            <p class="stat-value">{{ summary.topic_types.length }} выбрано</p>
            <router-link to="/topic-types" class="action-link">Настроить</router-link>
          </template>
        </Card>

        <Card>
          <template #title>🔗 Форум</template>
          <template #content>
            <p class="stat-value">{{ summary.forum_username || 'Не привязан' }}</p>
          </template>
        </Card>
      </div>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useSettingsStore } from '@/stores/settingsStore'

const settings = useSettingsStore()

const loading = computed(() => settings.loading)
const error = computed(() => settings.error)
const summary = computed(() => settings.summary)

onMounted(() => {
  settings.fetchSettings()
})
</script>

<style scoped>
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
}
.stat-value {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 0.5rem;
}
.action-link {
  color: var(--p-primary-color);
  text-decoration: none;
  font-size: 0.9rem;
}
.action-link:hover {
  text-decoration: underline;
}
</style>
