# 优化模块设计（optimize：badcase→分类→优化→diff→apply）

- **日期**：2026-07-14
- **状态**：草稿，待用户复核（brainstorm 已敲定 Q1/Q2，Q3-Q7 已提方案）
- **作者**：林大宇 + Claude（brainstorming）
- **关联**：
  - `docs/superpowers/specs/2026-07-01-tuning-loop-design.md`（4 节点调优闭环 spec，本设计**复用其 BOMDelta/PendingDelta/TuningRepository/apply 逻辑**，**聚焦重构 optimize 侧**：手填分类取代 LLM diagnose + 任务流 UI + diff）
  - `docs/frontend-design.md`（前端 SSoT，优化页 UI 对齐其设计系统）
  - AF-4 `errors.py`（优化模块的错误用 AppError 子类）

---

## 1. Context（为什么 / 与 07-01 的关系）

生成场景已成型：导入测试集 → 初始生成 BOM + 提示词。但**还不知道 badcase**——初始 BOM 跑出来的误抽/漏抽。优化模块吃 badcase → 改 BOM → 出带 diff 的新版本，把"专家手工迭代"工程化。

07-01 已有完整 4 节点（evaluate→diagnose→optimize→apply）spec，本设计**在其基础上聚焦重构 optimize 侧**，两点变化（用户 brief）：
1. **分类用"用户手填 issue_type（召回失败/抽取失败）+ 程序启发式自动判类"取代 07-01 的 LLM diagnose**（用户："系统感知不到原因，我手填"；务实档，LLM 归因留可插拔插槽）。
2. **optimize 做成和生成界面一致的任务流（列表+详情）+ diff 对比（红删绿增）**，关联源生成 BOM 任务。

非目标：evaluate（跑分导入）暂不做（badcase 由用户加工后直接导入）；diagnose 的 LLM 归因降级为"可插拔策略，默认不启用"。

---

## 2. 关键决策（Q1-Q7）

| Q | 决策 | 备注 |
|---|---|---|
| **Q1 分类** | 可插拔 `Classifier` 策略；默认 = 手填 issue_type + 程序启发式自动判类（空才判）；LLM 归因 = 未来插槽 | 取代 07-01 LLM diagnose；加分类方式 = 加策略类 |
| **Q2 badcase 导入** | 支持 2 格式（内部/现网，按列名识别）；case_type 从期望/实际派生；**无上下文** → 自动判类降级（按期望值关键词覆盖启发式，标 auto_judged） | 用户会手动加 issue_type 列 |
| **Q3 任务模型** | 复用 `pipeline_runs` 加 `mode=optimize` + 新 `OptimizeOrchestrator` | 落地时顺势抽 `BaseRunOrchestrator`（generate+optimize 共享 run 循环，2 实现才抽） |
| **Q4 diff** | `render_diff(bom_delta)` **纯函数**渲染，红删绿增，按字段组（定义/规则/毒药词/关键词/思维链） | diff 是 BOMDelta 的纯渲染，易测易换 |
| **Q5 关联** | 优化任务带 `source_bom_version_id`（= 源生成 BOM 版本 + apply 乐观锁基线）+ 反查源 run | 详情页头「源：生成任务 #X · BOM vY」 |
| **Q6 apply** | 沿用 07-01：优化产 BOMDelta→pending_deltas(pending)；应用=乐观锁+确定性合并→新 bom_version；冲突抛 `ConcurrencyError`（AF-4） | |
| **Q7 UI** | 侧边栏加第 4 项「优化任务」（/optimize/runs + /optimize/runs/:id），UI 复用生成列表+详情骨架，详情多：源关联+badcases+diff 卡片+应用按钮；badcase 导入在优化页顶部 | |

**抽象判据**（已敲定）：基类/抽象"当下共享 or 会变"才必要——BaseSkill✓、AppError✓、Classifier 接口✓（手填/启发式/LLM 多策略）、BaseRunOrchestrator（optimize 落地后 2 实现抽）；Repository 多 DB / Service ABC 不抽（假想未来）。

---

## 3. 数据流

