<template>
  <div class="workspace-grid">
    <KbManager v-model="selectedKbId" class="left-panel" @loaded="handleLoaded" />
    <QaTester :kb-id="selectedKbId" :knowledge-bases="knowledgeBases" class="right-panel" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import KbManager from '../../components/KbManager.vue'
import QaTester from '../../components/QaTester.vue'
import type { KnowledgeBase } from '../../api/kb'

const selectedKbId = ref<number | null>(null)
const knowledgeBases = ref<KnowledgeBase[]>([])

const handleLoaded = (list: KnowledgeBase[]) => {
  knowledgeBases.value = list
}
</script>

<style scoped>
.workspace-grid {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 20px;
  min-height: calc(100vh - 160px);
  align-items: stretch;
}

.left-panel,
.right-panel {
  min-width: 0;
  min-height: 0;
}

@media (max-width: 1080px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
}
</style>

