<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const API = '/api'

// ===== 侧边栏菜单 =====
const activeMenu = ref('generate')
const menuItems = [
  { key: 'generate', label: 'BOM 生成工作台', icon: 'MagicStick' },
  { key: 'config', label: '模型配置', icon: 'Setting' },
]

// ===== 左半屏：数据预处理 =====
const fileName = ref('')
const uploadedFile = ref(null)
const clauses = ref([])
const scanning = ref(false)
const selectedClause = ref(null)
const searchQuery = ref('')

const onUploadChange = async (uploadFile) => {
  const file = uploadFile.raw || uploadFile
  if (!file) return
  uploadedFile.value = file
  fileName.value = file.name
  scanning.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const { data } = await axios.post(`${API}/testset/scan`, form)
    clauses.value = data.clauses
    if (data.clauses.length) selectedClause.value = data.clauses[0]
  } catch (e) {
    ElMessage.error('扫描失败：' + (e.response?.data?.detail || e.message))
  } finally {
    scanning.value = false
  }
}

const filteredClauses = computed(() => {
  if (!searchQuery.value.trim()) return clauses.value
  const q = searchQuery.value.toLowerCase()
  return clauses.value.filter(c =>
    (c.block_name || '').toLowerCase().includes(q) || c.block_code.toLowerCase().includes(q)
  )
})

// ===== 右半屏：生成 =====
const runs = reactive({})
const startGenerate = async (block_code) => {
  const c = clauses.value.find(c => c.block_code === block_code)
  if (!c) return
  const r = reactive({ run_id: null, phase: 'running', statusData: null, result: null, error: '', pollTimer: null })
  runs[block_code] = r
  const form = new FormData()
  form.append('clause', c.block_name)
  form.append('block_code', c.block_code)
  try {
    const { data } = await axios.post(`${API}/generate`, form)
    r.run_id = data.run_id
    startPoll(block_code, r)
  } catch (e) {
    r.phase = 'error'
    r.error = e.response?.data?.detail || e.message
  }
}
const startPoll = (bc, r) => {
  const start = Date.now()
  let fails = 0
  r.pollTimer = setInterval(async () => {
    if (Date.now() - start > 5 * 60 * 1000) { stopPoll(r); r.phase = 'error'; r.error = '超时'; return }
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
    } catch (e) { fails++; if (fails >= 5) { stopPoll(r); r.phase = 'error'; r.error = '连接中断' } }
  }, 2000)
}
const stopPoll = (r) => { if (r?.pollTimer) { clearInterval(r.pollTimer); r.pollTimer = null } }

const currentRun = computed(() => selectedClause.value ? runs[selectedClause.value.block_code] : null)
const currentBom = computed(() => currentRun.value?.result?.bom)
const currentPrompt = computed(() => currentRun.value?.result?.full_prompt?.prompt_text || '')

const SKILL_NAMES = {
  FeatureExtractSkill: '关键词抽取', ExampleRetrieveSkill: '正例挑选',
  DefinitionRuleSkill: '定义+规则生成', ProfileBuildSkill: '召回画像',
  RuleCheckSkill: '规则校验', SelfCheckSkill: '自检', PromptAssembleSkill: '提示词组装',
}
const skillName = s => SKILL_NAMES[s] || s

const copyPrompt = async () => {
  if (!currentPrompt.value) return
  try { await navigator.clipboard.writeText(currentPrompt.value); ElMessage.success('提示词已复制') }
  catch { ElMessage.error('复制失败') }
}

// 初始化：从后端取已持久化的条款列表（刷新页面不丢）
onMounted(async () => {
  try {
    const { data } = await axios.get(`${API}/clauses`)
    if (data.clauses?.length) {
      clauses.value = data.clauses.map(c => ({
        block_code: c.block_code,
        block_name: c.block_name,
        positive_count: 0,
        sheets: [],
      }))
    }
  } catch (e) { /* 后端未起或无数据 */ }
})
</script>

