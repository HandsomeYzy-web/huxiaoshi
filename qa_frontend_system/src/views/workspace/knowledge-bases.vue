<template>
  <KbManager v-model="selectedKbId" />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import KbManager from '../../components/KbManager.vue'

const selectedKbId = ref<number | null>(null)
</script>
