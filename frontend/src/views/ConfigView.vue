<script setup>
// B-2 实现：模型配置表单（api_format/base_url/model/api_key/3 个温度）
// 数据源：configApi.get / update。api_key 留空=不改。提交后清 LLM 缓存。
</script>

<template>
  <div class="p-4">
    <h2 class="text-base font-semibold text-slate-700 mb-3">模型配置</h2>
    <el-empty description="（B-2）读写 config/llm.yaml" />
  </div>
</template>
