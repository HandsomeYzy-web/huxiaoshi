<template>
  <div class="chat-container">
    <div class="header">
      <h2>🤖 智能问答系统</h2>
    </div>

    <div class="message-list">
      <div v-for="(msg, index) in messages" :key="index" :class="['message', msg.role]">
        <div class="avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
        <div class="content">{{ msg.content }}</div>
      </div>
    </div>

    <div class="input-area">
      <input
        v-model="inputQuery"
        @keyup.enter="sendMessage"
        placeholder="请输入您的问题..."
        :disabled="isLoading"
      />
      <button @click="sendMessage" :disabled="isLoading || !inputQuery.trim()">发送</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

// 对话记录数组
const messages = ref<{role: 'user' | 'ai', content: string}[]>([
  { role: 'ai', content: '您好！我是企业级智能助手，有什么我可以帮您的吗？' }
])
const inputQuery = ref('')
const isLoading = ref(false)

const sendMessage = async () => {
  if (!inputQuery.value.trim() || isLoading.value) return

  const query = inputQuery.value
  inputQuery.value = ''

  // 1. 把用户的问题加入列表
  messages.value.push({ role: 'user', content: query })
  // 2. 先给 AI 建一个空的回复气泡
  messages.value.push({ role: 'ai', content: '' })
  isLoading.value = true

  try {
    // 3. 使用 Fetch 发起流式请求 (注意这里使用的是原生的 fetch 处理流)
    const response = await fetch('http://127.0.0.1:8000/api/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query })
    })

    if (!response.body) throw new Error('ReadableStream not supported in this browser.')

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let done = false

    // 4. 循环读取后端推过来的流式数据片段
    while (!done) {
      const { value, done: readerDone } = await reader.read()
      done = readerDone
      if (value) {
        const chunk = decoder.decode(value, { stream: true })
        // 把新接收到的字拼接到最后一个 AI 气泡的内容里
        messages.value[messages.value.length - 1].content += chunk
      }
    }
  } catch (error) {
    console.error('对话请求失败:', error)
    messages.value[messages.value.length - 1].content = '对不起，网络连接出错，请稍后再试。'
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
/* 简单的聊天界面样式 */
.chat-container { display: flex; flex-direction: column; height: 100vh; max-width: 800px; margin: 0 auto; border: 1px solid #ccc; }
.header { padding: 15px; background: #f5f5f5; text-align: center; border-bottom: 1px solid #ddd; }
.message-list { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
.message { display: flex; gap: 10px; max-width: 80%; }
.message.user { align-self: flex-end; flex-direction: row-reverse; }
.avatar { font-size: 24px; }
.content { padding: 10px 15px; border-radius: 8px; background: #eee; line-height: 1.5; white-space: pre-wrap; }
.message.user .content { background: #007bff; color: white; }
.input-area { padding: 15px; border-top: 1px solid #ddd; display: flex; gap: 10px; }
input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 4px; outline: none; }
button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
button:disabled { background: #ccc; cursor: not-allowed; }
</style>