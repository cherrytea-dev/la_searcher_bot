import apiClient from './client'
import type { ApiResponse, UserInfo } from '@/types/api'

export async function getUserInfo(): Promise<ApiResponse<UserInfo>> {
    const { data } = await apiClient.get<ApiResponse<UserInfo>>('/api/v1/user/info')
    return data
}
