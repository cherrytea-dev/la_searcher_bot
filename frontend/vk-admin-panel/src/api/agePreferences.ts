import apiClient from './client'
import type { ApiResponse } from '@/types/api'

export interface AgePeriod {
    min_age: number
    max_age: number
}

export async function getAgePreferences(): Promise<ApiResponse<AgePeriod[]>> {
    const { data } = await apiClient.post<ApiResponse<AgePeriod[]>>('/', {
        path: '/api/v1/age-preferences',
    })
    return data
}

export async function saveAgePeriod(period: AgePeriod): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>('/', {
        path: '/api/v1/age-preferences',
        min_age: period.min_age,
        max_age: period.max_age,
    })
    return data
}

export async function deleteAgePeriod(period: AgePeriod): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>('/', {
        data: {
            path: '/api/v1/age-preferences',
            min_age: period.min_age,
            max_age: period.max_age,
        },
    })
    return data
}