```
[用户上传 badcase Excel（2 格式之一 + 手填 issue_type 列）]
        │
   ① badcase 导入（POST /api/tuning/badcases/import）
      ├─ 识别格式 → 统一行模型（doc_id/expected/actual/similarity/issue_type/...）
      ├─ case_type 派生：期望空+实际非空=误抽；期望非空+实际空=漏抽；都非空+相似度≈0=错抽；都非空+相似度>0=正确(不入)
      ├─ issue_type：手填照用；空 → Classifier.auto_classify(启发式)：误抽/错抽→抽取失败；漏抽+期望值命中召回关键词→抽取失败；漏抽+未命中→召回失败。标 auto_judged
      └─ 落 badcases 表（+issue_type +auto_judged +context_text[可空]）
        │
   ② 触发 optimize（POST /api/tuning/optimize）
      ├─ 入参：block_code + source_bom_version_id + badcase_ids[]（或全选该 block 未关闭 badcase）
      ├─ 建 pipeline_run(mode=optimize, source_bom_version_id) + 异步起线程跑 OptimizeOrchestrator
      └─ 返 optimize_run_id（前端轮询，同 generate）
        │
   ③ OptimizeOrchestrator（异步，commit_after_each 节点级可见）
      ├─ Skill: 聚合 badcases（按 issue_type 分组：召回失败组 / 抽取失败组）
      ├─ Skill optimize_rules（Stage1, temp0.2, 吃抽取失败组 + 源 BOM）→ 改定义/拦截/匹配/毒药词
      ├─ Skill optimize_profile（Stage2, temp0.5, 吃召回失败组 + 源 BOM）→ 改画像关键词/混淆/正例（强制保留上版 positive_examples）
      ├─ sanitize_keywords（程序化过滤，非 LLM）
      ├─ Skill assemble_delta → 产 BOMDelta（modifications[] + regression_warnings + coverage_note）
      └─ 落 pending_deltas(from_bom_version_id=源, delta_json, status=pending) + run finish(success/fail)
        │
   ④ 优化任务详情（GET /api/tuning/optimize/runs/:id）
      ├─ 任务信息（源关联 source_bom_version_id → 源 run）
      ├─ 执行进度（节点，同生成）
      ├─ badcases（本次用的）
      ├─ **diff 卡片**：render_diff(pending_delta.delta_json) → 红删绿增（定义/规则/毒药词/关键词/思维链分组）
      └─ regression_warnings 顶部告警
        │
   ⑤ 应用（POST /api/tuning/apply/:delta_id）
      ├─ 乐观锁：from_bom_version_id == clause 当前最新 bom_version_id？不等 → ConcurrencyError(409)
      ├─ apply_bom_delta(源 BOM, delta) → 确定性合并 → 新 bom_version(bom_source=optimize, previous_bom_id)
      ├─ 逐条 Modification → rule_modifications（approver/approved_at）
      └─ pending_deltas.status=approved；clause.current_version 更新
```

---

## 4. 后端逻辑（文件 + 端点）

### 端点（`api/routers/tuning.py`，新；注册到 app.py）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/tuning/badcases/import` | 上传 badcase Excel（2 格式）→ 解析+判类+落库；返 badcase 列表（含 auto_judged 标记） |
| GET | `/api/tuning/badcases?block_code=X` | 列 badcase（可改 issue_type） |
| PUT | `/api/tuning/badcases/{id}` | 改 issue_type（用户复核/覆盖自动判类） |
| POST | `/api/tuning/optimize` | 触发优化：block_code + source_bom_version_id + badcase_ids → 建 optimize run + 异步跑 |
| GET | `/api/tuning/optimize/runs?block_code=X` | 优化任务列表（每条款最新一条，同生成 list_runs 模式） |
| GET | `/api/tuning/optimize/runs/:id` | 优化任务详情（源关联 + 节点进度 + badcases + BOMDelta + diff） |
| GET | `/api/tuning/optimize/runs/:id/diff` | 单取 diff（render_diff 渲染好供前端直接渲染） |
| POST | `/api/tuning/apply/:delta_id` | 应用 → 新 bom_version（409 ConcurrencyError） |
| POST | `/api/tuning/deltas/:delta_id/reject` | 拒绝 → pending_deltas.status=rejected |

