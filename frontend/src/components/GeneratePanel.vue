<script setup>
import { ref, reactive, computed, onUnmounted } from 'vue'
import axios from 'axios'
const API = '/api'

const SKILL_META = {
  FeatureExtractSkill: { name: '关键词抽取', desc: '从正例抽短词关键词、易混淆词，聚类选正例（程序化）' },
  ExampleRetrieveSkill: { name: '正例挑选', desc: '聚类选多样正例作召回锚点' },
  DefinitionRuleSkill: { name: '定义+规则生成', desc: '大模型产定义+分场景拦截+毒药词+思维链+判例' },
  ProfileBuildSkill: { name: '召回画像组装', desc: '大模型组装画像：关键词/混淆词/章节/语义查询/正反例' },
  RuleCheckSkill: { name: '规则校验', desc: '程序化校验拦截误杀+毒药词命中+场景覆盖' },
  SelfCheckSkill: { name: '自检', desc: '大模型走思维链自检方向反/主体错/毒药词误伤' },
  PromptAssembleSkill: { name: '提示词组装', desc: '组装完整提示词' },
}
const skillName = s => SKILL_META[s]?.name || s
const skillDesc = s => SKILL_META[s]?.desc || ''

// 两级视图：library（条款库）| generate（辅助生成）
const view = ref('library')
const selected = ref(null)

// 上传 + 扫描
const fileName = ref('')
const uploadedFile = ref(null)
const clauses = ref([])
const scanning = ref(false)
const scanError = ref('')
const searchQuery = ref('')

const onFileChange = async (e) => {
  const f = e.target.files[0]; if (!f) return
  uploadedFile.value = f; fileName.value = f.name
  scanning.value = true; scanError.value = ''
  try {
    const form = new FormData(); form.append('file', f)
    const { data } = await axios.post(`${API}/testset/scan`, form)
    clauses.value = data.clauses
  } catch (err) { scanError.value = err.response?.data?.detail || err.message }
  finally { scanning.value = false }
}

const filteredClauses = computed(() => {
  if (!searchQuery.value.trim()) return clauses.value
  const q = searchQuery.value.toLowerCase()
  return clauses.value.filter(c =>
    (c.block_name || '').toLowerCase().includes(q) || c.block_code.toLowerCase().includes(q)
  )
})

// 每条款生成状态
const runs = reactive({})
const startGenerate = async (block_code) => {
  const c = clauses.value.find(c => c.block_code === block_code); if (!c || !uploadedFile.value) return
  const r = reactive({ run_id: null, phase: 'running', statusData: null, result: null, error: '', pollTimer: null })
  runs[block_code] = r
  const form = new FormData(); form.append('file', uploadedFile.value)
  form.append('clause', c.block_name); form.append('block_code', c.block_code)
  try {
    const { data } = await axios.post(`${API}/generate`, form)
    r.run_id = data.run_id; startPoll(block_code, r)
  } catch (e) { r.phase = 'error'; r.error = e.response?.data?.detail || e.message }
}
const startPoll = (bc, r) => {
  const start = Date.now(); let fails = 0
  r.pollTimer = setInterval(async () => {
    if (Date.now() - start > 5*60*1000) { stopPoll(r); r.phase='error'; r.error='超时'; return }
    try {
      const { data } = await axios.get(`${API}/runs/${r.run_id}/status`)
      r.statusData = data; fails = 0
      if (data.status === 'success' || data.status === 'fail') {
        stopPoll(r)
        if (data.status === 'success') {
          try { const { data: res } = await axios.get(`${API}/runs/${r.run_id}/result`); r.result = res; r.phase = 'done' }
          catch (e) { r.phase = 'error'; r.error = '结果拉取失败' }
        } else { r.phase = 'error'; r.error = data.error_message || '生成失败' }
      }
    } catch (e) { fails++; if (fails >= 5) { stopPoll(r); r.phase='error'; r.error='连接中断' } }
  }, 2000)
}
const stopPoll = r => { if (r?.pollTimer) { clearInterval(r.pollTimer); r.pollTimer = null } }
onUnmounted(() => Object.values(runs).forEach(stopPoll))

