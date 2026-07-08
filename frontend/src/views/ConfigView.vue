<script setup>
// 模型配置。设计见 §3.5 + 后端 GET/POST /config。
// api_key 留空=不改；保存后清 LLM 客户端缓存。
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { configApi } from '../api/config'

const cfg = reactive({
  api_format: 'openai', base_url: '', model: '', api_key: '',
  temperature_stage1: 0.2, temperature_stage2: 0.5, temperature_stage3: 0.0,
})
const maskedKey = ref('')
const loading = ref(true)
const saving = ref(false)

onMounted(async () => {
  try {
    const data = await configApi.get()
    cfg.api_format = data.api_format || 'openai'
    cfg.base_url = data.base_url || ''
    cfg.model = data.model || ''
    cfg.temperature_stage1 = data.temperature_stage1 ?? 0.2
    cfg.temperature_stage2 = data.temperature_stage2 ?? 0.5
    cfg.temperature_stage3 = data.temperature_stage3 ?? 0.0
    maskedKey.value = data.api_key_masked || ''
    cfg.api_key = ''
  } catch {} finally { loading.value = false }
})

const save = async () => {
  saving.value = true
  try {
    const data = await configApi.update(cfg)
    ElMessage.success('已保存（更新字段：' + (data.updated_fields?.join(', ') || '无') + '）')
    cfg.api_key = ''
  } catch {} finally { saving.value = false }
}
</script>

<template>
  <div class="p-4">
    <div class="max-w-2xl bg-white rounded-lg p-6" v-loading="loading">
      <p class="text-slate-500 text-sm mb-4 leading-relaxed">
        修改后写回 <code class="bg-slate-100 px-1 rounded text-xs">config/llm.yaml</code>，立即生效（清 LLM 客户端缓存）。
        <b>API Key 留空 = 不改</b>（保持原值）。
      </p>
      <el-form :model="cfg" label-width="110px" v-if="!loading">
        <el-form-item label="API 格式">
          <el-select v-model="cfg.api_format"><el-option label="openai" value="openai" /><el-option label="anthropic" value="anthropic" /></el-select>
        </el-form-item>
        <el-form-item label="Model"><el-input v-model="cfg.model" placeholder="模型名" /></el-form-item>
        <el-form-item label="Base URL"><el-input v-model="cfg.base_url" placeholder="https://..." /></el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="cfg.api_key" type="password" :placeholder="maskedKey ? maskedKey + '（不改留空）' : '输入新 key'" />
          <div v-if="maskedKey" class="text-xs text-slate-400 mt-1">当前：{{ maskedKey }}</div>
        </el-form-item>
        <el-form-item label="Stage1 温度"><el-input-number v-model="cfg.temperature_stage1" :min="0" :max="2" :step="0.1" /></el-form-item>
        <el-form-item label="Stage2 温度"><el-input-number v-model="cfg.temperature_stage2" :min="0" :max="2" :step="0.1" /></el-form-item>
        <el-form-item label="Stage3 温度"><el-input-number v-model="cfg.temperature_stage3" :min="0" :max="2" :step="0.1" /></el-form-item>
        <el-form-item><el-button type="primary" :loading="saving" @click="save">保存配置</el-button></el-form-item>
      </el-form>
    </div>
  </div>
</template>
