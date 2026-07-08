<script setup>
// 任务详情（第三级）。设计见 §5.3 + §13.2。
// 任务信息 + RunProgress(节点) + 选取数据(selected_examples) + BomPreview(折叠) + 提示词复制。
// 失败/取消也拉 result（B 方案放宽，能拿到 selected_examples + 部分快照）。轮询 useRunPoll。
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { generateApi } from '../api/generate'
import { clausesApi } from '../api/clauses'
import { useRunPoll } from '../composables/useRunPoll'
import RunProgress from '../components/RunProgress.vue'
import BomPreview from '../components/BomPreview.vue'

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()

const statusData = ref(null)
const result = ref(null)
const phase = ref('running')
const errorMsg = ref('')
const clauseName = ref('')

const isTerminal = computed(() => ['success', 'fail', 'cancelled'].includes(statusData.value?.status))

const { start } = useRunPoll(async (payload) => {
  if (payload.statusData) statusData.value = payload.statusData
  if (payload.result) result.value = payload.result
  phase.value = payload.phase
  if (payload.error) errorMsg.value = payload.error
})

onMounted(async () => {
  try {
    const data = await generateApi.status(props.id)
    statusData.value = data
    if (data.status === 'success') {
      try { result.value = await generateApi.result(props.id) } catch {}
      phase.value = 'done'
    } else if (['fail', 'cancelled'].includes(data.status)) {
      try { result.value = await generateApi.result(props.id) } catch {}
      phase.value = 'error'
      errorMsg.value = data.error_message || `任务${data.status}`
    } else {
      start(props.id)
    }
    if (data.block_code) {
      try { const c = await clausesApi.list(); clauseName.value = (c.clauses || []).find(x => x.block_code === data.block_code)?.block_name || data.block_code } catch {}
    }
  } catch {
    phase.value = 'error'
    errorMsg.value = '任务不存在或加载失败'
  }
})

const copyPrompt = async () => {
  const text = result.value?.full_prompt?.prompt_text || ''
  if (!text) return
  try { await navigator.clipboard.writeText(text); ElMessage.success('提示词已复制') }
  catch { ElMessage.error('复制失败') }
}
const tagType = s => ({ success: 'success', fail: 'danger', cancelled: 'danger', running: 'warning', queued: 'info' }[s] || 'info')
</script>

<template>
  <div class="p-4 space-y-3 max-w-5xl">
    <el-button text icon="ArrowLeft" @click="router.push('/runs')">返回任务列表</el-button>

    <el-card v-if="statusData" shadow="never">
      <div class="flex items-center gap-4 text-sm flex-wrap">
        <span class="text-base font-bold text-slate-800">{{ clauseName || statusData.block_code }}</span>
        <el-tag :type="tagType(statusData.status)" size="small">{{ statusData.status }}</el-tag>
        <span class="text-slate-400">run_id: {{ id }}</span>
        <span class="text-slate-400" v-if="statusData.started_at">{{ new Date(statusData.started_at).toLocaleString() }}</span>
        <span class="text-slate-400" v-if="statusData.duration_ms">· {{ Math.round(statusData.duration_ms / 1000) }}s</span>
      </div>
    </el-card>

    <el-alert v-if="errorMsg" :title="errorMsg" type="error" :closable="false" show-icon />

    <el-card v-if="statusData" shadow="never">
      <template #header><span class="text-sm font-semibold text-slate-600">执行进度</span></template>
      <RunProgress :nodes="statusData.nodes || []" :running="phase === 'running'" />
    </el-card>

    <el-card v-if="result?.selected_examples?.length" shadow="never">
      <template #header><span class="text-sm font-semibold text-slate-600">选取数据（聚类选的代表正例）</span></template>
      <el-table :data="result.selected_examples" size="small">
        <el-table-column label="文档ID" width="320">
          <template #default="{ row }"><span class="font-mono text-xs text-slate-500">{{ row.doc_id }}</span></template>
        </el-table-column>
        <el-table-column label="期望结果">
          <template #default="{ row }"><span class="text-sm text-slate-600">{{ row.expected_value }}</span></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="result?.bom" shadow="never">
      <template #header>
        <span class="text-sm font-semibold text-slate-600">BOM 结果 <span class="text-xs text-slate-400 ml-1" v-if="result.bom.version">v{{ result.bom.version }}</span></span>
      </template>
      <BomPreview :bom="result.bom" />
    </el-card>

    <el-card v-if="result?.full_prompt?.prompt_text" shadow="never">
      <template #header>
        <div class="flex items-center justify-between">
          <span class="text-sm font-semibold text-slate-600">完整提示词</span>
          <el-button type="primary" size="small" plain icon="CopyDocument" @click="copyPrompt">复制</el-button>
        </div>
      </template>
      <pre class="text-xs leading-relaxed overflow-auto max-h-96 p-3 rounded font-mono" style="background:#0f172a;color:#e2e8f0">{{ result.full_prompt.prompt_text }}</pre>
    </el-card>
  </div>
</template>
