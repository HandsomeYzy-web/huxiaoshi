<template>
  <div class="overview-grid">
    <section class="overview-card intro-card">
      <header class="section-head">
        <div class="head-icon">
          <el-icon><Collection /></el-icon>
        </div>
        <div>
          <h2 class="section-title">学院知识库概况</h2>
          <p class="section-subtitle">汇聚 · 沉淀 · 共享 · 创新</p>
        </div>
      </header>

      <p class="intro-text">实时掌握知识库建设与资源利用情况</p>

      <div class="intro-metrics">
        <article class="metric-card">
          <div class="metric-icon">
            <el-icon><Reading /></el-icon>
          </div>
          <div class="metric-main">
            <span class="metric-label">知识库总数</span>
            <strong class="metric-value">{{ canViewKnowledgeBases ? knowledgeBases.length : '--' }}</strong>
            <span class="metric-tip">{{ canViewKnowledgeBases ? '当前账号可访问' : '缺少知识库查看权限' }}</span>
          </div>
        </article>

        <article class="metric-card">
          <div class="metric-icon">
            <el-icon><Document /></el-icon>
          </div>
          <div class="metric-main">
            <span class="metric-label">文件总数</span>
            <strong class="metric-value">{{ canViewFileStats ? formattedTotalFiles : '--' }}</strong>
            <span class="metric-tip">{{ canViewFileStats ? '已按知识库汇总' : '缺少文件统计权限' }}</span>
          </div>
        </article>
      </div>

      <div class="update-row">数据更新时间：{{ updateTimeLabel }}</div>
    </section>

    <section class="overview-card insight-card">
      <header class="section-head chart-head">
        <div>
          <h2 class="section-title">文件资源分布</h2>
          <p class="section-subtitle">按知识库统计当前文件数量</p>
        </div>
        <div class="scope-chip">全部知识库</div>
      </header>

      <div v-if="!canViewKnowledgeBases" class="state-block">
        <el-empty description="当前账号没有知识库查看权限，无法展示概览数据。" />
      </div>

      <div v-else-if="!canViewFileStats" class="state-block">
        <el-empty description="当前账号没有文件统计权限，无法展示文件分布。" />
      </div>

      <div v-else-if="loading" class="state-block">
        <el-skeleton animated>
          <template #template>
            <el-skeleton-item variant="h3" style="width: 42%; margin-bottom: 18px;" />
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
        <div class="chart-shell">
          <div ref="chartRef" class="chart-canvas" />
          <div class="chart-center-copy" :style="{ left: pieCenter[0], top: pieCenter[1] }">
            <strong class="chart-center-value">{{ formattedTotalFiles }}</strong>
            <span class="chart-center-text">{{ donutCenterLabel }}</span>
          </div>
        </div>

        <div class="stats-list">
          <article v-for="item in rowsWithPercent" :key="item.id" class="stats-item">
            <div class="stats-name">
              <span class="stats-dot" :style="{ background: item.color }" />
              <span>{{ item.name }}</span>
            </div>
            <strong class="stats-value">{{ item.value.toLocaleString('zh-CN') }}</strong>
          </article>
        </div>
      </div>

      <div class="insight-quote">知识如海，求索不止。持续建设高质量知识库，助力教学科研与学术创新。</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Collection, Document, Reading } from '@element-plus/icons-vue'
import * as echarts from 'echarts'

import { getFilesByKnowledgeBase } from '../../api/file'
import { getKnowledgeBases, type KnowledgeBase } from '../../api/kb'

interface ChartRow {
  id: number
  name: string
  value: number
  color: string
}

const chartRef = ref<HTMLDivElement | null>(null)
const knowledgeBases = ref<KnowledgeBase[]>([])
const chartRows = ref<ChartRow[]>([])
const loading = ref(false)
const errorMessage = ref('')
const updateTime = ref('')

let chartInstance: echarts.ECharts | null = null

const palette = ['#A0292E', '#2E655A', '#C7A57C', '#D7A66C', '#5A789B', '#9CA6AD', '#B67752', '#6E8F74']
const pieCenter = ['38%', '50%'] as const
const donutCenterLabel = '\u6587\u4ef6\u603b\u6570'

const canViewKnowledgeBases = computed(() => true)
const canViewFileStats = computed(() => true)
const totalFiles = computed(() => chartRows.value.reduce((sum, item) => sum + item.value, 0))
const formattedTotalFiles = computed(() => totalFiles.value.toLocaleString('zh-CN'))
const sortedRows = computed(() => [...chartRows.value].sort((a, b) => b.value - a.value))
const rowsWithPercent = computed(() =>
  sortedRows.value.map(item => ({
    ...item,
    percent: totalFiles.value ? Number(((item.value / totalFiles.value) * 100).toFixed(1)) : 0,
  })),
)
const updateTimeLabel = computed(() => updateTime.value || '--')

