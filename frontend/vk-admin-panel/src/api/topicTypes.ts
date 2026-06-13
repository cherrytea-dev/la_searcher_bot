import apiClient from './client'
import type { ApiResponse } from '@/types/api'

export async function getTopicTypes(): Promise<ApiResponse<number[]>> {
    const { data } = await apiClient.post<ApiResponse<number[]>>('/', {
        path: '/api/v1/topic-types',
    })
    return data
}

export async function addTopicType(topicTypeId: number): Promise<ApiResponse<null>> {
    const { data } = await apiClient.post<ApiResponse<null>>('/', {
        path: '/api/v1/topic-types',
        topic_type_id: topicTypeId,
    })
    return data
}

export async function removeTopicType(topicTypeId: number): Promise<ApiResponse<null>> {
    const { data } = await apiClient.delete<ApiResponse<null>>('/', {
        data: {
            path: '/api/v1/topic-types',
            topic_type_id: topicTypeId,
        },
    })
    return data
}
