<template>
  <div class="overview-grid">
    <section class="hero-card">
      <div class="hero-copy">
        <div class="eyebrow">Workspace</div>
        <h2>知识库概览</h2>
        <div class="hero-badge">当前账号可访问的知识库统计</div>
      </div>

      <div class="hero-metrics">
        <div class="metric-card">
          <span class="metric-label">知识库数量</span>
          <strong class="metric-value">{{ canViewKnowledgeBases ? knowledgeBases.length : '--' }}</strong>
          <span class="metric-hint">{{ canViewKnowledgeBases ? '当前账号可访问' : '缺少知识库查看权限' }}</span>
        </div>
        <div class="metric-card">
          <span class="metric-label">文件总数</span>
          <strong class="metric-value">{{ canViewFileStats ? totalFiles : '--' }}</strong>
          <span class="metric-hint">{{ canViewFileStats ? '已按知识库汇总' : '缺少文件统计权限' }}</span>
        </div>
      </div>
    </section>

    <section class="insight-card">
      <div class="card-header">
        <div>
          <div class="card-title">文件分布饼图</div>
          <div class="card-subtitle">按知识库统计当前已入库文件数量</div>
        </div>
        <el-tag v-if="chartRows.length" type="success" effect="plain">共 {{ chartRows.length }} 个知识库</el-tag>
      </div>

      <div v-if="!canViewKnowledgeBases" class="state-block">
        <el-empty description="当前账号没有知识库查看权限，无法展示概览数据。" />
      </div>

      <div v-else-if="!canViewFileStats" class="state-block">
        <el-empty description="当前账号没有文件统计权限，无法展示文件分布图。" />
      </div>

      <div v-else-if="loading" class="state-block">
        <el-skeleton animated>
          <template #template>
            <el-skeleton-item variant="h3" style="width: 40%; margin-bottom: 18px;" />
            <el-skeleton-item variant="rect" style="width: 100%; height: 320px;" />
          </template>
        </el-skeleton>
      </div>

      <div v-else-if="errorMessage" class="state-block">
        <el-result icon="warning" title="概览加载失败" :sub-title="errorMessage" />
      </div>

      <div v-else-if="!knowledgeBases.length" class="state-block">
        <el-empty description="当前还没有可访问的知识库。" />
      </div>

      <div v-else-if="!totalFiles" class="state-block">
        <el-empty description="当前知识库下还没有已入库文件，暂时无法生成分布图。" />
      </div>

      <div v-else class="chart-layout">
        <div ref="chartRef" class="chart-canvas" />

        <div class="stats-list">
          <div
            v-for="item in rowsWithPercent"
            :key="item.id"
            class="stats-item"
          >
            <div class="stats-name">
              <span class="stats-dot" :style="{ background: item.color }" />
              <span>{{ item.name }}</span>
            </div>
            <div class="stats-meta">
              <strong class="stats-value">{{ item.value }}</strong>
              <span class="stats-percent">{{ item.percent }}%</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'

import { getFilesByKnowledgeBase } from '../../api/file'
import { getKnowledgeBases, type KnowledgeBase } from '../../api/kb'
import { useAuthStore } from '../../stores/auth'

interface ChartRow {
  id: number
  name: string
  value: number
  color: string
}

const authStore = useAuthStore()

const chartRef = ref<HTMLDivElement | null>(null)
const knowledgeBases = ref<KnowledgeBase[]>([])
const chartRows = ref<ChartRow[]>([])
const loading = ref(false)
const errorMessage = ref('')

let chartInstance: echarts.ECharts | null = null

const palette = ['#1f5f4a', '#d7a73f', '#4f8f80', '#d8754f', '#889f5d', '#4f6cd8', '#8b5fbf', '#d9507c']

const canViewKnowledgeBases = computed(() => authStore.hasPermission('kb.view'))
const canViewFileStats = computed(() => authStore.hasPermission('workspace.file'))
const totalFiles = computed(() => chartRows.value.reduce((sum, item) => sum + item.value, 0))
const sortedRows = computed(() => [...chartRows.value].sort((a, b) => b.value - a.value))
const rowsWithPercent = computed(() =>
  sortedRows.value.map(item => ({
    ...item,
    percent: totalFiles.value ? Number(((item.value / totalFiles.value) * 100).toFixed(1)) : 0,
  })),
)

const disposeChart = () => {
  chartInstance?.dispose()
  chartInstance = null
}

