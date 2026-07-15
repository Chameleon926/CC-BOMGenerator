# 开发进度跟踪

> 开工前先读这个文件，确认对方当前进度后再开始写代码。
> 每次改完代码必须更新自己的段落。

---

## 🟦 林大宇（feature_lindayu）

### 当前任务
- **Step 2 分层重构已完成** ✅（5 阶段，5 commit；架构决策见技术文档第 10 章）
- **调优闭环 PR1（契约+DB 地基）已完成** ✅（spec+plan 落库；T1-T3 commit；alembic 0003 实跑落库）
- **generate 端到端验证 + 前端 demo + BOM 精细化升级 + 进度反馈修复 全部完成** ✅（2026-07-02）：
  - generate 验证：修 5 真 bug（编码/JSON/block_code/version）+ 异步化（POST /generate 返 run_id + status/result 端点）
  - 前端 demo：Vue3 三环节（设计/进度/输出），Vite 代理联调通，多 agent 验证
  - **generate BOM 精细化升级 T1-T6**（8 task，对标旧平台押金/封顶 prompt）：BOM 加 scene/logic/poison_words/reasoning_chain/scene_judgments/negative_examples；gen_stage1 产精细规则（few-shot 外置）；RuleCheck 读 poison_words+scene 分桶；SelfCheck 走 reasoning_chain 抓方向反/主体错；assemble 展示精细字段（示例不进）；回修链重 assemble+种子带新字段；专家 agent 审视修正 M1-M10
  - 进度反馈修复：orchestrator commit_after_each（节点级 commit），/status 实时见节点
- **下一步**：
  - **后端 B 方案已 commit + push**（`43e28b6` = origin；含 GET/runs + stop + finish守护 + selected_examples）。⚠️ **PR 待杨力 review 契约变更**（CleanedTestSet 加 PositiveExample + positive_examples；ingest 改解析全列）—— 需通知杨力
  - **前端 3 层 IA 已实现（B-0/B-1/B-2 本地 commit，待 push + runtime 联调）**：router+views+composables 骨架 + 4 页真功能（LibraryView/RunsView/RunDetailView/ConfigView）+ 删死代码；vite build 通过。下一步：push + 启后端联调（导入→生成→详情走查）+ a11y 打磨 + api 拦截器轮询降噪
  - **后端**：技术文档同步（第4章 generate 算法 + 第8章 BOM 输出对照，反映精细 BOM）+ 回归案例（押金/封顶业务正确性）+ 调优闭环 PR2（logic+prompt）

