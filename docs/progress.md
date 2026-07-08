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
  - **前端（以 `docs/frontend-design.md` §10 路线图为单一事实源）**：P0 vue-router 路由化（4 路由）+ 删死代码（旧 GeneratePanel.vue/ConfigPanel.vue）+ 接线 4 个 api 模块；P0 后端 commit `GET /runs` + `POST /runs/{id}/stop`；P1 任务列表/详情页 + 后端补 selected_examples
  - **后端**：技术文档同步（第4章 generate 算法 + 第8章 BOM 输出对照，反映精细 BOM）+ 回归案例（押金/封顶业务正确性）+ 调优闭环 PR2（logic+prompt）
  - **✅ 4 个后端缺口 B 方案已补**（详见 `frontend-design.md` §6.2，待 commit）：① `GET /runs` + `POST /runs/{id}/stop` 已写 ② **finish-cancelled 守护已修**（repository 列查询绕 identity map，并发推演 a/b/c/d 通过）③ `selected_examples` 全链路带 doc_id（新增 PositiveExample 行契约，真实数据验证 PASS；run_result 放宽失败/取消也返；state.positive_examples 改名 selected_values 避免同名异类型）④ stop 不真中断 Thread（已知限制，UX 文案待定）。**资深测试 24 项 pytest 全绿，PM 条件通过。契约变更需通知杨力（铁律9）**

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
