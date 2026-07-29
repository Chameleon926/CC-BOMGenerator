<script setup>
// 条款库（第一级）。设计见 docs/frontend-design.md §5.1 + §13.2。
// 导入(scan) / 新增(create) / 删除(remove popconfirm) / 搜索 / 生成(→任务列表)
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { clausesApi } from '../api/clauses'
import { generateApi } from '../api/generate'
import { addPendingRun } from '../composables/useRunPoll'

const router = useRouter()
const clauses = ref([])
const loading = ref(false)
const searchQuery = ref('')
const uploadedFileName = ref('')

const createDialog = ref(false)
const createForm = ref({ block_code: '', block_name: '', domain: '' })
const creating = ref(false)

const filteredClauses = computed(() => {
  if (!searchQuery.value.trim()) return clauses.value
  const q = searchQuery.value.toLowerCase()
  return clauses.value.filter(c =>
    (c.block_name || '').toLowerCase().includes(q) || (c.block_code || '').toLowerCase().includes(q)
  )
})

const refresh = async () => {
  loading.value = true
  try { clauses.value = (await clausesApi.list()).clauses || [] }
  catch { /* 拦截器已提示 */ }
  finally { loading.value = false }
}
onMounted(refresh)

const onUploadChange = async (uploadFile) => {
  const file = uploadFile.raw || uploadFile
  if (!file) return
  uploadedFileName.value = file.name
  loading.value = true
  try {
    const data = await clausesApi.scan(file)
    ElMessage.success(`已导入 ${data.clauses?.length || 0} 条`)
    await refresh()
  } catch {} finally { loading.value = false }
}

const submitCreate = async () => {
  if (!createForm.value.block_code || !createForm.value.block_name) {
    ElMessage.warning('编码和名称必填'); return
  }
  creating.value = true
  try {
    await clausesApi.create(createForm.value)
    ElMessage.success('已新增')
    createDialog.value = false
    createForm.value = { block_code: '', block_name: '', domain: '' }
    await refresh()
  } catch {} finally { creating.value = false }
}

const removeClause = async (block_code) => {
  try { await clausesApi.remove(block_code); ElMessage.success('已删除'); await refresh() } catch {}
}

// 生成配置弹窗（用户配正例数量 + 显示可用数 + 校验）
const genDialog = ref(false)
const genRow = ref(null)
const genForm = ref({ num_examples: 5 })
const openGenerate = (row) => {
  genRow.value = row
  genForm.value.num_examples = Math.min(5, row.positive_count || 5)
  genDialog.value = true
}
const confirmGenerate = async () => {
  const row = genRow.value
  if (!row) return
  const available = row.positive_count || 0
  if (available > 0 && genForm.value.num_examples > available) {
    ElMessage.warning(`测试集只有 ${available} 个正例，无法生成 ${genForm.value.num_examples} 个`)
    return
  }
  try {
    const data = await generateApi.start({
      block_code: row.block_code, clause: row.block_name,
      num_examples: genForm.value.num_examples,
    })
    addPendingRun({ run_id: data.run_id, block_code: row.block_code, clause: row.block_name })
    genDialog.value = false
    router.push('/runs')
  } catch {}
}

// 正例预览 → 跳用例库（按条款筛选）
const openPreview = (block_code) => {
  router.push({ path: '/cases', query: { block_code } })
}
</script>

