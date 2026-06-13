<template>
  <Dialog
    :visible="visible"
    :header="title"
    :modal="true"
    :closable="true"
    @update:visible="$emit('update:visible', $event)"
  >
    <p>{{ message }}</p>
    <template #footer>
      <Button label="Отмена" severity="secondary" @click="$emit('cancel')" />
      <Button :label="confirmLabel || 'Подтвердить'" severity="danger" @click="$emit('confirm')" />
    </template>
  </Dialog>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
  title: string
  message: string
  confirmLabel?: string
}>()

defineEmits<{
  'update:visible': [value: boolean]
  confirm: []
  cancel: []
}>()
</script>
