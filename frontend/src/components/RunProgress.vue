<script setup>
// 节点执行进度（任务详情用，列表用 el-progress 直接内联）。
// 设计见 docs/frontend-design.md §5.3 + §13.3。
// - 失败节点 ❗：hover（~0.6s）弹出失败原因，可一键复制。
// - 执行中：按已完成步数推出当前步骤名（[N] 名称 ⟳），名称在前转圈在后。
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { skillName, SKILL_SEQUENCE, formatDuration } from '../constants/skill'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
  errorMessage: { type: String, default: '' },
})

// 已完成步数（非回修）→ 当前执行的是第 done+1 步
const doneCount = computed(() => props.nodes.filter(n => !n.is_retry).length)
const runningSeq = computed(() => doneCount.value + 1)
const runningSkill = computed(() => SKILL_SEQUENCE[doneCount.value]) // undefined = 全部跑完

const copyError = async () => {
  try { await navigator.clipboard.writeText(props.errorMessage); ElMessage.success('失败原因已复制') }
  catch { ElMessage.error('复制失败') }
}
</script>

<template>
  <div class="space-y-1.5">
    <div v-for="(n, i) in nodes" :key="i"
         class="flex items-center gap-2 text-xs py-1" :class="{ 'pl-4 text-orange-500': n.is_retry }">
      <span class="w-5 text-slate-400 text-center">{{ n.is_retry ? '↻' : n.seq }}</span>
      <span class="flex-1 text-slate-600">{{ skillName(n.skill) }}</span>

      <!-- 失败节点：hover 弹失败原因（可复制） -->
      <el-popover v-if="!n.success && errorMessage" trigger="hover" :show-after="600" :hide-after="200" placement="top" :width="460">
        <template #reference>
          <el-icon color="#dc2626" class="cursor-pointer"><WarningFilled /></el-icon>
        </template>
        <div class="text-xs">
          <div class="font-semibold text-slate-700 mb-1.5">失败原因</div>
          <pre class="text-red-600 bg-red-50 p-2 rounded max-h-52 overflow-auto whitespace-pre-wrap break-all leading-relaxed">{{ errorMessage }}</pre>
          <el-button size="small" icon="CopyDocument" @click="copyError" class="mt-2">复制原因</el-button>
        </div>
      </el-popover>

      <el-icon v-else :color="n.success ? '#16a34a' : '#dc2626'">
        <CircleCheckFilled v-if="n.success" /><WarningFilled v-else />
      </el-icon>

      <span class="text-slate-300 w-14 text-right tabular-nums">{{ formatDuration(n.duration_ms) }}</span>
    </div>

    <!-- 执行中：显示当前步骤名（按已完成数推出）+ 转圈 -->
    <div v-if="running && runningSkill" class="flex items-center gap-2 text-xs py-1 text-blue-500">
      <span class="w-5 text-slate-400 text-center">{{ runningSeq }}</span>
      <span class="flex-1">{{ skillName(runningSkill) }}</span>
      <el-icon class="is-loading" color="#3b82f6"><Loading /></el-icon>
      <span class="text-slate-300 w-14 text-right">执行中</span>
    </div>
  </div>
</template>