<template>
  <div class="p-4 h-full flex flex-col gap-3 overflow-hidden">
    <div class="flex items-center gap-3 flex-wrap">
      <el-upload drag :auto-upload="false" :show-file-list="false" accept=".xlsx,.xls,.csv" :on-change="onUploadChange" class="!w-auto">
        <div class="flex items-center gap-2 px-4 py-2 text-sm">
          <el-icon class="text-blue-400"><Upload /></el-icon>
          <span v-if="uploadedFileName" class="text-green-600 font-medium">{{ uploadedFileName }}</span>
          <span v-else class="text-slate-500">导入测试集</span>
        </div>
      </el-upload>
      <el-button icon="Plus" @click="createDialog = true">新增条款</el-button>
      <div class="flex-1"></div>
      <el-input v-model="searchQuery" placeholder="搜索条款名称 / 编码" prefix-icon="Search" clearable style="width:220px" :disabled="!clauses.length" />
    </div>

    <el-card class="flex-1 overflow-hidden" shadow="never" body-class="p-0" v-loading="loading">
      <el-table :data="filteredClauses" height="100%" empty-text="上传测试集后显示条款">
        <el-table-column prop="block_name" label="条款名称" min-width="140">
          <template #default="{ row }"><span class="font-medium text-slate-700">{{ row.block_name || row.block_code }}</span></template>
        </el-table-column>
        <el-table-column prop="block_code" label="编码" width="130" />
        <el-table-column prop="positive_count" label="用例" width="70" align="center" />
        <el-table-column label="版本" width="70" align="center">
          <template #default="{ row }">{{ row.current_version ? 'v' + row.current_version : '—' }}</template>
        </el-table-column>
        <el-table-column prop="source_file" label="来源" width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="170" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openPreview(row.block_code)">正例</el-button>
            <el-button type="primary" size="small" icon="Promotion" @click="openGenerate(row)">生成</el-button>
            <el-popconfirm title="确认删除？将级联清理该条款的所有 BOM / 运行记录。" width="260" @confirm="removeClause(row.block_code)">
              <template #reference><el-button type="danger" size="small" icon="Delete" plain>删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createDialog" title="新增条款" width="420">
      <el-form :model="createForm" label-width="72px">
        <el-form-item label="编码" required><el-input v-model="createForm.block_code" placeholder="如 FSB0000011" /></el-form-item>
        <el-form-item label="名称" required><el-input v-model="createForm.block_name" placeholder="如 交付模式" /></el-form-item>
        <el-form-item label="业务域"><el-input v-model="createForm.domain" placeholder="采购/销售/服务/工程/框架" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">新增</el-button>
      </template>
    </el-dialog>

    <!-- 生成配置弹窗（正例数量可配 + 显示可用数 + 校验） -->
    <el-dialog v-model="genDialog" title="生成 BOM" width="440">
      <div class="text-sm text-slate-600 mb-3">
        条款：<b>{{ genRow?.block_name || genRow?.block_code }}</b>
        <span class="text-slate-400 ml-2">{{ genRow?.block_code }}</span>
      </div>
      <el-form label-width="90px">
        <el-form-item label="正例数量">
          <el-input-number v-model="genForm.num_examples" :min="1" :max="genRow?.positive_count || 99" />
        </el-form-item>
      </el-form>
      <div class="text-xs text-slate-400 mt-1 ml-1 leading-relaxed">
        测试集有 <b class="text-slate-600">{{ genRow?.positive_count || '?' }}</b> 个正例（去重后）。<br>
        选取的正例用于：召回画像锚点 + 提示词【正向抽取示例】。
      </div>
      <template #footer>
        <el-button @click="genDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmGenerate">生成</el-button>
      </template>
    </el-dialog>

    <!-- 正例预览弹窗（区分总用例 / 正例 / 负例） -->
    <el-dialog v-model="previewDialog" :title="`正例预览 · ${previewData?.block_name || ''}`" width="720">
      <div v-if="previewData" class="space-y-3">
        <div class="flex gap-2 flex-wrap text-sm">
          <el-tag>总用例 {{ previewData.total_count || 0 }}</el-tag>
          <el-tag type="success">正例（有期望值）{{ previewData.positive_count || 0 }}</el-tag>
          <el-tag type="info">负例（空，不应抽取）{{ (previewData.total_count || 0) - (previewData.positive_count || 0) }}</el-tag>
          <el-tag type="warning" effect="plain">去重后 {{ previewData.count || 0 }}</el-tag>
        </div>
        <div class="text-xs text-slate-400 leading-relaxed">
          <b>正例</b> = 该文档包含此条款（应抽取，用于生成 BOM）；<b>负例</b> = 该文档不含此条款（不应抽取，用于防误抽校验）。
        </div>
        <el-table :data="previewData.positive_examples" size="small" max-height="420">
          <el-table-column label="文档ID" width="280">
            <template #default="{ row }"><span class="font-mono text-xs text-slate-500">{{ row.doc_id || '—' }}</span></template>
          </el-table-column>
          <el-table-column label="期望值（正例内容）">
            <template #default="{ row }"><span class="text-sm text-slate-600 whitespace-pre-wrap">{{ row.expected_value }}</span></template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else class="text-center py-8 text-slate-400">加载中...</div>
    </el-dialog>
  </div>
</template>