### service（`services/tuning/`，新）
- `badcase_service.py`：`import_badcases(file, block_code)`（解析+判类+落库，事务边界）、`list_badcases`、`update_issue_type`
- `optimize_service.py`：`start_optimize(db, block_code, source_bom_version_id, badcase_ids) -> optimize_run_id`（建 run+commit+起线程，**仿 generate.py:_bg_generate 模式**）、`get_optimize_run_detail`、`get_diff`
- `apply_service.py`：`run_apply(delta_id, approver) -> new_bom_version_id`（乐观锁+合并+落 bom_version/rule_modifications，事务）

### 编排 + 算法（`nodes/tuning/`，新；复用 BaseSkill+_logic 模式）
- `orchestrator.py`：`OptimizeOrchestrator(skills, repo, run_id, commit_after_each)`（**与 GenerationOrchestrator 同构**——落地时提 BaseRunOrchestrator 共享 run/retry 循环）
- `skills/classify_skill.py` + `_classify_logic.py`：聚合 badcases + Classifier 调用 → 分组
- `skills/optimize_rules_skill.py` + `_optimize_rules_logic.py`：Stage1（temp=get_temperature("stage1")，吃抽取失败组+源BOM，产定义/规则 Modification）
- `skills/optimize_profile_skill.py` + `_optimize_profile_logic.py`：Stage2（temp=get_temperature("stage2")，吃召回失败组+源BOM，产画像 Modification，强制保留 positive_examples）
- `skills/assemble_delta_skill.py`：汇总 Modification → BOMDelta + regression_warnings
- `_sanitize_keywords.py`：程序化关键词过滤（复用生成侧经验）

### 可插拔分类（`nodes/tuning/classifier.py`，新）
```python
class Classifier(Protocol):  # 可插拔策略接口
    def classify(self, badcase, source_bom) -> IssueType: ...

class HeuristicClassifier:    # 默认实现（手填优先 + 启发式判空）
    def classify(self, badcase, source_bom) -> IssueType: ...  # 见 §5 算法
# 未来：class LlmDiagnoseClassifier(Classifier): ...  # 不改调用方即可加
```

---

## 5. 算法

### 5.1 case_type 派生（导入时，纯函数）
```
expected 空 + actual 非空        → 误抽（false_positive）
expected 非空 + actual 空        → 漏抽（miss）
都非空 + similarity/score ≈ 0    → 错抽（mismatch，按 badcase 处理）
都非空 + similarity/score > 0    → 正确（不入 badcase，业务认"包含算对"）
```
> 阈值默认 0（>0 即正确）。可配（常量 `CORRECT_SIMILARITY_THRESHOLD = 0.0`）。
> 「错抽(mismatch)」归入 `CaseType.FALSE_POSITIVE`（07-01 CaseType 为 miss/fp 两值）；如需独立区分可后加 `CaseType.MISMATCH`（可延展）。issue_type 路由上 mismatch→抽取失败（抽了错的=BOM问题）。

### 5.2 issue_type 自动判类（HeuristicClassifier，对空 issue_type）
```
误抽 / 错抽                       → 抽取失败（规则匹配过头）
漏抽 + 期望值命中≥1 召回关键词    → 抽取失败（召回到了没抽出=BOM问题）
漏抽 + 期望值未命中任何召回关键词 → 召回失败（画像没覆盖）
```
- "召回关键词" = source_bom.recall_profile.positive_keywords。
- 无上下文 → 只能查"期望值"是否含关键词（降级启发式）；auto_judged=True + confidence="低"，前端可让用户一键复核/覆盖。
- 手填的 issue_type 直接用（auto_judged=False）。

### 5.3 optimize 两阶段（复刻 PoC，产 delta 而非整版）
- Stage1 optimize_rules（fix_target 含 rules）：吃【抽取失败组】badcase + 源 BOM → LLM 产定义/拦截/匹配/毒药词的 Modification（action=add/update/delete，before/after）。
- Stage2 optimize_profile（fix_target 含 recall_profile）：吃【召回失败组】+ 源 BOM → LLM 产关键词/混淆/正例 Modification，**强制保留上版 positive_examples**（防回归）。
- sanitize_keywords 程序化过滤（去停用词/过短/含数字等，复用 `_keyword_logic` 经验）。
- assemble_delta：汇总 → BOMDelta（fix_targets 由两组 badcase 是否非空决定 rules/recall_profile/both）+ regression_warnings（LLM 自评）。

