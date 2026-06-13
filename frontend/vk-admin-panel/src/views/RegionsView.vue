<template>
  <AppLayout>
    <LoadingSpinner v-if="regionStore.loading && regionStore.regions.length === 0" message="Загрузка регионов..." />
    <ErrorAlert v-else-if="regionStore.error" :message="regionStore.error" closable @close="regionStore.error = null" />

    <template v-else>
      <div class="regions-toolbar">
        <IconField>
          <InputIcon>
            <i class="pi pi-search" />
          </InputIcon>
          <InputText
            v-model="regionStore.searchQuery"
            placeholder="Поиск региона..."
            class="search-input"
          />
        </IconField>
        <span class="subscribed-count">Подписок: {{ regionStore.subscribedCount }}</span>
      </div>

      <div class="regions-list">
        <div v-for="region in regionStore.filteredRegions" :key="region.id" class="region-item">
          <span class="region-name">{{ region.name }}</span>
          <ToggleSwitch
            :modelValue="region.subscribed"
            @update:modelValue="() => regionStore.toggle(region.name)"
          />
        </div>
      </div>

      <div v-if="regionStore.filteredRegions.length === 0" class="empty-state">
        <p>Регионы не найдены</p>
      </div>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRegionStore } from '@/stores/regionStore'

const regionStore = useRegionStore()

onMounted(() => {
  regionStore.fetchRegions()
})
</script>

<style scoped>
.regions-toolbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}
.search-input {
  width: 300px;
}
.subscribed-count {
  color: var(--p-text-muted-color);
  font-size: 0.9rem;
}
.regions-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  max-width: 500px;
}
.region-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: white;
  border-radius: 6px;
  border: 1px solid var(--p-surface-200);
}
.region-name {
  font-weight: 500;
  color: var(--app-text-color);
}
.empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--p-text-muted-color);
}
</style>
