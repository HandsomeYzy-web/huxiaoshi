<template>
  <el-a-conversations class="session-sidebar">
    <template #header>
      <div class="session-header">
        <h1 class="title">聊天记录</h1>
        <el-button type="primary" size="small" @click="$emit('create')">
          + 新建对话
        </el-button>
      </div>
    </template>

    <template #scroll>
      <div class="session-list">
        <button
          v-for="session in sessions"
          :key="session.id"
          type="button"
          :class="['session-item', { active: session.id === activeSessionId }]"
          @click="$emit('select', session.id)"
        >
          <div class="session-info">
            <div class="session-title">{{ session.title }}</div>
            <div class="session-time">{{ formatTime(session.updated_at) }}</div>
          </div>
          <div class="session-actions" @click.stop>
            <el-tooltip content="重命名" placement="top">
              <el-button link size="small" class="action-btn" @click="$emit('rename', session)">重命名</el-button>
            </el-tooltip>
            <el-tooltip content="删除" placement="top">
              <el-button link size="small" class="action-btn action-delete" @click="$emit('delete', session.id)">删除</el-button>
            </el-tooltip>
          </div>
        </button>
      </div>
    </template>
  </el-a-conversations>
</template>

<script setup lang="ts">
import type { ChatSessionSummary } from '../../api/chat'

defineProps<{
  sessions: ChatSessionSummary[]
  activeSessionId: number | null
}>()

defineEmits<{
  create: []
  select: [sessionId: number]
  rename: [session: ChatSessionSummary]
  delete: [sessionId: number]
}>()

const formatTime = (value: string | Date): string => {
  const date = new Date(value)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()

  if (isToday) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.session-sidebar {
  width: 280px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.04);
}

.session-sidebar :deep(.el-a-conversations-header) {
  padding: 0;
}

.session-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #e4e7ed;
}

.title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
}

.session-item {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #303133;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.session-item:hover {
  background: #f5f7fa;
}

.session-item.active {
  background: #ecf5ff;
  font-weight: 500;
  color: #409eff;
}

.session-title {
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-time {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.session-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
</style>
