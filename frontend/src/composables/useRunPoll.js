// 运行轮询 composable —— 跨页共享 + 单 run 状态轮询。
// 设计见 docs/frontend-design.md §13.1（跨页状态约定）、§6.3（轮询契约）。
//
// 关键：onUnmounted 必清 pollTimer（参考旧 GeneratePanel.vue:81 的正确清理，
// App.vue 旧版漏了这点 → §9.1#2）。
import { ref, onUnmounted } from 'vue'
import { generateApi } from '../api/generate'

// ---- 模块级单例：刚创建、尚未落库 GET /runs 的 run（避免条款库→任务列表竞态）----
const pendingRuns = ref([]) // [{ run_id, block_code, clause }]
export function addPendingRun(run) { pendingRuns.value.push(run) }
export function clearPendingRun(run_id) {
  pendingRuns.value = pendingRuns.value.filter(r => r.run_id !== run_id)
}
export function usePendingRuns() { return pendingRuns }

// 终态集合（命中即停轮询）
const TERMINAL = ['success', 'fail', 'cancelled']

/**
 * 单 run 轮询。调用方在 onUnmounted 调 stop()。
 * @param {(payload)=>void} onUpdate 每次状态变更回调：{ phase, statusData?, result?, error? }
 *   phase: 'running' | 'done' | 'error'
 */
export function useRunPoll(onUpdate, { interval = 2000, timeoutMs = 5 * 60 * 1000, maxFails = 5 } = {}) {
  let timer = null
  let fails = 0
  let startedAt = 0

  const stop = () => { if (timer) { clearInterval(timer); timer = null } }

  const start = (run_id) => {
    stop()
    fails = 0
    startedAt = Date.now()
    onUpdate({ phase: 'running' })
    timer = setInterval(async () => {
      if (Date.now() - startedAt > timeoutMs) { stop(); onUpdate({ phase: 'error', error: '超时' }); return }
      try {
        const data = await generateApi.status(run_id, { skipToast: true })
        fails = 0
        onUpdate({ phase: 'running', statusData: data })
        if (TERMINAL.includes(data.status)) {
          stop()
          // 放宽：任何终态都拉 result（失败/取消也有部分结果：keywords/examples/bom快照）
          try {
            const result = await generateApi.result(run_id)
            onUpdate({
              phase: data.status === 'success' ? 'done' : 'error',
              statusData: data,
              result,
              error: data.status !== 'success' ? (data.error_message || `任务${data.status}`) : undefined,
            })
          } catch {
            onUpdate({ phase: 'error', statusData: data, error: data.error_message || `任务${data.status}` })
          }
        }
      } catch {
        if (++fails >= maxFails) { stop(); onUpdate({ phase: 'error', error: '连接中断' }) }
      }
    }, interval)
  }

  onUnmounted(stop) // 组件卸载必清（防泄漏 + 防卸载后继续 setState）

  return { start, stop }
}
