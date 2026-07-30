<script setup>
// 用例库列表（条款视角：每行=一个条款 + 用例统计 + 模糊搜索）。
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { casesApi } from '../api/cases'

const router = useRouter()
const cases = ref([])
const loading = ref(false)
const searchQuery = ref('')

const refresh = async () => {
  loading.value = true
  try {
    const data = await casesApi.list(searchQuery.value.trim())
    cases.value = data.cases || []
  } catch {} finally { loading.value = false }
}

// 搜索 debounce
let searchTimer = null
const onSearch = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(refresh, 300)
}

onMounted(refresh)
</script>

<template>
  <div class="p-4 h-full flex flex-col gap-3 overflow-hidden">
    <div class="flex items-center gap-3">
      <span class="text-base font-semibold text-slate-700">用例库</span>
      <div class="flex-1"></div>
      <el-input v-model="searchQuery" placeholder="搜索条款名称 / 编码" prefix-icon="Search" clearable
                style="width:240px" @input="onSearch" @clear="refresh" />
    </div>

    <el-card class="flex-1 overflow-hidden" shadow="never" body-class="p-0" v-loading="loading">
      <el-table :data="cases" height="100%" empty-text="无匹配条款" @row-click="(row) => router.push(`/cases/${row.block_code}`)">
        <el-table-column prop="block_name" label="条款名称" min-width="160">
          <template #default="{ row }"><span class="font-medium text-slate-700">{{ row.block_name }}</span></template>
        </el-table-column>
        <el-table-column prop="block_code" label="编码" width="140" />
        <el-table-column label="总用例" width="80" align="center">
          <template #default="{ row }">{{ row.total }}</template>
        </el-table-column>
        <el-table-column label="正例（有期望值）" width="130" align="center">
          <template #default="{ row }"><el-tag type="success" size="small">{{ row.positive }}</el-tag></template>
        </el-table-column>
        <el-table-column label="负例（空）" width="100" align="center">
          <template #default="{ row }"><el-tag type="info" size="small">{{ row.negative }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click.stop="router.push(`/cases/${row.block_code}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