### 5.4 diff（render_diff 纯函数）
```
render_diff(bom_delta) -> [DiffNode(group, items)]
  group: definition | interception | match | poison | profile_keywords | profile_confusion | reasoning | ...
  items: [{action: add/update/delete, before?, after?, target}]
```
前端按 group 渲染：definition 文本 diff（行级）；列表（规则/关键词）item 级 add(绿)/delete(红)/update(before→after)。**diff 是 BOMDelta 的纯渲染**，无副作用，单测易写。

### 5.5 apply 合并（07-01 apply_bom_delta，确定性纯函数）
`apply_bom_delta(source_bom, delta) -> new_bom`：按 Modification.type 路由到 BOM 各字段，add 追加 / delete 移除 / update 替换。纯函数，易测。乐观锁：from_bom_version_id != 当前最新 → ConcurrencyError。

---

## 6. 表 / 字段设计

### 6.1 `badcases` 表加列（alembic 新迁移 0005）
| 列 | 类型 | 说明 |
|---|---|---|
| `issue_type` | VARCHAR(16), NULL | 召回失败/抽取失败（见 enums.IssueType）；NULL=未判 |
| `auto_judged` | BOOLEAN, default 0 | 是否系统自动判类（前端复核提示） |
| `context_text` | TEXT, NULL | 上下文原文（2 格式都没有，留字段备用；现网格式可从语义项拼） |
> 复用现有 `badcases`(doc_id/case_type/expected/actual/coverage/trace_json/platform_run_id)。case_type 落派生值；trace_json 现网格式无 trace → NULL（判类降级不依赖 trace）。

### 6.2 `pipeline_runs` 复用 mode=optimize + 加 source_bom_version_id
- `mode` 已支持 optimize（PipelineMode.OPTIMIZE）。
- **加列 `source_bom_version_id`（INT NULL FK→bom_versions）**：generate run 为 NULL；optimize run = 源 BOM 版本。**理由**：优化 run 从创建就知道源，UI 详情在**运行中**就能显示「源：生成任务#X·BOM vY」（pending_delta 是跑完才产，靠它链源会运行中缺失）。pending_deltas.from_bom_version_id 镜像此值作 apply 乐观锁基线。

### 6.3 复用 `pending_deltas`（07-01，已建）
- `from_bom_version_id`（源 BOM + 乐观锁基线）、`delta_json`（BOMDelta）、`status`(pending/approved/rejected)、`reviewed_by/at`。
- 加索引 `(block_code, status)`（评审点过：optimize 列待审 delta 查询用）。

### 6.4 `enums/issue_type.py`（新，铁律9 通知杨力）
```python
class IssueType(str, Enum):
    RECALL_FAIL = "召回失败"      # 画像/召回锚点问题
    EXTRACTION_FAIL = "抽取失败"  # BOM 定义+规则问题
```
> 加类型 = 加枚举值 + Classifier/优化路由分支。**不内联 Literal**。

---

## 7. UI（前端，对齐 frontend-design.md）

### 7.1 侧边栏加「优化任务」
router 加 `/optimize/runs` + `/optimize/runs/:id`。App.vue sidebar 第 4 项。

### 7.2 优化任务列表 `/optimize/runs`（复用生成列表骨架）
- el-table：源条款 / 进度(el-progress) / 状态 / badcase 数 / 创建/更新时间 / 操作[详情]
- 每条款最新一条（同 list_runs GROUP BY）+ 轮询（任一 running）+ onUnmounted 清理（复用 useRunPoll）

### 7.3 优化任务详情 `/optimize/runs/:id`（复用生成详情骨架 + diff）
- 头部：源关联「源：生成任务 #X · BOM vY」（点回源）+ run 状态/耗时
- 执行进度（RunProgress 复用，中文化 optimize skill 名）
- badcases 卡片：本次用的 badcase 列表（doc_id/期望/实际/issue_type，auto_judged 标黄"待复核"）
- **diff 卡片（BomDiff.vue 新建）**：render_diff 的结果按字段组红删绿增；regression_warnings 顶部红告警
- 操作：[应用](popconfirm，提示乐观锁风险) [拒绝]

