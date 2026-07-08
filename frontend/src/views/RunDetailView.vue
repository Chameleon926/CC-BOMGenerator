<script setup>
// B-2 实现（§5.3 + §13.2）：
// 任务信息 + 执行进度(RunProgress list 形态，中文化节点+✓/✗/○+耗时) + 选取数据(selected_examples)
// + BOM 折叠(BomPreview) + 提示词复制。轮询 useRunPoll(onUnmounted 清)。
defineProps({ id: { type: [String, Number], required: true } })
</script>

<template>
  <div class="p-4">
    <h2 class="text-base font-semibold text-slate-700 mb-3">任务详情 #{{ id }}</h2>
    <el-empty description="（B-2）执行进度 + 选取数据 + BOM + 提示词" />
  </div>
</template>
