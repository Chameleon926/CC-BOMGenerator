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

const generate = async (row) => {
  try {
    const data = await generateApi.start({ block_code: row.block_code, clause: row.block_name })
    addPendingRun({ run_id: data.run_id, block_code: row.block_code, clause: row.block_name })
    // 跳任务列表（不带 block_code 筛选）：显示所有条款各自的最新一条，新生成的在顶部
    router.push('/runs')
  } catch {}
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
            <el-button type="primary" size="small" icon="Promotion" @click="generate(row)">生成</el-button>
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
  </div>
</template>
