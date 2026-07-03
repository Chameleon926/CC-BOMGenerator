<script setup>
import { ref, computed, onUnmounted } from 'vue'
import axios from 'axios'

const API = '/api' // vite 代理 → backend:8000

// ① 设计环节
const file = ref(null)
const clause = ref('')
const blockCode = ref('')
const nkw = ref(10), nsec = ref(6), nq = ref(3), skipVerify = ref(false)
const fileName = ref('')
const onFileChange = (e) => { file.value = e.target.files[0]; fileName.value = file.value?.name || '' }
const clearFile = () => { file.value = null; fileName.value = '' }

// 状态机
const phase = ref('idle') // idle | running | done | error
const runId = ref(null)
const statusData = ref(null)
const result = ref(null)
const error = ref('')
let pollTimer = null

const TOTAL_STEPS = 7              // 7 个 Skill（不含回修）
const POLL_INTERVAL = 2000
const POLL_MAX_MS = 5 * 60 * 1000  // C1: 超时熔断
const POLL_MAX_FAILS = 5           // C2: 连续失败上限

const stopPolling = () => { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }

const startGenerate = async () => {
  if (!file.value) { error.value = '请先上传测试集 Excel'; return }
  phase.value = 'running'; error.value = ''; result.value = null; statusData.value = null
  const form = new FormData()
  form.append('file', file.value)
  if (clause.value) form.append('clause', clause.value)
  if (blockCode.value) form.append('block_code', blockCode.value)
  form.append('nkw', nkw.value); form.append('nsec', nsec.value); form.append('nq', nq.value)
  form.append('skip_verify', skipVerify.value)
  try {
    const { data } = await axios.post(`${API}/generate`, form)
    runId.value = data.run_id
    startPolling()
  } catch (e) {
    phase.value = 'error'
    error.value = (e.response?.data?.detail) || e.message || '启动生成失败'
  }
}

const startPolling = () => {
  const pollStart = Date.now()
  let failCount = 0
  pollTimer = setInterval(async () => {
    if (Date.now() - pollStart > POLL_MAX_MS) {                         // C1 超时熔断
      stopPolling(); phase.value = 'error'; error.value = '生成超时（超过 5 分钟）'; return
    }
    try {
      const { data } = await axios.get(`${API}/runs/${runId.value}/status`)
      statusData.value = data; failCount = 0                           // C2 成功重置
      if (data.status === 'success' || data.status === 'fail') {
        stopPolling()
        if (data.status === 'success') await fetchResult()
        else { phase.value = 'error'; error.value = data.error_message || '生成失败（查看节点 ✗）' }
      }
    } catch (e) {                                                       // C2 连续失败
      failCount += 1
      if (failCount >= POLL_MAX_FAILS) {
        stopPolling(); phase.value = 'error'
        error.value = '后端连接中断（连续 ' + POLL_MAX_FAILS + ' 次轮询失败）'
      }
    }
  }, POLL_INTERVAL)
}

const fetchResult = async () => {                                       // I3 防静默死锁
  try {
    const { data } = await axios.get(`${API}/runs/${runId.value}/result`)
    result.value = data; phase.value = 'done'
  } catch (e) {
    phase.value = 'error'; error.value = '结果拉取失败：' + ((e.response?.data?.detail) || e.message)
  }
}

const reset = () => {                                                   // I7 清文件
  stopPolling()
  phase.value = 'idle'; runId.value = null; statusData.value = null; result.value = null; error.value = ''
  file.value = null; fileName.value = ''
}

onUnmounted(stopPolling)

const copyPrompt = async () => {                                        // I4 clipboard 降级
  const text = result.value?.full_prompt?.prompt_text || ''
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {                                                           // 非 secure context 降级
      const ta = document.createElement('textarea')
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'
      document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta)
    }
    alert('提示词已复制，可粘贴到新平台跑分')
  } catch {
    alert('复制失败，请手动选择提示词文本复制')
  }
}