function formatDateTime(date: Date) {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}:${pad(date.getSeconds())}`
}

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
        radius: ['52%', '76%'],
        center: pieCenter,
        itemStyle: {
          borderRadius: 5,
          borderColor: '#f7f2eb',
          borderWidth: 3,
        },
        label: {
          show: false,
        },
        data: chartRows.value.map(item => ({
          name: item.name,
          value: item.value,
          itemStyle: { color: item.color },
        })),
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
    updateTime.value = formatDateTime(new Date())
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
      updateTime.value = formatDateTime(new Date())
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
    updateTime.value = formatDateTime(new Date())
  } catch (error: any) {
    chartRows.value = []
    updateTime.value = formatDateTime(new Date())
    errorMessage.value = error?.message || '未能获取知识库统计信息。'
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
  grid-template-columns: minmax(340px, 0.88fr) minmax(0, 1.12fr);
  gap: 20px;
}

.overview-card {
  border-radius: 26px;
  border: 1px solid #e5d5c3;
  background:
    linear-gradient(180deg, rgba(255, 253, 250, 0.98) 0%, rgba(252, 246, 239, 0.95) 100%),
    repeating-linear-gradient(
      0deg,
      rgba(193, 149, 117, 0.04) 0 2px,
      rgba(193, 149, 117, 0) 2px 4px
    );
  box-shadow: 0 16px 30px rgba(124, 84, 58, 0.08);
}

.intro-card {
  padding: 24px 24px 20px;
}

.section-head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.head-icon {
  width: 46px;
  height: 46px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  font-size: 20px;
  color: #7f1f20;
  border: 1px solid #d8bda5;
  background: radial-gradient(circle at 28% 25%, #fffaf2 0%, #f2e6d6 100%);
}

.section-title {
  margin: 0;
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: 24px;
  line-height: 1.1;
  color: #4e2f26;
}

.section-subtitle {
  margin: 6px 0 0;
  font-size: 14px;
  color: #8c6d59;
}

.intro-text {
  margin: 14px 0 16px;
  font-size: 14px;
  color: #6d5d52;
}

.intro-metrics {
  display: grid;
  gap: 14px;
}

.metric-card {
  display: grid;
  grid-template-columns: 60px 1fr;
  gap: 14px;
  align-items: center;
  padding: 14px 14px;
  border: 1px solid #e6d4bf;
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94) 0%, rgba(253, 248, 241, 0.94) 100%),
    radial-gradient(circle at 86% 8%, rgba(177, 125, 93, 0.12), transparent 38%);
}

.metric-icon {
  width: 50px;
  height: 50px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  font-size: 20px;
  color: #8b3f2f;
  border: 1px solid #d6b599;
  background: linear-gradient(180deg, #fffdf8 0%, #f7eddf 100%);
}

.metric-main {
  display: grid;
  gap: 4px;
}

.metric-label {
  font-size: 16px;
  color: #6b594c;
}

.metric-value {
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: 46px;
  line-height: 1;
  color: #7f1f20;
}

.metric-tip {
  font-size: 13px;
  color: #8b7666;
}

.update-row {
  margin-top: 14px;
  font-size: 13px;
  color: #7d6c5f;
}

.insight-card {
  display: flex;
  flex-direction: column;
  padding: 24px 24px 20px;
}

.chart-head {
  justify-content: space-between;
  align-items: flex-start;
}

.scope-chip {
  padding: 6px 12px;
  border-radius: 10px;
  border: 1px solid #e0cfbc;
  font-size: 13px;
  color: #6e5d50;
  background: #fffbf6;
}

.state-block {
  min-height: 330px;
  display: grid;
  place-items: center;
}

.chart-layout {
  display: grid;
  grid-template-columns: minmax(300px, 1fr) minmax(240px, 0.82fr);
  gap: 16px;
  align-items: center;
}

.chart-shell {
  position: relative;
}

.chart-canvas {
  width: 100%;
  min-height: 340px;
}

.chart-center-copy {
  position: absolute;
  transform: translate(-50%, -50%);
  display: grid;
  justify-items: center;
  line-height: 1;
  pointer-events: none;
}

.chart-center-value {
  font-size: 42px;
  font-weight: 700;
  color: #2a231e;
}

.chart-center-text {
  margin-top: 6px;
  font-size: 18px;
  color: #7e695a;
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
  padding: 10px 12px;
}

.stats-name {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  color: #4f4035;
  font-size: 14px;
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
  font-size: 24px;
  color: #35271f;
}

.insight-quote {
  margin-top: auto;
  border: 1px solid #e6d3be;
  border-radius: 14px;
  padding: 12px 14px;
  font-size: 14px;
  color: #6e5c50;
  background: linear-gradient(180deg, rgba(255, 252, 247, 0.95) 0%, rgba(252, 245, 236, 0.95) 100%);
}

@media (max-width: 1400px) {
  .overview-grid {
    gap: 16px;
  }
}

@media (max-width: 1080px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }

  .chart-layout {
    grid-template-columns: 1fr;
  }

  .chart-canvas {
    min-height: 300px;
  }
}

@media (max-width: 720px) {
  .intro-card,
  .insight-card {
    padding: 18px;
  }

  .section-head {
    gap: 10px;
  }

  .head-icon {
    width: 40px;
    height: 40px;
    font-size: 18px;
  }

  .section-title {
    font-size: 20px;
  }

  .section-subtitle,
  .intro-text {
    font-size: 13px;
  }

  .metric-card {
    grid-template-columns: 52px 1fr;
    gap: 12px;
    padding: 14px;
  }

  .metric-icon {
    width: 46px;
    height: 46px;
    font-size: 18px;
  }

  .metric-label,
  .metric-tip,
  .update-row {
    font-size: 12px;
  }

  .metric-value {
    font-size: 34px;
  }

  .stats-value {
    font-size: 22px;
  }

  .scope-chip {
    margin-top: 10px;
  }

  .chart-head {
    flex-direction: column;
  }
}
</style>