const renderChart = () => {
  if (!chartRef.value || !chartRows.value.length) {
    disposeChart()
    return
  }

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  chartInstance.setOption({
    tooltip: {
      trigger: 'item',
      formatter: '{b}<br/>文件数: {c}<br/>占比: {d}%',
    },
    legend: {
      show: false,
    },
    series: [
      {
        type: 'pie',
        radius: ['46%', '74%'],
        center: ['50%', '48%'],
        padAngle: 2,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#ffffff',
          borderWidth: 3,
        },
        label: {
          show: true,
          formatter: ({ name, value, percent }: { name: string; value: number; percent: number }) =>
            `${name}\n${value} 个 | ${percent}%`,
          color: '#26433a',
          fontSize: 12,
        },
        labelLine: {
          length: 12,
          length2: 10,
        },
        data: chartRows.value.map(item => ({
          name: item.name,
          value: item.value,
          itemStyle: { color: item.color },
        })),
      },
    ],
    graphic: [
      {
        type: 'text',
        left: 'center',
        top: '42%',
        style: {
          text: '文件总数',
          fill: '#6a7f77',
          fontSize: 13,
          fontWeight: 500,
        },
      },
      {
        type: 'text',
        left: 'center',
        top: '49%',
        style: {
          text: String(totalFiles.value),
          fill: '#18312a',
          fontSize: 28,
          fontWeight: 800,
        },
      },
    ],
  })
}

const handleResize = () => {
  chartInstance?.resize()
}

const loadOverview = async () => {
  if (!canViewKnowledgeBases.value) {
    knowledgeBases.value = []
    chartRows.value = []
    errorMessage.value = ''
    disposeChart()
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    const kbList = await getKnowledgeBases()
    knowledgeBases.value = kbList

    if (!canViewFileStats.value || !kbList.length) {
      chartRows.value = []
      return
    }

    const totals = await Promise.all(
      kbList.map(async (item, index) => {
        const data = await getFilesByKnowledgeBase(item.id, { page: 1, page_size: 1 })
        return {
          id: item.id,
          name: item.name,
          value: data.total,
          color: palette[index % palette.length],
        }
      }),
    )

    chartRows.value = totals
  } catch (error: any) {
    chartRows.value = []
    errorMessage.value = error?.message || '未能获取知识库统计信息'
  } finally {
    loading.value = false
    await nextTick()
    if (chartRows.value.length && totalFiles.value > 0) {
      renderChart()
    } else {
      disposeChart()
    }
  }
}

onMounted(async () => {
  await loadOverview()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  disposeChart()
})
</script>

<style scoped>
.overview-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.88fr) minmax(0, 1.12fr);
  gap: 20px;
  align-items: stretch;
}

.hero-card,
.insight-card {
  padding: 28px;
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 18px 40px rgba(32, 50, 45, 0.08);
}

.hero-card {
  min-height: 420px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  background:
    radial-gradient(circle at top right, rgba(242, 217, 141, 0.35), transparent 26%),
    linear-gradient(135deg, #14362d 0%, #234940 54%, #f0ead5 180%);
  color: #f7f7f1;
}

.eyebrow {
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #f2d98d;
}

h2 {
  margin: 16px 0 0;
  max-width: 560px;
  font-size: 38px;
  line-height: 1.15;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  margin-top: 14px;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 12px;
  color: rgba(247, 247, 241, 0.88);
  background: rgba(255, 255, 255, 0.12);
}

.hero-metrics {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
  margin-top: 30px;
}

.metric-card {
  display: grid;
  gap: 8px;
  padding: 22px 20px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.metric-label {
  font-size: 13px;
  color: rgba(247, 247, 241, 0.74);
}

.metric-value {
  font-size: 34px;
  line-height: 1;
  font-weight: 800;
  color: #ffffff;
}

.metric-hint {
  font-size: 12px;
  color: rgba(247, 247, 241, 0.66);
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}

.card-title {
  font-size: 22px;
  font-weight: 800;
  color: #18312a;
}

.card-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: #6b7c76;
}

.state-block {
  min-height: 360px;
  display: grid;
  place-items: center;
}

.chart-layout {
  display: grid;
  grid-template-columns: minmax(300px, 1.1fr) minmax(260px, 0.9fr);
  gap: 20px;
  align-items: center;
}

.chart-canvas {
  width: 100%;
  min-height: 380px;
  height: 100%;
}

.stats-list {
  display: grid;
  gap: 10px;
}

.stats-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid #e5ece6;
  border-radius: 16px;
  background: #f8faf7;
}

.stats-name {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  color: #27443b;
  font-weight: 600;
}

.stats-name span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stats-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex: 0 0 auto;
}

.stats-value {
  font-size: 18px;
  color: #18312a;
}

.stats-meta {
  display: grid;
  justify-items: end;
  gap: 2px;
}

.stats-percent {
  font-size: 12px;
  color: #6b7c76;
}

@media (max-width: 1080px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }

  h2 {
    font-size: 30px;
  }

  .chart-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .chart-canvas {
    height: 320px;
    min-height: 320px;
  }

  .card-header {
    flex-direction: column;
  }
}
</style>