// Skill 中文名 + 业务描述（业务用户看得懂）
const SKILL_META = {
  FeatureExtractSkill: { name: '关键词抽取', desc: '从正例文本抽取短词关键词、易混淆词，并聚类挑选多样正例（程序化算法，不调大模型，防过拟合）' },
  ExampleRetrieveSkill: { name: '正例挑选', desc: '从候选中按多样性聚类挑选代表性正例，作为向量召回的锚点' },
  DefinitionRuleSkill: { name: '定义 + 规则生成', desc: '大模型基于关键词产出语义定义 + 拦截规则（防误抽）+ 匹配规则（防漏抽）' },
  ProfileBuildSkill: { name: '召回画像组装', desc: '大模型组装召回画像：正向关键词、易混淆词、章节提示、语义查询句、正例' },
  RuleCheckSkill: { name: '规则校验', desc: '程序化检查拦截规则是否误杀正例（不调大模型），若误杀则触发回修' },
  SelfCheckSkill: { name: '自检', desc: '大模型自检 BOM 是否有红旗（规则矛盾 / 过拟合 / 漏覆盖），有红旗则触发回修' },
  PromptAssembleSkill: { name: '提示词组装', desc: '把定义 + 规则 + 画像 + 输出 JSON Schema 组装成完整提示词，供新平台跑分' },
}
const skillName = (s) => SKILL_META[s]?.name || s
const skillDesc = (s) => SKILL_META[s]?.desc || '（暂无描述）'

// 进度：首次执行的节点数（不含回修）
const firstPassNodes = computed(() => (statusData.value?.nodes || []).filter(n => !n.is_retry))
const progress = computed(() => Math.min(100, Math.round(firstPassNodes.value.length / TOTAL_STEPS * 100)))
const elapsed = computed(() => statusData.value?.duration_ms ? Math.round(statusData.value.duration_ms / 1000) + 's' : '—')
</script>