const openGenerate = (c) => { selected.value = c; view.value = 'generate' }
const backToLibrary = () => { view.value = 'library' }
const currentRun = computed(() => selected.value ? runs[selected.value.block_code] : null)

const copyPrompt = async (text) => {
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text)
    else { const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta) }
    alert('提示词已复制')
  } catch { alert('复制失败') }
}

// 全部生成
const generatingAll = ref(false)
const generateAll = async () => {
  generatingAll.value = true
  for (const c of clauses.value) {
    if (runs[c.block_code]?.phase === 'done') continue
    startGenerate(c.block_code)
    while (runs[c.block_code]?.phase === 'running') await new Promise(r => setTimeout(r, 2000))
  }
  generatingAll.value = false
}
const completedCount = computed(() => Object.values(runs).filter(r => r.phase === 'done').length)

// 卡片辅助
const bomDesc = (bc) => {
  const r = runs[bc]?.result
  if (r?.bom?.semantic_definition) return r.bom.semantic_definition.slice(0, 80) + (r.bom.semantic_definition.length > 80 ? '…' : '')
  return '尚未生成 BOM，点击进入辅助生成。'
}
const statusText = (bc) => {
  const p = runs[bc]?.phase
  return p ? ({ running: '⏳ 生成中', done: '✓ 已生成', error: '✗ 失败' }[p]) : '待生成'
}
const statusClass = (bc) => {
  const p = runs[bc]?.phase
  return p === 'done' ? 'green' : p === 'running' ? 'amber' : p === 'error' ? 'red' : 'gray'
}
const bomVersion = (bc) => runs[bc]?.result?.bom?.version
</script>

