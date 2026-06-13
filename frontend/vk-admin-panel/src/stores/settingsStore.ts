import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SettingsSummary } from '@/types/api'
import { getSettings } from '@/api/settings'

export const useSettingsStore = defineStore('settings', () => {
    const summary = ref<SettingsSummary | null>(null)
    const loading = ref(false)
    const error = ref<string | null>(null)

    async function fetchSettings() {
        loading.value = true
        error.value = null
        try {
            const res = await getSettings()
            if (res.ok && res.data) {
                summary.value = res.data
            } else {
                error.value = res.error || 'Failed to load settings'
            }
        } catch {
            error.value = 'Network error while loading settings'
        } finally {
            loading.value = false
        }
    }

    function clear() {
        summary.value = null
        error.value = null
    }

    return { summary, loading, error, fetchSettings, clear }
})
