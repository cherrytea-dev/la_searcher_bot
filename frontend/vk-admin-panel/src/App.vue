<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import bridge from '@vkontakte/vk-bridge'

onMounted(() => {
  // Initialize VK Bridge (required for VK Mini Apps)
  // This enables communication with the VK platform (auto-resize, etc.)
  bridge.send('VKWebAppInit')
})
</script>

<style>
:root {
  --app-text-color: #212529;
}
</style>
