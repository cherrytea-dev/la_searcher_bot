import apiClient from './client'
import type { ApiResponse } from '@/types/api'

export async function getPreferences(): Promise<ApiResponse<string[]>> {
    const { data } = await apiClient.get<ApiResponse<string[]>>('/api/v1/preferences')
    return data
}

export async function setPreference(preference: string, enabled: boolean): Promise<ApiResponse<null>> {
    if (enabled) {
        const { data } = await apiClient.post<ApiResponse<null>>('/api/v1/preferences', { preference })
        return data
    } else {
        const { data } = await apiClient.delete<ApiResponse<null>>('/api/v1/preferences', {
            data: { preference },
        })
        return data
    }
}
