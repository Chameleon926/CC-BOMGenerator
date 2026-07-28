// Skill 名中文化映射（全局唯一，列表/详情复用）。别在各组件各写一份。
// 与后端 orchestrator create_default_orchestrator() 的 7 个 Skill 顺序一致。
export const SKILL_NAMES = {
  FeatureExtractSkill:  '关键词抽取',
  ExampleRetrieveSkill: '正例挑选',
  DefinitionRuleSkill:  '定义+规则生成',
  ProfileBuildSkill:    '召回画像组装',
  RuleCheckSkill:       '规则校验',
  SelfCheckSkill:       '自检',
  ExampleAnnotateSkill: '典型正例标注',
  PromptAssembleSkill:  '提示词组装',
}

// Skill 执行顺序（与后端 create_default_orchestrator 的 skills 列表一致）。
// 用于执行中显示「当前第几步」：已完成 N 步 → 当前即第 N+1 步（SKILL_SEQUENCE[N]）。
export const SKILL_SEQUENCE = [
  'FeatureExtractSkill',
  'ExampleRetrieveSkill',
  'DefinitionRuleSkill',
  'ProfileBuildSkill',
  'RuleCheckSkill',
  'SelfCheckSkill',
  'ExampleAnnotateSkill',
  'PromptAssembleSkill',
]

export const skillName = (s) => SKILL_NAMES[s] || s

// 耗时格式化：ms → 自动 ms/s/m/h（598ms / 1.3s / 43.2s / 1m30s / 1h2m）
export const formatDuration = (ms) => {
  if (!ms || ms === 0) return '—'
  if (ms < 1000) return ms + 'ms'
  const s = ms / 1000
  if (s < 60) return s.toFixed(1) + 's'
  const m = Math.floor(s / 60)
  const remS = Math.round(s % 60)
  if (m < 60) return `${m}m${remS}s`
  const h = Math.floor(m / 60)
  const remM = m % 60
  return `${h}h${remM}m`
}

// Skill 节点总数（后端 orchestrator 8 个；与 GET /runs 的 total_steps 一致）
export const TOTAL_STEPS = 8
