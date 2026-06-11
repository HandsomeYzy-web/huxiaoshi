<template>
  <el-a-conversations class="session-sidebar">
    <template #header>
      <div class="session-header">
        <div class="session-heading">
          <span class="heading-mark">识</span>
          <div class="heading-text">
            <h1 class="title">对话记录</h1>
            <p class="subtitle">湖小识 · 智能问答</p>
          </div>
        </div>
        <el-button
          class="new-chat-btn"
          size="small"
          :loading="creating"
          :disabled="creating"
          @click="$emit('create')"
        >
          <el-icon class="new-chat-icon"><Plus /></el-icon>
          <span>新建对话</span>
        </el-button>
      </div>
    </template>

    <template #scroll>
      <div v-if="!sessions.length" class="session-empty">
        <el-icon class="session-empty-icon"><ChatLineRound /></el-icon>
        <p>还没有对话，点击上方新建开始吧</p>
      </div>

      <div v-else class="session-list">
        <button
          v-for="session in sessions"
          :key="session.id"
          type="button"
          :class="['session-item', { active: session.id === activeSessionId }]"
          @click="$emit('select', session.id)"
        >
          <span class="session-rail" aria-hidden="true" />
          <el-icon class="session-bubble-icon"><ChatDotRound /></el-icon>
          <div class="session-info">
            <div class="session-title">{{ session.title }}</div>
            <div class="session-time">{{ formatTime(session.updated_at) }}</div>
          </div>
          <div class="session-actions" @click.stop>
            <el-tooltip content="重命名" placement="top">
              <button type="button" class="action-btn" @click="$emit('rename', session)">
                <el-icon><EditPen /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip content="删除" placement="top">
              <button type="button" class="action-btn action-delete" @click="$emit('delete', session.id)">
                <el-icon><Delete /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </button>
      </div>
    </template>
  </el-a-conversations>
</template>

<script setup lang="ts">
import { ChatDotRound, ChatLineRound, Delete, EditPen, Plus } from '@element-plus/icons-vue'

import type { ChatSessionSummary } from '../../api/chat'

defineProps<{
  sessions: ChatSessionSummary[]
  activeSessionId: number | null
  creating?: boolean
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
  width: 288px;
  background:
    linear-gradient(180deg, rgba(255, 252, 247, 0.96) 0%, rgba(250, 243, 233, 0.96) 100%),
    radial-gradient(circle at 12% 4%, rgba(177, 125, 93, 0.1), transparent 42%);
  border-right: 1px solid #e9dbc8;
  box-shadow: 2px 0 14px rgba(83, 38, 18, 0.06);
}

.session-sidebar :deep(.el-a-conversations-header) {
  padding: 0;
}

.session-header {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px 18px 16px;
  border-bottom: 1px solid #ece0cf;
}

.session-heading {
  display: flex;
  align-items: center;
  gap: 12px;
}

.heading-mark {
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 13px;
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: 22px;
  font-weight: 700;
  color: #fbe9d2;
  background: linear-gradient(150deg, #9f2f2f 0%, #7a1c20 100%);
  box-shadow: 0 8px 18px rgba(122, 28, 32, 0.28);
}

.heading-text {
  min-width: 0;
}

.title {
  margin: 0;
  font-family: 'Noto Serif SC', 'STSong', 'Songti SC', serif;
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #4e2f26;
}

.subtitle {
  margin: 3px 0 0;
  font-size: 12px;
  color: #9a8470;
}

.new-chat-btn {
  width: 100%;
  height: 40px;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #fbe9d2;
  background: linear-gradient(95deg, #9f2f2f 0%, #7a1c20 100%);
  box-shadow: 0 8px 16px rgba(122, 28, 32, 0.22);
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
}

.new-chat-btn:hover {
  filter: brightness(1.06);
  box-shadow: 0 10px 20px rgba(122, 28, 32, 0.3);
  transform: translateY(-1px);
}

.new-chat-btn:active {
  transform: translateY(0);
}

.new-chat-icon {
  margin-right: 4px;
}

.session-empty {
  display: grid;
  place-items: center;
  gap: 10px;
  padding: 48px 24px;
  text-align: center;
  color: #a3917f;
}

.session-empty-icon {
  font-size: 30px;
  color: #cbae8f;
}

.session-empty p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 12px;
}

.session-item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 12px 12px 12px 14px;
  border: 1px solid transparent;
  border-radius: 14px;
  background: transparent;
  color: #4e3a30;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  transition: background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.session-rail {
  position: absolute;
  left: 0;
  top: 50%;
  width: 3px;
  height: 0;
  border-radius: 0 3px 3px 0;
  background: linear-gradient(180deg, #c98a3a 0%, #9f2f2f 100%);
  transform: translateY(-50%);
  transition: height 0.2s ease;
}

.session-bubble-icon {
  margin-top: 2px;
  font-size: 16px;
  color: #b08763;
  flex: 0 0 auto;
  transition: color 0.2s ease;
}

.session-item:hover {
  background: rgba(255, 244, 230, 0.85);
  border-color: #ecd9c2;
}

.session-item.active {
  background:
    linear-gradient(180deg, rgba(255, 247, 237, 0.96) 0%, rgba(252, 238, 222, 0.96) 100%);
  border-color: #e4c39c;
  box-shadow: 0 6px 16px rgba(122, 28, 32, 0.1);
}

.session-item.active .session-rail {
  height: calc(100% - 18px);
}

.session-item.active .session-title {
  color: #7a1c20;
  font-weight: 600;
}

.session-item.active .session-bubble-icon {
  color: #9f2f2f;
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-title {
  font-size: 14px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-time {
  font-size: 12px;
  color: #a3917f;
  margin-top: 4px;
}

.session-actions {
  display: flex;
  gap: 4px;
  flex: 0 0 auto;
  opacity: 0;
  transform: translateX(4px);
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.session-item:hover .session-actions,
.session-item.active .session-actions {
  opacity: 1;
  transform: translateX(0);
}

.action-btn {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: rgba(122, 28, 32, 0.06);
  color: #8a6a52;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.action-btn:hover {
  background: rgba(122, 28, 32, 0.14);
  color: #7a1c20;
}

.action-delete:hover {
  background: rgba(196, 60, 56, 0.16);
  color: #c0392b;
}
</style>
