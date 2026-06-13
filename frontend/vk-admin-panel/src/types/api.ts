/** Generic API response wrapper matching vk_admin_api format. */
export interface ApiResponse<T> {
    ok: boolean
    data: T | null
    error?: string
}

/** A geographic region (forum folder) with subscription status. */
export interface Region {
    id: number
    name: string
    subscribed: boolean
}

/** Full settings summary returned by GET /api/v1/settings. */
export interface SettingsSummary {
    user_id: number
    role: string | null
    regions: Region[]
    preferences: string[]
    coordinates: { lat: number; lon: number } | null
    radius: number | null
    age_preferences: { min_age: number; max_age: number }[]
    topic_types: number[]
    follow_mode: boolean
    has_forum: boolean
    forum_username: string | null
}

/** Active search record returned by GET /api/v1/searches/active. */
export interface ActiveSearch {
    search_id: number
    display_name: string
    status: string
    family_name: string
    start_time: string | null
    folder_id: number
    topic_type: string | null
    topic_type_id: number | null
}

/** User info returned by GET /api/v1/user/info. */
export interface UserInfo {
    user_id: number
    role: string | null
    regions: number[]
    forum_username: string | null
    forum_user_id: string | null
    sys_roles: string[]
}

/** Auth response after successful login. */
export interface AuthResult {
    user_id: number
}
