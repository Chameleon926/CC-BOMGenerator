# 开发进度跟踪

> 开工前先读这个文件，确认对方当前进度后再开始写代码。
> 每次改完代码必须更新自己的段落。

---

## 🟦 林大宇（feature_lindayu）

### 当前任务
- **Step 2 分层重构已完成** ✅（5 阶段，5 commit；架构决策见技术文档第 10 章）：
  - ✅ 阶段1：contracts/ → schemas/ 物理搬移 + import 替换
  - ✅ 阶段2：recorder.py → PipelineRepository 类（注入 session，run 级 UoW 事务）
  - ✅ 阶段3：orchestrator 解耦 + 修签名 bug（source→bom_source、删多余 json、sequence→seq）
  - ✅ 阶段4：main.py → app/api/routers + services 分层
  - ✅ 阶段5：修 5 个坏测试 + 删 recorder
- **调优闭环执行中（PR1 契约+DB 地基）**：spec + 计划已完成，PR1-T1 已落地（schemas/bom_delta.py BOMDelta 契约，TDD 2 项测试通过）。下一步：PR1-T2（DiagnosisResult 加 root_component/severity）→ PR1-T3（models 改 + alembic 0003）→ PR1-T4（文档同步 + 开 PR 等杨力 review）

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