### 已完成
| 日期 | 模块 | 文件 | 说明 |
|------|------|------|------|
| 06-29 | M1 | contracts/ 全部 8 个文件 | 定义 BOM/TestSet/Diagnosis/Trace/Evaluation/GenerationState/CleanedTestSet/FullPrompt |
| 06-30 | B1-B5 | nodes/skills/ + _*_logic.py | B模块全链路（关键词→定义规则→画像→自检→组装） |
| 06-30 | LLM | llm/client.py | 双格式(OpenAI/Anthropic)，讯飞星辰API实测通过 |
| 06-30 | 重构 | nodes/orchestrator.py + skills/ | Node/Skill流水线重构(BaseSkill+7个Skill+Orchestrator+回修1次) |
| 06-30 | 测试 | test_orchestrator.py | 编排器测试4项全通过（含回修验证） |
| 06-30 | DB v1 | db/models.py + alembic 0001 | 初始6张表落地MySQL |
| 06-30 | DB v2 | db/models.py v2 + alembic 0002 | 三方审查后12张表（+clause_items/platform_runs/badcases/diagnoses/desensitization_logs），避保留字，加唯一约束 |
| 06-30 | 文档 | 技术设计文档第9章 | 12张表完整字段级说明 |
| 06-30 | 基础 | logging_config.py | 统一日志（log.info/log.error，不用debug/warn） |
| 06-30 | 基础 | db/recorder.py | 管线写库模块（已对齐v2字段名） |
| 06-30 | API | main.py | FastAPI /api/generate 接口 |
| 07-01 | Step1 | recorder.py v2 | 字段对齐models v2（run_status/bom_source/model_name/seq/before_json） |
| 07-01 | Step1 | nodes/ 清理 | 删5个旧函数式文件，逻辑移入 skills/_*_logic.py |
| 07-01 | Step1 | enums/ | 新增8个枚举统一事实源，contracts里的Literal全部替换 |
| 07-01 | Step2-阶段1 | schemas/（原contracts/） | git mv 整目录→schemas/ + nodes下13文件import替换；CLAUDE.md目录树/矩阵+技术文档3.1-3.2路径同步 |
| 07-01 | Step2-阶段2 | db/repository.py + db/__init__.py | 新增 PipelineRepository（6方法，注入session，只flush不commit）；db/__init__ 加 session_scope/get_db；recorder 暂留待阶段5删 |
| 07-01 | Step2-阶段3 | nodes/orchestrator.py + nodes/pipeline.py | 删 recorder 依赖、run(state,repo) 注入；修签名 bug（source→bom_source、删多余 json、sequence→seq）；pipeline 用 session_scope 包事务；技术文档新增第10章分层架构 |
| 07-01 | Step2-阶段4 | app.py + api/ + services/ + main.py薄壳 | main.py 拆为 create_app 工厂 + api/routers/generate.py + services/(generate\|ingest)_service.py；main.py 改启动薄壳；装 fastapi/uvicorn；路由冒烟 + HTTP /api/health 200 通过 |
| 07-01 | Step2-阶段5 | tests/（5 logic + orchestrator）+ 删 recorder | 5 坏测试 import 对齐 skills/_*_logic + schemas；test_orchestrator full/retry 改 run(state,repo)+标 skip；删 db/recorder.py；pytest collect 13 项全绿，6 项纯逻辑测试 PASSED |
| 07-01 | 调优闭环设计 | docs/superpowers/specs/2026-07-01-tuning-loop-design.md | brainstorm 5 段：4 节点独立 service(走法A) + BOMDelta 契约 + TuningRepository + alembic 0003(trace_json+pending_deltas) + 乐观锁 + root_component 归因路由 + 务实档；自审已修 4 处 |
| 07-01 | 调优闭环计划 | docs/superpowers/plans/2026-07-01-tuning-loop.md | writing-plans：三批 PR × 13 task（契约+DB / logic+prompt / service+API），每 task TDD（写测试→实现→commit），含完整代码骨架+测试 |
| 07-01 | 调优-PR1-T1 | schemas/bom_delta.py + tests/tuning/test_bom_delta.py | 新增 BOMDelta 契约（optimize 产出/apply 输入/审计源）：ModificationType 6值 + Modification(before/after/reason/diagnosis_ids 对齐 rule_modifications 审计表) + BOMDelta(block_code/from_version/fix_targets/modifications/coverage_note/regression_warnings)；TDD 2 项测试通过 |
| 07-01 | 调优-PR1-T1-fix | enums/bom_enums.py + schemas/bom_delta.py | code review 修正：ModificationType/ModificationAction 迁 enums（唯一事实源，不内联）+ 补扎实测试断言 |
| 07-01 | 调优-PR1-T2 | enums/diagnosis_enums.py + enums/__init__.py + schemas/diagnosis.py + tests/tuning/test_diagnosis_ext.py | DiagnosisResult 加 root_component（归因路由 extraction→进 optimize / dq→交新平台）+ severity（normal/fatal 严重性分级）；RootComponent/Severity 走 enums 唯一事实源不内联；TDD 2 项测试通过 + test_verify.py 回归不破 |
| 07-01 | 调优-PR1-T3 | db/models.py + alembic/versions/0003_badcase_trace_and_pending_deltas.py | Badcase 加 trace_json + 新增 PendingDelta ORM（8字段，from_bom_version_id FK 乐观锁基线）；alembic 0003 实跑 upgrade 0002→0003 落库 MySQL（pending_deltas 表 + badcases.trace_json）；TDD 2 项 ORM 冒烟通过 |
| 07-02 | generate 验证 | logging_config/pipeline/client/repository/ingest_service | 修 5 真 bug（编码 ✅emoji/JSON trailing comma/block_code 去下划线匹配/version 自增）；验证日志 docs/verification-log.md 7 条 |
| 07-02 | generate 异步+进度 | api/routers/generate.py + nodes/orchestrator.py | POST /generate 异步（run_id）+ GET /runs/{id}/status（节点进度）+ /result（BOM）；orchestrator commit_after_each 节点级 commit 实时见节点 |
| 07-02 | 前端 demo | frontend/index.html + src/App.vue + main.js | Vue3 三环节（设计/进度/输出），Vite 代理联调，轮询健壮性（超时/连续失败/clipboard 降级） |
| 07-02 | generate 升级 T1-T6 | schemas/bom.py + gen_stage1.txt + _generate_logic + rule_check + verify.txt + _verify_logic + assemble.txt + _prompt_logic + gen_stage2.txt + _profile_logic | BOM 精细化（scene/logic/poison_words/reasoning_chain/scene_judgments/negative_examples）；gen_stage1 产精细规则+思维链+判例（few-shot 外置 _fewshot_deposit_cap.txt）；RuleCheck 读 poison_words 校验误杀+scene 分桶；SelfCheck 走 reasoning_chain 抓方向反/主体错；assemble 展示精细字段（示例不进）；回修链重 assemble+种子带新字段。8 task TDD，专家 agent 审视修正 M1-M10 |
| 07-02 | 文档+gitignore | docs/superpowers/plans/2026-07-02-generate-bom-upgrade.md + verification-log + .gitignore | generate 升级计划（8 task+M1-M10）+ 验证日志（7 条）+ test/ 不入库（真实合同数据铁律5） |
| 07-06 | 前端企业级重构 | frontend/（App.vue + main.js + style.css + tailwind.config.js） | 装 Element Plus + Tailwind CSS；App.vue 重写为蓝白企业级分屏工作台（sidebar 240 + topbar 60 + 左数据预处理 el-upload/el-table + 右生成结果 el-descriptions BOM + 提示词代码块）；icon 全局注册（main.js）；scan/generate/clauses/config API 联调 |
| 07-06 | scan 持久化 | api/routers/generate.py（scan 端点）+ ingest_service.scan_clauses | scan 时存 xlsx 到 backend/data/uploads/latest.xlsx + upsert clauses 表；新增 GET /api/clauses（从 latest.xlsx scan，含 positive_count+sheets） |
| 07-06 | generate 文件可选 | api/routers/generate.py（generate 端点） | file 改 File(None) 可选；不传时用 backend/data/uploads/latest.xlsx（刷新页面也能 generate，不依赖前端 File 对象） |
| 07-08 | 前端设计文档 | docs/frontend-design.md | ui-ux-pro-max 审视 + 沉淀**前端单一事实源**：3 层 IA（条款库→任务列表→详情）+ Data-Dense Dashboard 设计系统 + 后端契约表（含 4 缺口）+ 死代码清单（2 旧组件待删 / 4 api 模块待接线）+ P0-P2 路线图 + 变更协议铁律。同步更新 progress.md 当前任务/下一步 |
| 07-08 | 后端-B 方案 | schemas/cleaned_test_set.py + generation_state.py + services/ingest_service.py + nodes/skills/(_keyword_logic/example_retrieve/rule_check/self_check/profile_build_skill) + nodes/orchestrator.py + db/repository.py + api/routers/generate.py + tests/(test_b_plan.py + test_finish_cancelled_guard.py) | 补原型 4 缺口：PositiveExample 行契约 + selected_examples 全链路带 doc_id（真实数据验证 PASS，run_result 放宽失败/取消也返）+ GET /runs(progress%) + POST /runs/{id}/stop + finish-cancelled 守护（repository 列查询绕 identity map，并发推演通过）；state.positive_examples 改名 selected_values；资深测试 24 项 pytest 全绿。**契约变更需通知杨力（铁律9）** |
| 07-08 | 前端设计评审+补遗(B-0) | docs/frontend-design.md | 资深前端 agent 评审施工图，修 4 阻塞（§3.2 status 字段名 run_status→`status` / §5.2 删无端点重试 / block_code 来源 route.query / 轮询条件）+ 新增 §13 施工补遗（跨页状态约定/字段映射/组件 props 边界/迁移顺序依赖图/router mode/错误边界/api 模块更正） |
| 07-08 | 前端 router 骨架(B-1) | frontend/src/(router/views/composables/constants)+main.js+App.vue | vue-router 3层IA骨架(4路由 createWebHistory)+App纯Shell(sidebar RouterLink+topbar+RouterView)+composables/useRunPoll(跨页 pendingRuns 单例+单run轮询 onUnmounted 清理)+constants/skill(SKILL_NAMES 去重)；vite build 通过 |
| 07-08 | 前端 views 实现(B-2) | frontend/src/(views×4 + components/RunProgress+BomPreview + api/generate.js) | LibraryView(导入scan/新增/删除popconfirm/搜索/生成→任务列表) + RunsView(el-progress+状态tag+停止popconfirm/详情+轮询+合并pendingRuns) + RunDetailView(节点进度+选取数据selected_examples+BOM折叠+提示词复制+useRunPoll) + ConfigView；删死代码 GeneratePanel/ConfigPanel；api/generate 补 list+stop；vite build 通过 |
| 07-10 | review 驱动改进 | 后端(generate/orchestrator/llm.client/3 logic) + 前端(RunProgress/RunDetailView/RunsView/LibraryView/ConfigView/constants/skill) | 列表每条款最新一条 + 失败返部分结果(selected_examples/keywords) + 温度配置接线(原硬编码 0.2/0.5/0.0 是摆设→client.get_temperature 真生效) + 失败节点 hover tooltip(可复制) + 执行中显示当前步骤名 + 更新时间列 + 生成不带回筛选 + ConfigView stage 说明/tooltips；24 测试过。LLM 配置 glm-5.2@bigmodel 跑通完整 success |
| 07-10 | 架构夯实 AF-1 | enums/bom_enums.py + db/repository.py + nodes/orchestrator.py + api/routers/generate.py + db/models.py | RunStatus 加 CANCELLED；裸串 running/cancelled/success/fail 换 RunStatus.X.value（沿用 state.bom.source.value 约定）；models 列 comment 补 cancelled。import + 24 测试 + runtime(stop finished run→400) 全过。**改 enum 走铁律9（通知杨力）** |
| 07-10 | 架构夯实 AF-2 | api/routers/(generate 拆薄 + 新建 runs/clauses/config) + app.py | 426 行 generate.py 按资源拆 4 router（generate:/generate+/health；runs:列表/停止/进度/结果+GenerateResponse；clauses:scan+CRUD；config:读写 llm.yaml）；散落函数内的 `from ...db.models import` 提到文件顶部；app.py 注册 4 个。import + 10 路由全注册 + 24 测试 + runtime(/api/clauses) 全过 |
| 07-10 | 架构夯实 AF-3 | services/generate_service.py（删）+ db/repository.py + nodes/orchestrator.py | run_generate 是旧同步模式（无 run_id/async/commit_after_each），异步重构后零代码引用→删整个文件；修正 repository/orchestrator 的误导 docstring（原谎称 HTTP 走 generate_service 管 commit，实为 generate.py:_bg_generate+session_scope+commit_after_each）。async run 模式等 optimize 落地有 2 实现再抽共享（抽象判据）。import+24测试过 |
| 07-10 | 架构夯实 AF-4 | errors.py（新）+ app.py + tests/test_errors.py（新）| 架构师版（带基类）：AppError 基类 + NotFound/ConcurrencyError/ClassifyFailed/DeltaConflict 子类；app.py 注册 `exception_handler(AppError)` 按 MRO 通吃所有子类，统一返 {detail=message(前端 .detail 兼容), code, context(可选)}。加新错误=加子类零改调用方/注册。现有 HTTPException 散抛不动，新代码（优化模块）用 AppError 子类。3 errors 测试 + 24 回归 + runtime health 全过 |
| 07-14 | 优化模块设计 spec 草稿 | docs/superpowers/specs/2026-07-14-optimization-module-design.md | brainstorm Q1(分类可插拔 Classifier：手填 issue_type+启发式判类，LLM 归因留插槽) / Q2(badcase 2 格式+case_type 派生+issue_type 自动判类) 敲定；Q3-Q7 提方案落 spec：badcase 导入→分类→optimize(pipeline_runs mode=optimize + OptimizeOrchestrator)→diff(render_diff 纯函数红删绿增)→apply(乐观锁+ConcurrencyError)；复用 07-01 BOMDelta/PendingDelta/apply_bom_delta；新增 IssueType 枚举/HeuristicClassifier/render_diff/优化任务 UI(独立 sidebar)。**待用户复核** |
| 07-15 | 优化模块阶段1 实现计划 | docs/superpowers/plans/2026-07-15-optimization-phase1-badcase-import.md | writing-plans 产出 7 task TDD bite-sized：①IssueType 枚举 ②alembic 0005(badcases 加 issue_type/auto_judged/context_text + platform_run_id 改 nullable) ③badcase 解析纯函数(格式识别+case_type 派生) ④HeuristicClassifier(启发式判类) ⑤TuningRepository ⑥badcase_service(解析→取源BOM关键词→判类→落库) ⑦tuning 路由+冒烟。阶段2-4 各自后续计划。**待执行** |
| 07-15 | 典型正例 TE-1 | schemas/bom.py + tests/test_bom_typical_examples.py | BOM 加 TypicalExample(value,reason) + typical_examples 字段（进提示词【正向抽取示例】，与召回锚点 positive_examples 分开）。3 测试+30 回归过。**BOM 契约变更，铁律9 通知杨力** |
| 07-15 | 典型正例 TE-2 | nodes/skills/_example_annotate_logic.py + example_annotate.py + prompts/example_annotate.txt + tests/test_example_consistency.py | ExampleAnnotateSkill：LLM 为 selected_examples 生成锚定 BOM 规则的分析理由（引用匹配规则解释命中+确认不触发拦截/毒药词）→ typical_examples；程序化一致性校验 check_consistency（正例被拦截规则/毒药词命中→红旗、未被匹配规则/recall关键词覆盖→红旗，复用 rule_check._extract_rule_keywords）落日志。5 一致性测试 + 35 回归过。|
| 07-15 | 典型正例 TE-3 | orchestrator.py + prompts/assemble.txt + _prompt_logic.py + api/routers/runs.py + frontend/constants/skill.js + example_annotate.txt/py | orchestrator 8 节点加 ExampleAnnotateSkill（skills+retry_skills，PromptAssemble 前）；assemble.txt 加【正向抽取示例】段（目标画像后，value+分析理由+使用规则）；_format_typical_examples；TOTAL_STEPS 7→8 + 前端 SKILL 映射/顺序/总数同步。修 example_annotate prompt 改返 {\"reasons\":[...]}（_parse_json 字典导向，裸数组会被剥 [] 失败；只返理由不回显长正例原文省 token），skill 用 values 配对。返利条款生成 success：8 节点全过，typical_examples 5 个带锚定匹配规则的理由，提示词含【正向抽取示例】+【示例使用规则】（8842 字符）。|

### 阻塞
- 暂无

### 待对方
- 杨力写 ingest.py + dedup.py + clean.py（A 模块数据预处理），交付 CleanedTestSet

---

## 🟩 杨力（feature_yangli）

### 当前任务
- （首次启动时）阅读 `docs/技术设计-生成场景后端专项.md` + `docs/progress.md` + `CLAUDE.md`
- 负责文件：`nodes/skills/_keyword_logic.py` 不属于你（那是 B 模块内部逻辑）
- **你负责的文件**（见下方协作矩阵）：
  - `nodes/skills/ingest_skill.py`（如用 Skill 模式）或 `services/ingest_service.py`
  - Excel 解析、去重、清洗 → 输出 CleanedTestSet
  - 也可以提 PR 优化 `db/repository.py`（session 管理）

### 已完成
| 日期 | 模块 | 文件 | 说明 |
|------|------|------|------|
| （待补充） | | | |

### 阻塞
- 暂无

### 待对方
- Step 2 分层重构已完成（contracts→schemas、recorder→Repository、main→api/services 分层），可基于重构结果开工
