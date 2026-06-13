import apiClient from './client'
import type { ApiResponse } from '@/types/api'

export async function getFollowMode(): Promise<ApiResponse<boolean>> {
    const { data } = await apiClient.post<ApiResponse<boolean>>('/', {
        path: '/api/v1/follow-mode',
    })
    return data
}

export async function setFollowMode(enabled: boolean): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>('/', {
        path: '/api/v1/follow-mode',
        enabled,
    })
    return data
}
