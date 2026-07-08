<script setup>
// B-2 实现（docs/frontend-design.md §5.1 + §13.2）：
// el-upload 导入(scan) + el-table 条款列表 + 新增(dialog) + 删除(popconfirm) + 搜索(debounce) + el-empty
// 数据源：clausesApi.list / scan / create / remove
</script>

<template>
  <div class="p-4">
    <h2 class="text-base font-semibold text-slate-700 mb-3">条款库</h2>
    <el-empty description="（B-2）导入测试集 / 新增 / 删除 / 搜索" />
  </div>
</template>
