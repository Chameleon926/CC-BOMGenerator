<script setup>
// 用例详情（某条款的用例行：正例/负例标注 + 正负例 tabs 筛选）。不搜其他条款。
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { casesApi } from '../api/cases'

const props = defineProps({ id: { type: String, required: true } })  // id = block_code
const router = useRouter()

const blockName = ref('')
const rows = ref([])
const columns = ref([])
const loading = ref(false)
const filterType = ref('all')  // all | positive | negative

const loadRows = async () => {
  loading.value = true
  try {
    const data = await casesApi.rows(props.id, { filter: filterType.value })
    rows.value = data.rows || []
    blockName.value = data.block_name || props.id
    // 提取动态列（从第一条 row_data）
    if (rows.value.length && !columns.value.length) {
      columns.value = Object.keys(rows.value[0].row_data)
    }
  } catch {} finally { loading.value = false }
}

onMounted(loadRows)
watch(filterType, loadRows)
</script>

<template>
  <div class="p-4 space-y-3">
    <el-button text icon="ArrowLeft" @click="router.push('/cases')">返回用例库</el-button>

    <el-card shadow="never">
      <div class="flex items-center gap-4 text-sm flex-wrap">
        <span class="text-base font-bold text-slate-800">{{ blockName }}</span>
        <span class="text-slate-400">{{ id }}</span>
        <el-radio-group v-model="filterType" size="small">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="positive">正例</el-radio-button>
          <el-radio-button value="negative">负例</el-radio-button>
        </el-radio-group>
        <span class="text-xs text-slate-400">共 {{ rows.length }} 行</span>
      </div>
    </el-card>

    <el-card shadow="never" body-class="p-0" v-loading="loading">
      <el-table :data="rows" height="550" size="small" empty-text="无数据">
        <el-table-column label="类型" width="80" align="center" fixed>
          <template #default="{ row }">
            <el-tag :type="row.has_expected ? 'success' : 'info'" size="small">
              {{ row.has_expected ? '正例' : '负例' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-for="col in columns" :key="col" :label="col" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="text-xs text-slate-600 whitespace-pre-wrap">{{ row.row_data[col] || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="text-xs text-slate-400">
      <b>正例</b> = 该文档包含此条款（有期望值，应抽取）；<b>负例</b> = 该文档不含此条款（空期望值，不应抽取）。
    </div>
  </div>
</template>
