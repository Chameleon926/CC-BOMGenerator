<script setup>
// 用例详情（完整用例行：保留原始列 + 正例/负例标注 + 按条款/正负例筛选）。
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { casesApi } from '../api/cases'

const props = defineProps({ id: { type: [String, Number], required: true } })
const route = useRoute()
const router = useRouter()

const detail = ref(null)
const rows = ref([])
const columns = ref([])        // 动态列名（从 row_data 提取）
const loading = ref(false)
const filterBlock = ref('')    // 按条款筛选
const filterType = ref('all')  // all | positive | negative

const loadRows = async () => {
  loading.value = true
  try {
    const data = await casesApi.rows(props.id, {
      block_code: filterBlock.value,
      filter: filterType.value,
    })
    rows.value = data.rows || []
    // 提取动态列（从第一条 row_data）
    if (rows.value.length && !columns.value.length) {
      columns.value = Object.keys(rows.value[0].row_data)
    }
  } catch {} finally { loading.value = false }
}

onMounted(async () => {
  try { detail.value = await casesApi.get(props.id) } catch {}
  // 从条款库跳来 → 自动按 block_code 筛选
  if (route.query.block_code) {
    filterBlock.value = route.query.block_code
  }
  await loadRows()
})

watch([filterBlock, filterType], () => loadRows())

const tagText = (s) => ({ all: '全部', positive: '正例', negative: '负例' }[s] || s)
</script>

<template>
  <div class="p-4 space-y-3">
    <el-button text icon="ArrowLeft" @click="router.push('/cases')">返回用例库</el-button>

    <el-card v-if="detail" shadow="never">
      <div class="flex items-center gap-4 text-sm flex-wrap">
        <span class="text-base font-bold text-slate-800">{{ detail.file_name }}</span>
        <el-tag>总用例 {{ detail.total_cases }}</el-tag>
        <el-tag type="success">正例 {{ detail.positive_cases }}</el-tag>
        <el-tag type="info">负例 {{ detail.negative_cases }}</el-tag>
        <el-tag type="warning" effect="plain">覆盖条款 {{ detail.clauses_count }}</el-tag>
        <span class="text-xs text-slate-400" v-if="detail.imported_at">{{ new Date(detail.imported_at).toLocaleString() }}</span>
      </div>
    </el-card>

    <!-- 筛选 -->
    <div class="flex items-center gap-3 flex-wrap">
      <el-select v-model="filterBlock" placeholder="全部条款" clearable filterable style="width:240px">
        <el-option v-for="bc in detail?.block_codes || []" :key="bc" :label="bc" :value="bc" />
      </el-select>
      <el-radio-group v-model="filterType">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="positive">正例</el-radio-button>
        <el-radio-button value="negative">负例</el-radio-button>
      </el-radio-group>
      <span class="text-xs text-slate-400">共 {{ rows.length }} 行</span>
    </div>

    <!-- 用例表格（动态列 + 正例/负例标签） -->
    <el-card shadow="never" body-class="p-0" v-loading="loading">
      <el-table :data="rows" height="500" size="small" empty-text="无数据">
        <!-- 正例/负例标签列 -->
        <el-table-column label="类型" width="80" align="center" fixed>
          <template #default="{ row }">
            <el-tag :type="row.has_expected ? 'success' : 'info'" size="small">
              {{ row.has_expected ? '正例' : '负例' }}
            </el-tag>
          </template>
        </el-table-column>
        <!-- 动态原始列 -->
        <el-table-column v-for="col in columns" :key="col" :prop="`row_data.${col}`" :label="col" min-width="140" show-overflow-tooltip>
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