<template>
  <div class="h-screen flex overflow-hidden bg-slate-50">
    <!-- ===== 左侧 Sidebar 240px ===== -->
    <aside class="w-60 bg-white border-r border-slate-200 flex flex-col flex-shrink-0">
      <!-- Logo -->
      <div class="h-15 flex items-center gap-2.5 px-5 border-b border-slate-100" style="height:60px">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center text-white text-base font-bold" style="background:linear-gradient(135deg,#409EFF,#7c3aed)">
          <el-icon><Monitor /></el-icon>
        </div>
        <div>
          <div class="text-sm font-bold text-slate-800 leading-tight">语义 BOM 工作台</div>
          <div class="text-xs text-slate-400">BOM Generator Studio</div>
        </div>
      </div>
      <!-- 菜单 -->
      <nav class="flex-1 py-3 px-2.5 space-y-1">
        <div v-for="item in menuItems" :key="item.key"
             class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg cursor-pointer text-sm font-medium transition-all"
             :class="activeMenu === item.key
               ? 'bg-blue-500 text-white shadow-md shadow-blue-500/30'
               : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'"
             @click="activeMenu = item.key">
          <el-icon :size="17"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </div>
      </nav>
    </aside>

    <!-- ===== 右侧主体 ===== -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- 顶栏 60px -->
      <header class="h-15 bg-white border-b border-slate-200 flex items-center px-6 gap-3 flex-shrink-0" style="height:60px">
        <span class="text-base font-semibold text-slate-700">BOM 生成工作台</span>
        <span class="text-slate-300">/</span>
        <span class="text-sm text-slate-400">{{ selectedClause?.block_name || '请上传测试集' }}</span>
        <div class="flex-1"></div>
        <el-tag type="success" effect="light" round>
          <el-icon class="mr-1"><CircleCheckFilled /></el-icon> 模型已连接
        </el-tag>
      </header>

      <!-- ===== 主工作区：左右分屏 ===== -->
      <main class="flex-1 overflow-hidden p-4">
        <div class="h-full flex gap-4">

          <!-- ===== 左半屏：数据预处理 ===== -->
          <section class="w-1/2 flex flex-col gap-3 overflow-hidden">
            <!-- 上传 -->
            <el-upload
              class="block"
              drag
              :auto-upload="false"
              :show-file-list="false"
              accept=".xlsx,.xls,.csv"
              :on-change="onUploadChange"
            >
              <div class="flex flex-col items-center py-4">
                <el-icon class="text-3xl text-blue-400 mb-2"><Upload /></el-icon>
                <div class="text-sm text-slate-500" v-if="!fileName">拖拽或点击上传测试集 Excel（多 sheet / 多条款）</div>
                <div class="text-sm text-green-600 font-medium" v-else>✓ {{ fileName }}</div>
              </div>
            </el-upload>

            <!-- 去重统计 -->
            <div v-if="clauses.length" class="flex gap-2 flex-wrap">
              <el-tag type="primary" effect="plain">条款数：{{ clauses.length }}</el-tag>
              <el-tag type="success" effect="plain">总用例：{{ clauses.reduce((s, c) => s + c.positive_count, 0) }}</el-tag>
              <el-tag type="info" effect="plain">完成：{{ Object.values(runs).filter(r => r.phase === 'done').length }}</el-tag>
            </div>

            <!-- 条款列表（el-table）-->
            <el-card class="flex-1 overflow-hidden" shadow="never" body-class="p-0">
              <template #header>
                <div class="flex items-center justify-between">
                  <span class="text-sm font-semibold text-slate-600">条款 / 要素列表</span>
                  <el-input v-model="searchQuery" placeholder="搜索..." prefix-icon="Search" clearable size="small" style="width:160px" :disabled="!clauses.length" />
                </div>
              </template>
              <el-table :data="filteredClauses" highlight-current-row size="small"
                        @current-change="(row) => row && (selectedClause = row)"
                        :row-class-name="({ row }) => selectedClause?.block_code === row.block_code ? 'current-row' : ''"
                        height="100%" empty-text="上传测试集后显示条款">
                <el-table-column prop="block_name" label="条款名称" min-width="120">
                  <template #default="{ row }">
                    <span class="font-medium text-slate-700">{{ row.block_name || row.block_code }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="block_code" label="编码" width="120" />
                <el-table-column prop="positive_count" label="用例" width="60" align="center" />
                <el-table-column label="状态" width="90" align="center">
                  <template #default="{ row }">
                    <el-tag v-if="runs[row.block_code]?.phase === 'done'" type="success" size="small">已生成</el-tag>
                    <el-tag v-else-if="runs[row.block_code]?.phase === 'running'" type="warning" size="small">生成中</el-tag>
                    <el-tag v-else-if="runs[row.block_code]?.phase === 'error'" type="danger" size="small">失败</el-tag>
                    <el-tag v-else type="info" size="small">待生成</el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>
          </section>

          <!-- ===== 右半屏：生成结果 ===== -->
          <section class="w-1/2 flex flex-col gap-3 overflow-y-auto pr-1">
            <!-- 操作栏 -->
            <div class="flex items-center gap-3">
              <div class="flex-1">
                <div class="text-lg font-bold text-slate-800">{{ selectedClause?.block_name || '选择左侧条款' }}</div>
                <div class="text-xs text-slate-400" v-if="selectedClause">{{ selectedClause.block_code }} · {{ selectedClause.positive_count }} 用例</div>
              </div>
              <el-button type="primary" size="default" icon="Promotion" :loading="currentRun?.phase === 'running'"
                         :disabled="!selectedClause || !uploadedFile"
                         @click="startGenerate(selectedClause.block_code)">
                {{ currentRun?.phase === 'done' ? '重新生成' : '🚀 生成语义 BOM' }}
              </el-button>
            </div>

            <!-- 进度 -->
            <el-card v-if="currentRun?.statusData" shadow="never">
              <div class="flex items-center gap-2 mb-3">
                <span class="text-sm font-semibold text-slate-600">执行进度</span>
                <el-tag :type="currentRun.statusData.status === 'success' ? 'success' : currentRun.statusData.status === 'fail' ? 'danger' : 'warning'" size="small">
                  {{ currentRun.statusData.status }}
                </el-tag>
                <span class="text-xs text-slate-400" v-if="currentRun.statusData.duration_ms">· {{ Math.round(currentRun.statusData.duration_ms / 1000) }}s</span>
              </div>
              <div class="space-y-1.5">
                <div v-for="(n, i) in currentRun.statusData.nodes" :key="i"
                     class="flex items-center gap-2 text-xs py-1" :class="{ 'pl-4 text-orange-500': n.is_retry }">
                  <span class="w-5 text-slate-400 text-center">{{ n.is_retry ? '↻' : n.seq }}</span>
                  <span class="flex-1 text-slate-600">{{ skillName(n.skill) }}</span>
                  <el-icon :color="n.success ? '#16a34a' : '#dc2626'">
                    <CircleCheckFilled v-if="n.success" /><WarningFilled v-else />
                  </el-icon>
                  <span class="text-slate-300 w-12 text-right">{{ n.duration_ms }}ms</span>
                </div>
                <div v-if="currentRun.phase === 'running'" class="text-blue-500 text-xs py-1 flex items-center gap-1">
                  <el-icon class="is-loading"><Loading /></el-icon> 处理中…
                </div>
              </div>
            </el-card>

            <!-- BOM 结构化预览 -->
            <el-card v-if="currentBom" shadow="never">
              <template #header>
                <span class="text-sm font-semibold text-slate-600">BOM 结构化预览</span>
                <span class="text-xs text-slate-400 ml-2">v{{ currentBom.version }}</span>
              </template>
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="语义定义">
                  <span class="text-sm leading-relaxed text-slate-600">{{ currentBom.semantic_definition }}</span>
                </el-descriptions-item>
                <el-descriptions-item v-if="currentBom.extraction_rules?.absolute_interception_rules?.length" label="拦截规则">
                  <div class="space-y-1.5">
                    <div v-for="(r, i) in currentBom.extraction_rules.absolute_interception_rules" :key="i">
                      <el-tag type="danger" size="small" effect="plain" class="mr-1">{{ r.scene || '场景' }}</el-tag>
                      <span class="text-sm text-slate-600">{{ r.rule }}</span>
                      <div class="text-xs text-slate-400 ml-1" v-if="r.logic">逻辑：{{ r.logic }}</div>
                    </div>
                  </div>
                </el-descriptions-item>
                <el-descriptions-item v-if="currentBom.extraction_rules?.poison_words?.length" label="毒药词">
                  <el-tag v-for="w in currentBom.extraction_rules.poison_words" :key="w" type="danger" effect="dark" size="small" class="mr-1.5 mb-1">{{ w }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item v-if="currentBom.extraction_rules?.core_match_rules?.length" label="匹配规则">
                  <div class="space-y-1.5">
                    <div v-for="(r, i) in currentBom.extraction_rules.core_match_rules" :key="i">
                      <el-tag type="primary" size="small" effect="plain" class="mr-1">{{ r.scene || '场景' }}</el-tag>
                      <span class="text-sm text-slate-600">{{ r.rule }}</span>
                      <div class="text-xs text-slate-400 ml-1" v-if="r.logic">逻辑：{{ r.logic }}</div>
                    </div>
                  </div>
                </el-descriptions-item>
                <el-descriptions-item v-if="currentBom.reasoning_chain?.length" label="排雷思维链">
                  <ol class="text-sm text-slate-600 list-decimal ml-4 space-y-0.5">
                    <li v-for="(s, i) in currentBom.reasoning_chain" :key="i">{{ s }}</li>
                  </ol>
                </el-descriptions-item>
                <el-descriptions-item v-if="currentBom.recall_profile" label="召回画像">
                  <div class="space-y-1 text-sm">
                    <div><span class="text-slate-400">关键词：</span>
                      <el-tag v-for="w in currentBom.recall_profile.positive_keywords" :key="w" type="primary" effect="plain" size="small" class="mr-1 mb-0.5">{{ w }}</el-tag>
                    </div>
                    <div><span class="text-slate-400">易混淆：</span>
                      <el-tag v-for="w in currentBom.recall_profile.confusion_words" :key="w" type="warning" effect="plain" size="small" class="mr-1 mb-0.5">{{ w }}</el-tag>
                    </div>
                    <div><span class="text-slate-400">章节：</span>{{ currentBom.recall_profile.section_hints?.join(' · ') }}</div>
                  </div>
                </el-descriptions-item>
              </el-descriptions>
            </el-card>

            <!-- 完整提示词（代码块 + 复制）-->
            <el-card v-if="currentPrompt" shadow="never">
              <template #header>
                <div class="flex items-center justify-between">
                  <span class="text-sm font-semibold text-slate-600">完整提示词（粘新平台跑分）</span>
                  <el-button type="primary" size="small" plain icon="CopyDocument" @click="copyPrompt">复制</el-button>
                </div>
              </template>
              <pre class="text-xs leading-relaxed overflow-auto max-h-72 p-3 rounded font-mono"
                   style="background:#0f172a;color:#e2e8f0">{{ currentPrompt }}</pre>
            </el-card>

            <!-- 空状态 -->
            <div v-if="!currentRun" class="flex-1 flex flex-col items-center justify-center text-slate-300">
              <el-icon :size="40" class="mb-3"><MagicStick /></el-icon>
              <div class="text-sm">选择左侧条款并点击「生成语义 BOM」</div>
            </div>
          </section>

        </div>
      </main>
    </div>
  </div>
</template>
