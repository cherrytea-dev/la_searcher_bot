<template>
  <Message v-if="message" severity="error" :closable="closable" @close="$emit('close')">
    {{ message }}
  </Message>
</template>

<script setup lang="ts">
defineProps<{
  message: string | null
  closable?: boolean
}>()

defineEmits<{
  close: []
}>()
</script>
