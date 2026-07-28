<script setup>
// 任务详情（第三级）。设计见 §5.3 + §13.2。
// 任务信息 + RunProgress(节点) + 选取数据(selected_examples) + BomPreview(折叠) + 提示词复制。
// 失败/取消也拉 result（B 方案放宽，能拿到 selected_examples + 部分快照）。轮询 useRunPoll。
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { generateApi } from '../api/generate'
import { clausesApi } from '../api/clauses'
import { useRunPoll, addPendingRun } from '../composables/useRunPoll'
import { formatDuration } from '../constants/skill'
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

// 重试失败任务（新建一个 run）
const retryGenerate = async () => {
  const bc = statusData.value?.block_code
  if (!bc) return
  try {
    const data = await generateApi.start({ block_code: bc })
    addPendingRun({ run_id: data.run_id, block_code: bc })
    router.push(`/runs/${data.run_id}`)
    ElMessage.success('已重新生成')
  } catch {}
}

// 典型正例编辑（TE-4：改 value/reason → 重 assemble 提示词）
const teDialog = ref(false)
const teForm = ref({ index: -1, value: '', reason: '' })
const openTeEdit = (i) => {
  const te = result.value?.bom?.typical_examples?.[i]
  if (!te) return
  teForm.value = { index: i, value: te.value || '', reason: te.reason || '' }
  teDialog.value = true
}
const _putTypical = async (tes) => {
  const bc = statusData.value?.block_code
  if (!bc) { ElMessage.error('缺少 block_code'); throw new Error('no block_code') }
  await clausesApi.updateTypicalExamples(bc, tes)
}
const saveTe = async () => {
  const tes = [...(result.value?.bom?.typical_examples || [])]
  if (teForm.value.index >= 0) tes[teForm.value.index] = { value: teForm.value.value, reason: teForm.value.reason }
  try {
    await _putTypical(tes)
    ElMessage.success('已保存，提示词已重 assemble')
    teDialog.value = false
    result.value = await generateApi.result(props.id)  // 重取（bom+提示词已更新）
  } catch {}
}
const deleteTe = async (i) => {
  const tes = (result.value?.bom?.typical_examples || []).filter((_, idx) => idx !== i)
  try {
    await _putTypical(tes)
    ElMessage.success('已删除')
    result.value = await generateApi.result(props.id)
  } catch {}
}
</script>

<template>
  <div class="p-4 space-y-3 max-w-5xl">
    <el-button text icon="ArrowLeft" @click="router.push('/runs')">返回任务列表</el-button>
    <el-button v-if="statusData?.status === 'fail'" type="warning" size="small" @click="retryGenerate">重试生成</el-button>

    <el-card v-if="statusData" shadow="never">
      <div class="flex items-center gap-4 text-sm flex-wrap">
        <span class="text-base font-bold text-slate-800">{{ clauseName || statusData.block_code }}</span>
        <el-tag :type="tagType(statusData.status)" size="small">{{ statusData.status }}</el-tag>
        <span class="text-slate-400">run_id: {{ id }}</span>
        <span class="text-slate-400" v-if="statusData.started_at">{{ new Date(statusData.started_at).toLocaleString() }}</span>
        <span class="text-slate-400" v-if="statusData.duration_ms">· {{ formatDuration(statusData.duration_ms) }}</span>
      </div>
    </el-card>

    <el-alert v-if="errorMsg" :title="errorMsg" type="error" :closable="false" show-icon />

    <el-card v-if="statusData" shadow="never">
      <template #header><span class="text-sm font-semibold text-slate-600">执行进度</span></template>
      <RunProgress :nodes="statusData.nodes || []" :running="phase === 'running'" :error-message="statusData.error_message || ''" />
    </el-card>

    <el-card v-if="!result?.bom && (result?.keywords?.length || result?.confusion_words?.length)" shadow="never">
      <template #header>
        <span class="text-sm font-semibold text-slate-600">关键词（Skill1 统计抽取）</span>
        <span class="text-xs text-slate-400 ml-2">部分结果 · 定义/规则生成未完成</span>
      </template>
      <div class="space-y-1.5 text-sm">
        <div><span class="text-slate-400">正向关键词：</span>
          <el-tag v-for="w in result.keywords" :key="w" type="primary" effect="plain" size="small" class="mr-1 mb-0.5">{{ w }}</el-tag>
          <span v-if="!result.keywords?.length" class="text-slate-300">—</span>
        </div>
        <div><span class="text-slate-400">易混淆词：</span>
          <el-tag v-for="w in result.confusion_words" :key="w" type="warning" effect="plain" size="small" class="mr-1 mb-0.5">{{ w }}</el-tag>
          <span v-if="!result.confusion_words?.length" class="text-slate-300">—</span>
        </div>
      </div>
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

    <el-card v-if="result?.bom?.typical_examples?.length" shadow="never">
      <template #header>
        <span class="text-sm font-semibold text-slate-600">典型正例（带分析理由·可编辑）</span>
        <span class="text-xs text-slate-400 ml-2">进提示词【正向抽取示例】</span>
      </template>
      <div class="space-y-2">
        <div v-for="(te, i) in result.bom.typical_examples" :key="i" class="border border-slate-200 rounded p-2.5">
          <div class="flex items-start justify-between gap-2">
            <div class="flex-1 min-w-0">
              <div class="text-sm text-slate-700 whitespace-pre-wrap break-all">{{ te.value }}</div>
              <div class="text-xs text-slate-600 mt-1.5 bg-slate-50 p-1.5 rounded leading-relaxed"><span class="text-slate-400">分析：</span>{{ te.reason || '（无）' }}</div>
            </div>
            <div class="flex-shrink-0 flex flex-col gap-1">
              <el-button size="small" icon="EditPen" @click="openTeEdit(i)">编辑</el-button>
              <el-popconfirm title="删除该典型正例？提示词会重 assemble。" width="240" @confirm="deleteTe(i)">
                <template #reference><el-button size="small" type="danger" plain icon="Delete">删除</el-button></template>
              </el-popconfirm>
            </div>
          </div>
        </div>
      </div>
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

    <el-dialog v-model="teDialog" title="编辑典型正例" width="640">
      <el-form label-width="72px">
        <el-form-item label="正例值"><el-input type="textarea" :rows="5" v-model="teForm.value" /></el-form-item>
        <el-form-item label="分析理由"><el-input type="textarea" :rows="4" v-model="teForm.reason" placeholder="引用匹配规则解释命中 + 确认不触发拦截/毒药词" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="teDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTe">保存（重 assemble 提示词）</el-button>
      </template>
    </el-dialog>
  </div>
</template>
