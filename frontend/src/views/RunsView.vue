<script setup>
// B-2 实现（§5.2 + §13.1/§13.2）：
// el-table 任务列表 + el-progress(progress%) + el-tag(status) + 停止(popconfirm)/详情
// block_code 读 route.query.block_code 透传 GET /runs；任一 running 时轮询(onUnmounted 清)
// 合并 usePendingRuns 单例（刚创建未落库的 run，避免竞态）
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <div class="p-4">
    <h2 class="text-base font-semibold text-slate-700 mb-3">
      生成任务<span class="text-slate-400 text-sm ml-2">{{ route.query.block_code || '全部' }}</span>
    </h2>
    <el-empty description="（B-2）任务列表 + 进度 + 状态 + 停止/详情" />
  </div>
</template>