### 7.4 badcase 导入（优化页顶部入口）
- el-upload（2 格式自动识别）→ import → ElMessage.success("已导入 N 条，自动判类 M 条") → 列表
- 列表 issue_type 可改（el-select 召回失败/抽取失败），auto_judged 行标"自动判定·可改"

---

## 8. 错误处理（用 AF-4 AppError 子类）
- `ConcurrencyError`（apply 乐观锁冲突）→ 409
- `ClassifyFailed`（判类启发式无法判定 + 用户没填）→ 422，提示人工标注
- `DeltaConflict`（BOMDelta 合并矛盾）→ 409
- 文件格式错/缺列 → 400（HTTPException，导入校验）
- LLM/JSON 解析失败 → 重试≤2（同 generate），仍失败 → run fail（不落 pending_delta）

---

## 9. 可延展性（呼应 [[design-robust-extensible]]）
- **Classifier 可插拔**：手填/启发式默认，LLM 归因未来加策略类零改调用方。
- **BaseRunOrchestrator**：optimize 落地后，generate+optimize 2 实现共享 run/retry 循环 → 提基类（判据满足才抽）。
- **IssueType 枚举**：加分类类型 = 加枚举值 + 路由分支。
- **diff 纯函数**：换 diff 粒度/算法只改 render_diff。
- **温度可调**：optimize 两阶段复用 get_temperature(stage)（已接线）。
- 稳定接口：badcase→分类结果→BOMDelta→新BOM；内部算法（判类/两阶段/diff/合并）可换。

---

## 10. 测试
- `_logic` 纯函数单测（mock LLM）：case_type 派生（4 分支）/ HeuristicClassifier 判类（3 分支）/ optimize 两阶段产 Modification / sanitize / **apply_bom_delta 合并（delta+旧BOM→断言新BOM）** / **render_diff（delta→断言红绿结构）**
- 乐观锁并发：两 apply 同 from_bom_version_id，第二个断言 ConcurrencyError
- 端到端（需 DB+LLM）：导入 badcase → optimize → diff → apply → 新 bom_version，标 skip 手动跑

---

## 11. 文件落地清单
```
backend/src/cc_bom_generator/
├─ api/routers/tuning.py              # 新（/api/tuning/*）
├─ services/tuning/                   # 新
│  ├─ badcase_service.py / optimize_service.py / apply_service.py
├─ nodes/tuning/                      # 新
│  ├─ orchestrator.py (OptimizeOrchestrator)
│  ├─ classifier.py (Classifier Protocol + HeuristicClassifier)
│  ├─ skills/ (classify/optimize_rules/optimize_profile/assemble_delta + _logic)
│  └─ _sanitize_keywords.py
├─ schemas/                           # 复用 bom_delta.py；加优化任务/坏例导入契约（如需）
├─ enums/issue_type.py                # 新（IssueType，铁律9）
├─ db/tuning_repository.py            # 新（save_badcases/list_pending_deltas/apply_bom_delta…）
├─ db/models.py + alembic/0005        # badcases 加 issue_type/auto_judged/context_text；pending_deltas 加索引
└─ prompts/opt_stage1.txt + opt_stage2.txt  # 适配（吃 badcase+源BOM，产 Modification）
frontend/src/
├─ views/OptimizeRunsView.vue + OptimizeRunDetailView.vue  # 新（复用生成骨架）
├─ components/BomDiff.vue             # 新（render_diff 渲染）
└─ api/tuning.js                      # 新
```
> 涉及 `schemas/`、`enums/`、`db/models.py`、`prompts/` 改动 → 铁律 9 开 PR 通知杨力。

---

## 12. 与 07-01 spec 的关系
- **复用**：BOMDelta/Modification 契约、pending_deltas 表、apply_bom_delta 合并逻辑、乐观锁、TuningRepository 设计、sanitize 思路、opt_stage1/2 prompt 骨架。
- **重构/聚焦**：diagnose 的 LLM 归因 → 降级为 Classifier 可插拔策略（默认手填+启发式）；evaluate（跑分导入）→ 暂不做（badcase 直接导入）；optimize → 升格为任务流（pipeline_runs mode=optimize）+ diff + UI。
- **新增**：render_diff 纯函数、badcase 2 格式导入+case_type 派生、HeuristicClassifier、IssueType 枚举、优化任务 UI（OptimizeRunsView/Detail/BomDiff）。
