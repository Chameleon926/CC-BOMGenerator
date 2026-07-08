<script setup>
// BOM 结构化折叠预览（任务详情用）。设计见 §5.3 + §13.3。
// 默认展开「定义」，其余收起（progressive-disclosure）。
import { ref, watch } from 'vue'

const props = defineProps({ bom: { type: Object, required: true } })
const activeNames = ref(['definition'])
watch(() => props.bom, () => { activeNames.value = ['definition'] })
</script>

<template>
  <el-collapse v-model="activeNames">
    <el-collapse-item title="语义定义" name="definition">
      <span class="text-sm leading-relaxed text-slate-600">{{ bom.semantic_definition }}</span>
    </el-collapse-item>

    <el-collapse-item v-if="bom.extraction_rules?.absolute_interception_rules?.length"
                      :title="`拦截规则（${bom.extraction_rules.absolute_interception_rules.length}）`" name="interception">
      <div class="space-y-1.5">
        <div v-for="(r, i) in bom.extraction_rules.absolute_interception_rules" :key="i">
          <el-tag type="danger" size="small" effect="plain" class="mr-1">{{ r.scene || '场景' }}</el-tag>
          <span class="text-sm text-slate-600">{{ r.rule }}</span>
          <div class="text-xs text-slate-400 ml-1" v-if="r.logic">逻辑：{{ r.logic }}</div>
        </div>
      </div>
    </el-collapse-item>

    <el-collapse-item v-if="bom.extraction_rules?.poison_words?.length"
                      :title="`毒药词（${bom.extraction_rules.poison_words.length}，一票否决）`" name="poison">
      <el-tag v-for="w in bom.extraction_rules.poison_words" :key="w" type="danger" effect="dark" size="small" class="mr-1.5 mb-1">{{ w }}</el-tag>
    </el-collapse-item>

    <el-collapse-item v-if="bom.extraction_rules?.core_match_rules?.length"
                      :title="`匹配规则（${bom.extraction_rules.core_match_rules.length}）`" name="match">
      <div class="space-y-1.5">
        <div v-for="(r, i) in bom.extraction_rules.core_match_rules" :key="i">
          <el-tag type="primary" size="small" effect="plain" class="mr-1">{{ r.scene || '场景' }}</el-tag>
          <span class="text-sm text-slate-600">{{ r.rule }}</span>
          <div class="text-xs text-slate-400 ml-1" v-if="r.logic">逻辑：{{ r.logic }}</div>
        </div>
      </div>
    </el-collapse-item>

    <el-collapse-item v-if="bom.reasoning_chain?.length" title="排雷思维链" name="chain">
      <ol class="text-sm text-slate-600 list-decimal ml-4 space-y-0.5">
        <li v-for="(s, i) in bom.reasoning_chain" :key="i">{{ s }}</li>
      </ol>
    </el-collapse-item>

    <el-collapse-item v-if="bom.recall_profile" title="召回画像" name="profile">
      <div class="space-y-1 text-sm">
        <div><span class="text-slate-400">关键词：</span>
          <el-tag v-for="w in bom.recall_profile.positive_keywords" :key="w" type="primary" effect="plain" size="small" class="mr-1 mb-0.5">{{ w }}</el-tag>
        </div>
        <div><span class="text-slate-400">易混淆：</span>
          <el-tag v-for="w in bom.recall_profile.confusion_words" :key="w" type="warning" effect="plain" size="small" class="mr-1 mb-0.5">{{ w }}</el-tag>
        </div>
        <div v-if="bom.recall_profile.section_hints?.length"><span class="text-slate-400">章节：</span>{{ bom.recall_profile.section_hints.join(' · ') }}</div>
      </div>
    </el-collapse-item>
  </el-collapse>
</template>
