import { createRouter, createWebHashHistory } from 'vue-router'
import { AUTH_STORAGE_KEY } from '@/api/client'

const router = createRouter({
    history: createWebHashHistory(),
    routes: [
        {
            path: '/login',
            name: 'Login',
            component: () => import('@/views/LoginView.vue'),
            meta: { requiresAuth: false },
        },
        {
            path: '/',
            name: 'Dashboard',
            component: () => import('@/views/DashboardView.vue'),
            meta: { requiresAuth: true },
        },
        {
            path: '/notifications',
            name: 'Notifications',
            component: () => import('@/views/NotificationsView.vue'),
            meta: { requiresAuth: true },
        },
        {
            path: '/regions',
            name: 'Regions',
            component: () => import('@/views/RegionsView.vue'),
            meta: { requiresAuth: true },
        },
        {
            path: '/coordinates',
            name: 'Coordinates',
            component: () => import('@/views/CoordinatesView.vue'),
            meta: { requiresAuth: true },
        },
        {
            path: '/radius',
            name: 'Radius',
            component: () => import('@/views/RadiusView.vue'),
            meta: { requiresAuth: true },
        },
        {
            path: '/age',
            name: 'AgePreferences',
            component: () => import('@/views/AgePreferencesView.vue'),
            meta: { requiresAuth: true },
        },
        {
            path: '/topic-types',
            name: 'TopicTypes',
            component: () => import('@/views/TopicTypesView.vue'),
            meta: { requiresAuth: true },
        },
        {
            path: '/follow-mode',
            name: 'FollowMode',
            component: () => import('@/views/FollowModeView.vue'),
            meta: { requiresAuth: true },
        },
        {
            path: '/searches',
            name: 'ActiveSearches',
            component: () => import('@/views/ActiveSearchesView.vue'),
            meta: { requiresAuth: true },
        },
    ],
})

// ── Auth guard ─────────────────────────────────────────────────────
router.beforeEach((to) => {
    if (to.meta.requiresAuth === false) return true
    const authData = localStorage.getItem(AUTH_STORAGE_KEY)
    if (!authData) return '/login'
    return true
})

export default router