<template>
  <div>
    <!-- ===== 第一级：条款/要素库 ===== -->
    <template v-if="view === 'library'">
      <div class="section-title">条款 / 要素库</div>
      <div class="section-desc">上传测试集自动识别条款/要素，点击卡片进入辅助生成。</div>

      <div class="lib-bar">
        <label class="upload" style="min-width:240px">
          <input type="file" @change="onFileChange" accept=".xlsx,.xls,.csv" />
          <span v-if="fileName" class="fname">✓ {{ fileName }}</span>
          <span v-else>📁 上传测试集（多 sheet / 多条款）</span>
        </label>
        <div class="search">
          <input v-model="searchQuery" placeholder="搜索条款名称 / 编码…" :disabled="!clauses.length" />
        </div>
        <button v-if="clauses.length" class="btn primary" @click="generateAll" :disabled="generatingAll">
          {{ generatingAll ? `生成中 ${completedCount}/${clauses.length}` : `⚡ 全部生成（${clauses.length}）` }}
        </button>
      </div>
      <p v-if="scanError" style="color:var(--danger);font-size:13px;margin-bottom:14px">⚠ {{ scanError }}</p>

      <div class="lib-grid" v-if="filteredClauses.length">
        <div v-for="c in filteredClauses" :key="c.block_code" class="el-card" @click="openGenerate(c)">
          <div class="top">
            <div class="ename">{{ c.block_name || c.block_code }}</div>
            <span class="tag indigo">条款</span>
          </div>
          <div class="meta">{{ c.block_code }} · {{ c.positive_count }} 用例 · {{ c.sheets.length }} sheet</div>
          <div class="desc">{{ bomDesc(c.block_code) }}</div>
          <div class="stat">
            <span v-if="bomVersion(c.block_code)" class="ver">v{{ bomVersion(c.block_code) }}</span>
            <span class="tag" :class="statusClass(c.block_code)">{{ statusText(c.block_code) }}</span>
          </div>
        </div>
      </div>
      <div v-else-if="!scanning && fileName" class="empty faint">无匹配条款</div>
      <div v-else-if="!fileName" class="empty faint">上传测试集后，条款将显示在这里</div>
    </template>

    <!-- ===== 第二级：辅助生成 ===== -->
    <template v-else-if="view === 'generate' && selected">
      <div class="back-btn" @click="backToLibrary">‹ 返回条款库</div>
      <div class="detail-head">
        <div>
          <div class="big">{{ selected.block_name }}</div>
          <div class="muted">{{ selected.block_code }} · {{ selected.positive_count }} 用例</div>
        </div>
        <button class="btn primary" @click="startGenerate(selected.block_code)" :disabled="currentRun?.phase === 'running'">
          {{ currentRun?.phase === 'running' ? '⏳ 生成中…' : currentRun?.phase === 'done' ? '↻ 重新生成' : '⚡ 生成 BOM' }}
        </button>
      </div>

      <!-- 节点进度 -->
      <div v-if="currentRun?.statusData" class="card card-pad" style="margin-bottom:16px">
        <h3>执行进度
          <span class="tag" :class="currentRun.statusData.status === 'success' ? 'green' : currentRun.statusData.status === 'fail' ? 'red' : 'amber'">{{ currentRun.statusData.status }}</span>
          <span class="hint" v-if="currentRun.statusData.duration_ms"> · {{ Math.round(currentRun.statusData.duration_ms/1000) }}s</span>
        </h3>
        <div class="nodes">
          <details v-for="(n,i) in currentRun.statusData.nodes" :key="i" class="node" :class="{retry: n.is_retry}">
            <summary>
              <span class="seq">{{ n.is_retry ? '↻' : n.seq }}</span>
              <span class="skill">{{ skillName(n.skill) }}</span>
              <span :style="{color: n.success ? 'var(--success)' : 'var(--danger)'}">{{ n.success ? '✓' : '✗' }}</span>
              <span class="faint" style="font-size:11px">{{ n.duration_ms }}ms</span>
            </summary>
            <div style="padding:4px 0 6px 28px;font-size:12px;color:var(--muted)">{{ skillDesc(n.skill) }}</div>
          </details>
          <div v-if="currentRun.phase === 'running'" style="padding:8px 0;color:var(--primary);font-size:13px">⏳ 处理中…</div>
        </div>
        <p v-if="currentRun.error" style="color:var(--danger);font-size:13px;margin-top:8px">⚠ {{ currentRun.error }}</p>
      </div>

      <!-- BOM 输出（gen-block）-->
      <div v-if="currentRun?.result" class="card card-pad">
        <h3>BOM 输出 <button class="btn sm" style="margin-left:auto" @click="copyPrompt(currentRun.result.full_prompt?.prompt_text)">📋 复制提示词</button></h3>

        <div class="gen-block">
          <div class="bt">◆ 定义</div>
          <div class="body">{{ currentRun.result.bom.semantic_definition }}</div>
        </div>

        <div class="gen-block">
          <div class="bt">◆ 拦截规则（{{ currentRun.result.bom.extraction_rules?.absolute_interception_rules?.length }} · 分场景）</div>
          <div class="body"><ul>
            <li v-for="(r,i) in currentRun.result.bom.extraction_rules?.absolute_interception_rules" :key="i">
              <span class="tag indigo" style="margin-right:6px">{{ r.scene || '—' }}</span>{{ r.rule }}
              <div class="faint" style="font-size:11px;margin-left:4px" v-if="r.logic">逻辑：{{ r.logic }}</div>
            </li>
          </ul></div>
        </div>

        <div class="gen-block" v-if="currentRun.result.bom.extraction_rules?.poison_words?.length">
          <div class="bt">◆ 毒药词（一票否决）</div>
          <div class="body"><span class="tag red" v-for="w in currentRun.result.bom.extraction_rules.poison_words" :key="w" style="margin:0 6px 6px 0">{{ w }}</span></div>
        </div>

        <div class="gen-block">
          <div class="bt">◆ 匹配规则（{{ currentRun.result.bom.extraction_rules?.core_match_rules?.length }}）</div>
          <div class="body"><ul>
            <li v-for="(r,i) in currentRun.result.bom.extraction_rules?.core_match_rules" :key="i">
              <span class="tag indigo" style="margin-right:6px">{{ r.scene || '—' }}</span>{{ r.rule }}
              <div class="faint" style="font-size:11px" v-if="r.logic">逻辑：{{ r.logic }}</div>
            </li>
          </ul></div>
        </div>

        <div class="gen-block" v-if="currentRun.result.bom.reasoning_chain?.length">
          <div class="bt">◆ 排雷思维链</div>
          <div class="body"><ol style="padding-left:18px"><li v-for="(s,i) in currentRun.result.bom.reasoning_chain" :key="i">{{ s }}</li></ol></div>
        </div>

        <div class="gen-block">
          <div class="bt">◆ 召回画像</div>
          <div class="body">
            <div style="margin-bottom:6px"><b>正向关键词：</b> <span class="tag indigo" v-for="w in currentRun.result.bom.recall_profile?.positive_keywords" :key="w" style="margin:0 4px 4px 0">{{ w }}</span></div>
            <div style="margin-bottom:6px"><b>易混淆词：</b> <span class="tag amber" v-for="w in currentRun.result.bom.recall_profile?.confusion_words" :key="w" style="margin:0 4px 4px 0">{{ w }}</span></div>
            <div style="margin-bottom:6px"><b>章节提示：</b> {{ currentRun.result.bom.recall_profile?.section_hints?.join(' · ') }}</div>
            <div><b>语义查询：</b><ul style="margin:4px 0"><li v-for="(q,i) in currentRun.result.bom.recall_profile?.semantic_queries" :key="i">{{ q }}</li></ul></div>
          </div>
        </div>

        <div class="gen-block">
          <div class="bt">◆ 完整提示词</div>
          <div class="body" style="font-family:ui-monospace,monospace;font-size:12px;white-space:pre-wrap;max-height:300px;overflow:auto">{{ currentRun.result.full_prompt?.prompt_text }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.lib-bar { display:flex; gap:12px; margin-bottom:18px; align-items:center; flex-wrap:wrap }
.search { flex:1; display:flex; align-items:center; background:var(--surface); border:1px solid var(--border); border-radius:9px; padding:8px 13px }
.search input { border:none; outline:none; flex:1; font-size:13px; font-family:inherit; background:transparent }
.lib-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px }
.el-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px; cursor:pointer; transition:.18s; box-shadow:var(--shadow) }
.el-card:hover { transform:translateY(-2px); box-shadow:var(--shadow-lg); border-color:#c7d2fe }
.el-card .top { display:flex; align-items:flex-start; justify-content:space-between; margin-bottom:8px; gap:8px }
.el-card .ename { font-size:15px; font-weight:600; line-height:1.3 }
.el-card .meta { font-size:12px; color:var(--muted); margin:2px 0 8px }
.el-card .desc { font-size:12.5px; color:#475569; line-height:1.55; height:38px; overflow:hidden }
.el-card .stat { display:flex; justify-content:space-between; align-items:center; margin-top:13px; padding-top:12px; border-top:1px dashed var(--border) }
.el-card .stat .ver { font-size:13px; font-weight:700; color:var(--primary) }
.empty { text-align:center; padding:42px 20px; font-size:13px }
.back-btn { display:inline-flex; align-items:center; gap:6px; color:var(--muted); cursor:pointer; font-size:13px; margin-bottom:14px; font-weight:500 }
.back-btn:hover { color:var(--primary) }
.detail-head { display:flex; align-items:center; gap:14px; margin-bottom:18px; flex-wrap:wrap }
.detail-head .big { font-size:24px; font-weight:700 }
.nodes { font-size:13px }
.node { border-bottom:1px solid var(--border) }
.node.retry { padding-left:14px }
.node summary { display:flex; align-items:center; gap:10px; padding:5px 0; cursor:pointer; list-style:none }
.node summary::-webkit-details-marker { display:none }
.node .seq { width:20px; color:var(--faint); text-align:center }
.node .skill { flex:1 }
@media(max-width:980px){ .lib-grid{grid-template-columns:repeat(2,1fr)} }
@media(max-width:640px){ .lib-grid{grid-template-columns:1fr} }
</style>
