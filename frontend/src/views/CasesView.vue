<script setup>
// 用例库列表（测试集文件级管理）。
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { casesApi } from '../api/cases'

const route = useRoute()
const router = useRouter()
const cases = ref([])
const loading = ref(false)

const refresh = async () => {
  loading.value = true
  try { const data = await casesApi.list(); cases.value = data.cases || [] }
  catch {} finally { loading.value = false }
}
onMounted(async () => {
  await refresh()
  // 从条款库跳来（?block_code=X）→ 自动跳最新测试集详情（按条款筛选）
  if (route.query.block_code && cases.value.length) {
    router.replace({ path: `/cases/${cases.value[0].id}`, query: { block_code: route.query.block_code } })
  }
})

const remove = async (id) => {
  try { await casesApi.remove(id); ElMessage.success('已删除'); await refresh() } catch {}
}
</script>

<template>
  <div class="p-4 h-full flex flex-col gap-3 overflow-hidden">
    <div class="flex items-center gap-3">
      <span class="text-base font-semibold text-slate-700">用例库</span>
      <span class="text-xs text-slate-400">管理导入的测试集（每次导入一条记录，含正例/负例）</span>
    </div>

    <el-card class="flex-1 overflow-hidden" shadow="never" body-class="p-0" v-loading="loading">
      <el-table :data="cases" height="100%" empty-text="暂无导入的测试集（条款库导入测试集后自动生成）">
        <el-table-column prop="file_name" label="文件名" min-width="180" show-overflow-tooltip />
        <el-table-column label="导入时间" width="160">
          <template #default="{ row }">{{ row.imported_at ? new Date(row.imported_at).toLocaleString() : '—' }}</template>
        </el-table-column>
        <el-table-column prop="total_cases" label="总用例" width="80" align="center" />
        <el-table-column label="正例（有期望值）" width="130" align="center">
          <template #default="{ row }"><el-tag type="success" size="small">{{ row.positive_cases }}</el-tag></template>
        </el-table-column>
        <el-table-column label="负例（空）" width="100" align="center">
          <template #default="{ row }"><el-tag type="info" size="small">{{ row.negative_cases }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="clauses_count" label="覆盖条款" width="80" align="center" />
        <el-table-column label="操作" width="140" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="router.push(`/cases/${row.id}`)">详情</el-button>
            <el-popconfirm title="确认删除？将级联删除该测试集的所有用例行。" width="260" @confirm="remove(row.id)">
              <template #reference><el-button type="danger" size="small" plain>删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