<template>
  <div class="app">
    <header>
      <h1>语义 BOM 生成 demo</h1>
      <p class="sub">上传测试集 → 实时看节点进度 → 出 BOM + 完整提示词（粘新平台跑分）</p>
    </header>

    <!-- ① 设计环节 -->
    <section class="card" v-if="phase === 'idle' || phase === 'error'">
      <h2>① 设计环节 · 上传测试集 & 参数</h2>
      <div class="form">
        <label class="file-label">
          <span>测试集 Excel（必填，需含「期望值」列；可选「Block Code」「Block Name」列）</span>
          <div class="file-drop">
            <input type="file" @change="onFileChange" accept=".xlsx,.xls,.csv" />
            <span class="file-name">{{ fileName || '点击选择文件…' }}</span>
            <button v-if="fileName" type="button" class="clear-btn" @click.stop="clearFile" title="移除文件">×</button>
          </div>
        </label>
        <div class="row">
          <label>条款名称（可选，空则从测试集聚）
            <input v-model="clause" placeholder="如：付款支持文档" />
          </label>
          <label>语义块编码（可选）
            <input v-model="blockCode" placeholder="如：FSB0000004" />
          </label>
        </div>
        <div class="row numbers">
          <label>关键词数 <input type="number" v-model.number="nkw" /></label>
          <label>章节数 <input type="number" v-model.number="nsec" /></label>
          <label>语义查询数 <input type="number" v-model.number="nq" /></label>
          <label class="check"><input type="checkbox" v-model="skipVerify" /> 跳过自检</label>
        </div>
        <button @click="startGenerate">开始生成</button>
        <p class="error" v-if="error">⚠ {{ error }}</p>
      </div>
    </section>

    <!-- ② 进度环节 -->
    <section class="card" v-if="phase === 'running' || phase === 'done'">
      <h2>
        ② 进度环节 · 实时节点状态
        <span class="badge" :class="statusData?.status">{{ statusData?.status }}</span>
        <span class="elapsed" v-if="phase === 'done'">耗时 {{ elapsed }}</span>
      </h2>
      <div class="progress-bar"><div class="progress-fill" :style="{ width: progress + '%' }"></div></div>
      <p class="progress-text">首次执行 {{ firstPassNodes.length }} / {{ TOTAL_STEPS }} 节点</p>
      <div class="nodes">
        <details v-for="n in statusData?.nodes" :key="n.seq + '-' + n.skill" class="node-details" :class="{ retry: n.is_retry, fail: !n.success }">
          <summary>
            <span class="seq">{{ n.is_retry ? '↻' : n.seq }}</span>
            <span class="skill">{{ skillName(n.skill) }}</span>
            <span class="ok" :class="{ ok2: n.success, nok: !n.success }">{{ n.success ? '✓' : '✗' }}</span>
            <span class="dur">{{ n.duration_ms }}ms</span>
            <span class="expand-hint">展开 ▾</span>
          </summary>
          <div class="node-body">
            <p class="node-desc">{{ skillDesc(n.skill) }}</p>
            <p class="retry-tag" v-if="n.is_retry">↻ 回修重跑（第 {{ n.retry_round }} 次）—— 首轮自检/规则校验发现问题，重新生成定义/画像/规则</p>
          </div>
        </details>
        <div v-if="phase === 'running'" class="node running-pending">
          <span class="spinner"></span>
          <span class="skill">正在处理下一个节点…</span>
        </div>
      </div>
      <button class="ghost" v-if="phase === 'done'" @click="reset">重新生成</button>
    </section>

    <!-- ③ 输出环节 -->
    <section class="card" v-if="result">
      <h2>③ 输出环节 · BOM + 完整提示词</h2>
      <div class="bom-summary">
        <span><b>条款：</b>{{ result.bom.clause }}</span>
        <span><b>编码：</b>{{ result.bom.block_code }}</span>
        <span><b>版本：</b>v{{ result.bom.version }}</span>
      </div>

      <details open>
        <summary>语义定义</summary>
        <p class="def">{{ result.bom.semantic_definition }}</p>
      </details>

      <details>
        <summary>拦截规则（{{ result.bom.extraction_rules?.absolute_interception_rules?.length }} 条 · 防误抽）</summary>
        <ul><li v-for="(r, i) in result.bom.extraction_rules?.absolute_interception_rules" :key="i">{{ r.rule }}</li></ul>
      </details>

      <details>
        <summary>匹配规则（{{ result.bom.extraction_rules?.core_match_rules?.length }} 条 · 防漏抽）</summary>
        <ul><li v-for="(r, i) in result.bom.extraction_rules?.core_match_rules" :key="i">{{ r.rule }}</li></ul>
      </details>

      <details>
        <summary>召回画像</summary>
        <div class="profile">
          <div><b>正向关键词：</b><span class="tags">{{ result.bom.recall_profile?.positive_keywords?.join(' · ') }}</span></div>
          <div><b>易混淆词：</b><span class="tags conf">{{ result.bom.recall_profile?.confusion_words?.join(' · ') }}</span></div>
          <div><b>章节提示：</b>{{ result.bom.recall_profile?.section_hints?.join(' · ') }}</div>
          <div><b>语义查询：</b><ul><li v-for="(q, i) in result.bom.recall_profile?.semantic_queries" :key="i">{{ q }}</li></ul></div>
          <div><b>正例（召回锚点）：</b><ul><li v-for="(e, i) in result.bom.recall_profile?.positive_examples" :key="i">{{ e }}</li></ul></div>
        </div>
      </details>

      <details>
        <summary>完整提示词（粘新平台跑分）<button class="copy" @click.stop="copyPrompt">复制</button></summary>
        <pre>{{ result.full_prompt?.prompt_text }}</pre>
      </details>
    </section>
  </div>
