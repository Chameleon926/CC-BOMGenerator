<script setup>
// 模型配置。设计见 §3.5 + 后端 GET/POST /config。
// api_key 留空=不改；保存后清 LLM 客户端缓存（温度立即生效）。
// 3 个 stage 温度已接线到生成管线（client.get_temperature），调了真生效。
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

// 3 个 stage 的说明（hover 「?」展示）。温度越高越发散/有创意，越低越确定/一致。
const stages = [
  {
    key: 'temperature_stage1', name: 'Stage1 · 定义规则', hint: '建议 0.1–0.3',
    tip: '【定义+规则生成】让大模型生成语义定义 + 拦截/匹配/毒药词规则（BOM 核心产出）。\n• 0.1–0.3（推荐）：规则稳定、可复现\n• >0.5：表达多样但易跑偏、漏规则\n默认 0.2',
  },
  {
    key: 'temperature_stage2', name: 'Stage2 · 召回画像', hint: '建议 0.4–0.7',
    tip: '【召回画像组装】组装召回锚点：关键词 / 易混淆词 / 章节提示 / 语义查询。\n• 0.4–0.7（推荐）：适度发散，覆盖多样同义表达\n• 过低：召回窄，漏同义表达\n默认 0.5',
  },
  {
    key: 'temperature_stage3', name: 'Stage3 · 自检', hint: '固定 0.0',
    tip: '【自检】大模型走思维链自检 BOM：抓资金方向反 / 主体错位 / 毒药词误伤。\n• 固定 0.0（强烈建议）：要确定性、严格判定\n• 调高会让自检结论不稳定\n默认 0.0',
  },
]

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

        <el-divider content-position="left">
          <span class="text-xs text-slate-400">生成管线温度（越高越发散，越低越确定）</span>
        </el-divider>

        <el-form-item v-for="s in stages" :key="s.key" :label="s.name">
          <div class="flex items-center gap-2">
            <el-input-number v-model="cfg[s.key]" :min="0" :max="2" :step="0.1" size="default" />
            <el-tooltip placement="right" :width="360" effect="light">
              <template #content>
                <div class="text-xs leading-relaxed text-slate-700" style="white-space: pre-line">{{ s.tip }}</div>
              </template>
              <el-icon class="text-slate-400 cursor-help" style="opacity: 0.55"><QuestionFilled /></el-icon>
            </el-tooltip>
            <span class="text-xs text-slate-400">{{ s.hint }}</span>
          </div>
        </el-form-item>

        <el-form-item><el-button type="primary" :loading="saving" @click="save">保存配置</el-button></el-form-item>
      </el-form>
    </div>
  </div>
</template>
