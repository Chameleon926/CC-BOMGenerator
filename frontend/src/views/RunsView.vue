<script setup>
// 生成任务列表（第二级）。设计见 §5.2 + §13.1/§13.2。
// el-progress(progress%) + el-tag(status) + 停止(popconfirm)/详情；block_code 读 route.query；
// 任一 running 时轮询(onUnmounted 清)；合并 usePendingRuns 单例（刚创建未落库）。
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { generateApi } from '../api/generate'
import { clausesApi } from '../api/clauses'
import { usePendingRuns, clearPendingRun } from '../composables/useRunPoll'

const route = useRoute()
const router = useRouter()
const block_code = computed(() => route.query.block_code || '')
const runs = ref([])
const clauseNames = ref({})
const loading = ref(false)
let pollTimer = null

const merged = computed(() => {
  const pending = usePendingRuns().value.filter(p => !block_code.value || p.block_code === block_code.value)
  const existIds = new Set(runs.value.map(r => r.run_id))
  const pendingRows = pending.filter(p => !existIds.has(p.run_id)).map(p => ({
    run_id: p.run_id, block_code: p.block_code, status: 'running', progress: 0, done_nodes: 0, total_steps: 7, started_at: null,
  }))
  return [...pendingRows, ...runs.value]
})
const anyRunning = computed(() => merged.value.some(r => r.status === 'running'))

const refresh = async () => {
  loading.value = true
  try {
    const data = await generateApi.list(block_code.value)
    runs.value = data.runs || []
    const ids = new Set(runs.value.map(r => r.run_id))
    usePendingRuns().value.filter(p => ids.has(p.run_id)).forEach(p => clearPendingRun(p.run_id))
  } catch {} finally { loading.value = false }
}

const startPoll = () => {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    if (!anyRunning.value) { clearInterval(pollTimer); pollTimer = null; return }
    try { runs.value = (await generateApi.list(block_code.value, { skipToast: true })).runs || [] } catch {}
  }, 2000)
}

onMounted(async () => {
  try { const c = await clausesApi.list(); clauseNames.value = Object.fromEntries((c.clauses || []).map(x => [x.block_code, x.block_name])) } catch {}
  await refresh()
  if (anyRunning.value) startPoll()
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

const stop = async (run_id) => {
  try { await generateApi.stop(run_id); ElMessage.success('已停止（当前节点跑完后生效）'); await refresh() } catch {}
}
const tagType = s => ({ queued: 'info', running: 'warning', success: 'success', fail: 'danger', cancelled: 'danger' }[s] || 'info')
const tagText = s => ({ queued: '排队中', running: '执行中', success: '成功', fail: '失败', cancelled: '已取消' }[s] || s)
const clauseName = bc => clauseNames.value[bc] || bc
</script>

<template>
  <div class="p-4 h-full flex flex-col gap-3 overflow-hidden">
    <el-card class="flex-1 overflow-hidden" shadow="never" body-class="p-0" v-loading="loading">
      <el-table :data="merged" height="100%" empty-text="暂无生成任务">
        <el-table-column label="条款" min-width="150">
          <template #default="{ row }">
            <span class="font-medium text-slate-700">{{ clauseName(row.block_code) }}</span>
            <div class="text-xs text-slate-400">{{ row.block_code }}</div>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="190">
          <template #default="{ row }">
            <el-progress :percentage="row.progress || 0" :text-inside="true" :stroke-width="16"
              :status="row.status === 'success' ? 'success' : (row.status === 'fail' || row.status === 'cancelled') ? 'exception' : ''" />
            <div class="text-xs text-slate-400">{{ row.done_nodes || 0 }}/{{ row.total_steps || 7 }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }"><el-tag :type="tagType(row.status)" size="small">{{ tagText(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ row.started_at ? new Date(row.started_at).toLocaleString() : '—' }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="80" align="center">
          <template #default="{ row }">{{ row.duration_ms ? Math.round(row.duration_ms / 1000) + 's' : '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="router.push(`/runs/${row.run_id}`)">详情</el-button>
            <el-popconfirm v-if="row.status === 'running'" title="确认停止？当前节点跑完后生效。" @confirm="stop(row.run_id)">
              <template #reference><el-button type="danger" size="small" plain>停止</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
