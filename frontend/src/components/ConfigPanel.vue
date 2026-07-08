<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from 'axios'

const API = '/api'
const cfg = reactive({
  api_format: '', base_url: '', model: '', api_key: '',
  temperature_stage1: 0.2, temperature_stage2: 0.5, temperature_stage3: 0.0,
})
const maskedKey = ref('')
const loading = ref(true)
const saving = ref(false)
const msg = ref('')
const msgType = ref('')  // 'ok' | 'err'

onMounted(async () => {
  try {
    const { data } = await axios.get(`${API}/config`)
    cfg.api_format = data.api_format || ''
    cfg.base_url = data.base_url || ''
    cfg.model = data.model || ''
    cfg.temperature_stage1 = data.temperature_stage1 ?? 0.2
    cfg.temperature_stage2 = data.temperature_stage2 ?? 0.5
    cfg.temperature_stage3 = data.temperature_stage3 ?? 0.0
    maskedKey.value = data.api_key_masked || ''
    cfg.api_key = ''  // 留空（不改=保持）
  } catch (e) {
    msg.value = '读取失败：' + (e.response?.data?.detail || e.message)
    msgType.value = 'err'
  } finally {
    loading.value = false
  }
})

const save = async () => {
  saving.value = true; msg.value = ''
  try {
    const { data } = await axios.post(`${API}/config`, cfg)
    msg.value = '✓ 已保存（更新字段：' + (data.updated_fields.join(', ') || '无') + '）'
    msgType.value = 'ok'
    cfg.api_key = ''  // 清空（已保存）
  } catch (e) {
    msg.value = '✗ 保存失败：' + (e.response?.data?.detail || e.message)
    msgType.value = 'err'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="config-panel">
    <h2>模型配置</h2>
    <p class="hint">修改后写回 <code>config/llm.yaml</code>，立即生效（清 LLM 客户端缓存）。<b>API Key 留空 = 不改</b>（保持原值）。</p>

    <form @submit.prevent="save" v-if="!loading" class="form">
      <div class="row">
        <label>API 格式
          <select v-model="cfg.api_format">
            <option value="anthropic">anthropic</option>
            <option value="openai">openai</option>
          </select>
        </label>
        <label>Model
          <input v-model="cfg.model" placeholder="astron-code-latest" />
        </label>
      </div>

      <label>Base URL
        <input v-model="cfg.base_url" placeholder="https://maas-coding-api..." />
      </label>

      <label>API Key <span class="masked" v-if="maskedKey">（当前：{{ maskedKey }}）</span>
        <input v-model="cfg.api_key" type="password" :placeholder="maskedKey ? maskedKey + '（不改留空）' : '输入新 key'" />
      </label>

      <div class="row temps">
        <label>Stage1 温度（定义规则）
          <input type="number" step="0.1" min="0" max="2" v-model.number="cfg.temperature_stage1" />
        </label>
        <label>Stage2 温度（画像）
          <input type="number" step="0.1" min="0" max="2" v-model.number="cfg.temperature_stage2" />
        </label>
        <label>Stage3 温度（自检）
          <input type="number" step="0.1" min="0" max="2" v-model.number="cfg.temperature_stage3" />
        </label>
      </div>

      <div class="actions">
        <button :disabled="saving">{{ saving ? '保存中…' : '💾 保存配置' }}</button>
        <span class="msg" :class="msgType">{{ msg }}</span>
      </div>
    </form>
    <p v-else>加载中…</p>
  </div>
</template>

<style scoped>
.config-panel { max-width: 640px; margin: 0 auto; background: #fff; border-radius: 8px; padding: 24px 28px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
h2 { margin: 0 0 8px; font-size: 18px; }
.hint { color: #666; font-size: 13px; margin: 0 0 18px; line-height: 1.6; }
code { background: #f0f2f5; padding: 1px 5px; border-radius: 3px; font-size: 12px; }
.form { display: flex; flex-direction: column; gap: 14px; }
label { display: flex; flex-direction: column; gap: 5px; font-size: 13px; color: #444; font-weight: 600; }
input, select { padding: 8px 10px; border: 1px solid #d9dce1; border-radius: 5px; font-size: 14px; font-weight: normal; }
input:focus, select:focus { outline: none; border-color: #4a90d9; }
.row { display: flex; gap: 14px; }
.row > label { flex: 1; }
.temps > label { max-width: 140px; }
.masked { font-weight: normal; color: #888; font-size: 11px; }
.actions { display: flex; align-items: center; gap: 14px; margin-top: 6px; }
button { background: #4a90d9; color: #fff; border: none; padding: 10px 22px; border-radius: 5px; cursor: pointer; font-size: 14px; }
button:hover { background: #357abd; }
button:disabled { opacity: .6; cursor: not-allowed; }
.msg { font-size: 13px; }
.msg.ok { color: #5cb85c; }
.msg.err { color: #d9534f; }
</style>
