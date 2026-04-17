import { ref } from 'vue'

/**
 * 打字机流：固定速度逐字输出，done 后等队列自然播完再回调。
 * 不做自适应加速——即使 chunk 一次性到达也保持打字效果。
 */
export const useTypewriterStream = (interval = 12, charsPerTick = 3) => {
  const text = ref('')
  const queue: string[] = []
  let timer: number | null = null
  let drainCallback: (() => void) | null = null

  const stop = () => {
    if (timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  const tick = () => {
    if (!queue.length) {
      stop()
      if (drainCallback) {
        const cb = drainCallback
        drainCallback = null
        cb()
      }
      return
    }
    text.value += queue.splice(0, charsPerTick).join('')
  }

  const start = () => {
    if (timer !== null) return
    timer = window.setInterval(tick, interval)
  }

  const enqueue = (chunk: string) => {
    if (!chunk) return
    queue.push(...Array.from(chunk))
    start()
  }

  /** 等队列自然播放完毕后执行回调（不会强制清空） */
  const onDrain = (cb: () => void) => {
    if (!queue.length && timer === null) {
      cb()
    } else {
      drainCallback = cb
    }
  }

  const flush = () => {
    stop()
    drainCallback = null
    if (queue.length) {
      text.value += queue.join('')
      queue.length = 0
    }
  }

  const reset = () => {
    stop()
    drainCallback = null
    queue.length = 0
    text.value = ''
  }

  return {
    text,
    enqueue,
    flush,
    reset,
    onDrain,
  }
}