</template>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f4f5f7; color: #222; }
.app { max-width: 920px; margin: 0 auto; padding: 24px 16px 60px; }
header h1 { margin: 0 0 4px; font-size: 24px; }
.sub { margin: 0 0 20px; color: #666; font-size: 13px; }
.card { background: #fff; border-radius: 10px; padding: 20px 22px; margin: 14px 0; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
h2 { font-size: 17px; margin: 0 0 16px; display: flex; align-items: center; gap: 10px; }
.form { display: flex; flex-direction: column; gap: 14px; }
.form label { display: flex; flex-direction: column; gap: 5px; font-size: 13px; color: #444; }
.form input[type=text], .form input:not([type]) { padding: 8px 10px; border: 1px solid #d9dce1; border-radius: 6px; font-size: 14px; }
.form input:focus { outline: none; border-color: #4a90d9; }
.file-drop { position: relative; border: 1.5px dashed #c4c8cf; border-radius: 6px; padding: 18px; text-align: center; cursor: pointer; }
.file-drop input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.file-name { color: #4a90d9; font-size: 14px; }
.clear-btn { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: #d9534f; color: #fff; border: none; width: 22px; height: 22px; border-radius: 50%; cursor: pointer; font-size: 14px; line-height: 1; padding: 0; }
.row { display: flex; gap: 14px; flex-wrap: wrap; }
.row > label { flex: 1; min-width: 180px; }
.row.numbers > label { max-width: 130px; }
.check { flex-direction: row !important; align-items: center; gap: 6px !important; }
button { background: #4a90d9; color: #fff; border: none; padding: 11px 22px; border-radius: 6px; cursor: pointer; font-size: 14px; align-self: flex-start; }
button:hover { background: #357abd; }
button.ghost { background: #fff; color: #4a90d9; border: 1px solid #4a90d9; }
button.copy { padding: 3px 10px; font-size: 12px; background: #5cb85c; }
.error { color: #d9534f; font-size: 13px; }
.badge { padding: 2px 10px; border-radius: 10px; font-size: 11px; color: #fff; background: #f0ad4e; }
.badge.success { background: #5cb85c; }
.badge.fail { background: #d9534f; }
.elapsed { font-size: 12px; color: #888; font-weight: normal; }
.progress-bar { background: #e9ecef; border-radius: 6px; height: 18px; overflow: hidden; }
.progress-fill { background: linear-gradient(90deg, #4a90d9, #5cb85c); height: 100%; transition: width .6s; }
.progress-text { font-size: 12px; color: #666; margin: 6px 0 12px; }
.nodes { font-size: 13px; }
.node-details { border-bottom: 1px solid #f0f0f0; }
.node-details:last-of-type { border: none; }
.node-details.retry { padding-left: 16px; }
.node-details.fail { color: #d9534f; }
.node-details > summary { display: flex; align-items: center; gap: 12px; padding: 7px 0; cursor: pointer; list-style: none; }
.node-details > summary::-webkit-details-marker { display: none; }
.node-details[open] > summary { color: #4a90d9; }
.seq { width: 24px; color: #999; text-align: center; }
.skill { flex: 1; }
.ok2 { color: #5cb85c; } .nok { color: #d9534f; }
.ok { width: 18px; font-weight: bold; }
.dur { color: #999; font-size: 11px; width: 70px; text-align: right; }
.expand-hint { font-size: 10px; color: #aaa; width: 50px; }
.node-body { padding: 4px 12px 12px 36px; color: #555; }
.node-desc { margin: 0; line-height: 1.6; font-size: 12px; }
.retry-tag { color: #e67e22; margin: 6px 0 0; font-size: 12px; }
.spinner { width: 14px; height: 14px; border: 2px solid #e0e0e0; border-top-color: #4a90d9; border-radius: 50%; animation: spin .8s linear infinite; display: inline-block; margin-right: 4px; }
@keyframes spin { to { transform: rotate(360deg); } }
.running-pending { display: flex; align-items: center; gap: 10px; padding: 8px 0; color: #4a90d9; }
.bom-summary { display: flex; gap: 24px; flex-wrap: wrap; padding: 10px 14px; background: #f8f9fa; border-radius: 6px; margin-bottom: 14px; font-size: 14px; }
details { margin: 8px 0; padding: 10px 14px; background: #fafbfc; border: 1px solid #eee; border-radius: 6px; }
summary { cursor: pointer; font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 10px; }
summary::marker { color: #4a90d9; }
.def { margin: 8px 0 0; line-height: 1.7; font-size: 14px; }
ul { margin: 8px 0; padding-left: 20px; line-height: 1.8; font-size: 13px; }
.profile div { margin: 8px 0; font-size: 13px; }
.tags { color: #4a90d9; }
.tags.conf { color: #e67e22; }
pre { background: #f0f2f5; padding: 12px; border-radius: 6px; white-space: pre-wrap; word-break: break-all; max-height: 360px; overflow: auto; font-size: 12px; margin-top: 10px; }
</style>
