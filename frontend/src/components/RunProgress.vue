<script setup>
// 节点执行进度（任务详情用，列表用 el-progress 直接内联）。
// 设计见 docs/frontend-design.md §5.3 + §13.3。
import { skillName } from '../constants/skill'

defineProps({
  nodes: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
})
</script>

<template>
  <div class="space-y-1.5">
    <div v-for="(n, i) in nodes" :key="i"
         class="flex items-center gap-2 text-xs py-1" :class="{ 'pl-4 text-orange-500': n.is_retry }">
      <span class="w-5 text-slate-400 text-center">{{ n.is_retry ? '↻' : n.seq }}</span>
      <span class="flex-1 text-slate-600">{{ skillName(n.skill) }}</span>
      <el-icon :color="n.success ? '#16a34a' : '#dc2626'">
        <CircleCheckFilled v-if="n.success" /><WarningFilled v-else />
      </el-icon>
      <span class="text-slate-300 w-14 text-right tabular-nums">{{ n.duration_ms ? n.duration_ms + 'ms' : '—' }}</span>
    </div>
    <div v-if="running" class="text-blue-500 text-xs py-1 flex items-center gap-1">
      <el-icon class="is-loading"><Loading /></el-icon> 处理中…
    </div>
  </div>
</template>
