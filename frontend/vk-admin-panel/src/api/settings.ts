import apiClient from './client'
import type { ApiResponse, SettingsSummary } from '@/types/api'

export async function getSettings(): Promise<ApiResponse<SettingsSummary>> {
    const { data } = await apiClient.get<ApiResponse<SettingsSummary>>('/api/v1/settings')
    return data
}
