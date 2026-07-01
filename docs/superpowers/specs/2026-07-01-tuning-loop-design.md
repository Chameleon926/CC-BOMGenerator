# 调优闭环（diagnose → optimize → apply → evaluate）设计文档

- **日期**：2026-07-01
- **状态**：已 brainstorm 认可，待写实现计划（writing-plans）
- **作者**：林大宇 + Claude（brainstorming）
- **关联**：技术设计文档第 10 章（分层架构）、第 10.5 节（路线图决策：调优闭环优先）

---

## 1. Context（为什么做这个）

Step 2 分层重构完成后，路线图从原「Step 3 Agent 化」调整为「调优闭环」（技术文档 10.5 节记录了砍 Agent 化的决策）。理由：BOM 生成本质是确定性管线，Agent 化是过度工程；而 **`diagnose → optimize → apply → evaluate` 调优闭环才是「保障准确率」的核心引擎**——把 PoC 的 52%→72% 手工迭代，工程化成半自动的可审计闭环。

PoC 的真实调优方式（`quick_poc/rule_pipeline.py`）：人填 `sample_slice.yaml`（badcase+trace）→ LLM 两阶段（Stage1 归因+改规则、Stage2 改画像）→ 人粘新平台跑分。本设计把这套**半自动专家调优**工程化，不做全自动闭环。

**业务前提**（关键）：抽取（Extraction）和数据质量校验（DQ）是解耦的——**我们的 BOM 只喂新平台的 Extraction；DQ 是新平台侧独立组件，不消费我们的 BOM**。因此调优闭环只处理 Extraction 侧（改 BOM），DQ 错例标注后交新平台团队。

---

## 2. 目标与非目标

### 目标
- 4 节点 `diagnose → optimize → apply → evaluate` 全链路后端实现
- 吃 badcase → 归因 → 改规则 → 应用新版 → 跑分回归 的半自动闭环
- 全过程信息持久化 + API 暴露，支撑前端「调优成效」页可视化
- 复用 PoC 已验证的轻量链路（trace 归因 + LLM + 程序化校验 + 人审）

### 非目标（YAGNI，明确不做）
- ❌ 向量库 / Hard Negative Mining（CLAUDE.md：Phase 2 再评估）
- ❌ 微调 SLM 探针 / SRL 模型（无标注数据+训练基建）
- ❌ Shadow Mode 热更新 / CI/CD 引擎（当前跑分仍人工导入，远未到此阶段）
- ❌ Meta-Agent 多工具自主调用（已砍 Agent 化）
- ❌ 全自动闭环（防回归需人审，optimize/apply 必须人触发）
- ❌ 改新平台 DQ 组件（不归本系统）

---

## 3. 关键决策（brainstorm 拍板）

| 决策点 | 选定 | 备选 / 否决理由 |
|---|---|---|
| **范围** | 完整 4 节点设计到一个 spec，分阶段实现 | 聚焦单节点会丢契约一致性 |
| **技术深度** | 务实档（复用 PoC 轻量链路，无重型依赖） | 重型档与 10.5 决策+金律 4.1 冲突 |
| **触发方式** | 半自动链式：evaluate/diagnose 自动，optimize/apply 人审 | 全自动无防回归保障；全手动太繁 |
| **optimize 产出** | BOMDelta 改动清单（补轻量契约） | 整版 BOM 无法填 rule_modifications 审计表、diff 不直观 |
| **架构走法** | 走法 A：4 节点独立 service + DB 链串联 | B（单 Orchestrator 流水线）人审断点难处理；C（扩展 GenerationOrchestrator）形态不符 |
| **仓储** | 新建 TuningRepository（与 PipelineRepository 并列） | 扩 PipelineRepository 会变 God Class |
| **apply 事务** | service 层 UoW 事务（非 Repository @Transactional） | 保持与 Step 2 事务模式一致 |
| **trace 存储** | badcases 加 trace_json 列（alembic 0003） | 独立表过度；不存则 diagnose 降级 |
| **待审 delta 存储** | 新建 pending_deltas 表（alembic 0003） | 复用 bom_versions.draft 语义不符 |
| **并发控制** | 乐观锁（from_bom_version_id 校验，先赢原则） | 悲观锁过度（调优低频） |
| **DQ 归因** | diagnose 输出 root_component(extraction/dq) 路由，dq 不进 optimize | target_module 进 delta 会伪造不存在的 DQ 落点 |

---

## 4. 整体架构（走法 A）

4 节点各自独立 service + API 端点，**节点间只通过 DB 关联**（badcases/diagnoses/pending_deltas/bom_versions/rule_modifications），不共享内存 state。人审断点是一等公民（DB 持久化等审批）。内部复用 `BaseSkill + _logic` 薄壳模式；仓储复用 Step 2 的 UoW 模式（注入 session、只 flush 不 commit、service 管事务）。

### 数据流

```
[人工上传跑分 Excel/CSV/JSON]
        │
        ▼
   ① evaluate（自动，非 LLM）  services/tuning/evaluate_service
      ├─ 落 platform_runs（accuracy/miss/fp/platform_batch）
      ├─ 落 badcases（doc_id/case_type/expected/actual/coverage/trace_json）
      └─ 对比上一版 platform_run → OptGain（fixed/regressed/net）
        │
        ▼
   ② diagnose（自动 batch，用 LLM） services/tuning/diagnose_service
      ├─ 取 trace(StructuredTrace) + badcase + 当前 BOM
      ├─ LLM 归因（复用 PoC opt_stage1 判定逻辑）
      │   → 5 类 category + root_cause + fix_target + root_component(extraction/dq) + severity(normal/fatal)
      └─ 落 diagnoses（1 badcase : 1 diagnosis）
        │
        ▼
   【人审 diagnosis —— 可视化：归因分布 + trace 证据 + 方向性 Fatal 标红】
        │  （root_component=dq 的不进 optimize，交新平台 DQ 团队）
        ▼
   ③ optimize（人触发，用 LLM 两阶段） services/tuning/optimize_service
      ├─ 吃 extraction 类 diagnosis 聚合 + 当前 BOM + few-shot
      ├─ Stage1(temp0.2) 改定义/规则 → Modification(DEFINITION/INTERCEPTION/MATCH)
      ├─ Stage2(temp0.5) 改画像 → Modification(KEYWORD/CONFUSION/PROFILE)，强制保留上版 positive_examples
      ├─ sanitize_keywords 程序化过滤（非 LLM）
      └─ 产 BOMDelta（含 regression_warnings）→ 落 pending_deltas(status=pending)
        │
        ▼
   【人审 BOMDelta —— 可视化：diff 视图 + 防回归告警】
        │
        ▼
   ④ apply（人确认，非 LLM 确定性合成） services/tuning/apply_service
      ├─ 乐观锁校验：from_bom_version_id == 当前 clause 最新 bom_version_id？
      ├─ BOMDelta + 旧 BOM → 确定性合并 → 新 bom_version（bom_source=optimize, previous_bom_id 串联）
      ├─ 逐条 Modification → rule_modifications（填 approver/approved_at）
      └─ clause.current_version 更新；pending_deltas.status=approved
        │
        ▼
   [新版本回新平台跑分] → 再次 ① evaluate（闭环兜底：OptGain.regressed 监控回归）
```

---

## 5. 契约设计

### 5.1 新增 `schemas/bom_delta.py`（林大宇 ownership）

```python
class ModificationType(str, Enum):
    DEFINITION = "definition"          # 语义定义
    INTERCEPTION = "interception"      # 拦截规则 absolute_interception_rules
    MATCH = "match"                    # 匹配规则 core_match_rules
    KEYWORD = "positive_keywords"      # 正向关键词
    CONFUSION = "confusion_words"      # 易混淆词
    PROFILE = "profile"                # 画像其余（section_hints/semantic_queries/positive_examples）

class Modification(BaseModel):
    type: ModificationType
    action: str = "update"             # add / update / delete
    target: str = ""                   # 定位锚点（某条 rule 文本 / 某关键词原文）
    before: dict | None = None         # 改前片段（对齐 rule_modifications.before_json）
    after: dict | None = None          # 改后片段（对齐 rule_modifications.after_json）
    reason: str = ""                   # 改动依据
    diagnosis_ids: list[str] = []      # 反向追溯到触发 badcase

class BOMDelta(BaseModel):
    block_code: str
    from_version: int                  # 基于的版本号（给 LLM/人看）；存库时 service 转 from_bom_version_id
    fix_targets: list[FixTarget]       # 聚合自 diagnosis，决定改 rules/recall_profile/both
    modifications: list[Modification] = []
    coverage_note: str = ""            # LLM 自评覆盖率影响
    regression_warnings: list[str] = []  # 防回归告警
```

### 5.2 扩展 `schemas/diagnosis.py`（林大宇 ownership）

`DiagnosisResult` 新增两字段（归因路由 + 严重性分级）：

```python
root_component: Literal["extraction", "dq"] = "extraction"
    # extraction → 进 optimize；dq → 标注交新平台 DQ 团队
severity: Literal["normal", "fatal"] = "normal"
    # fatal = 方向/主体/金额反转类错误（业务致命风险）
```

### 5.3 复用现有契约
- `evaluation.py`：RunResult / OptGain / Metrics（全复用，字段够）
- `trace.py`：TraceIO / StructuredTrace（全复用，diagnose 的归因证据源）
- `bom.py`：BOM / ExtractionRules / RecallProfile（apply 合成目标）

---

## 6. 四节点设计

### 6.1 evaluate（自动，非 LLM）
- **输入**：上传跑分文件（Excel/CSV/JSON）+ block_code + bom_version_id
- **输出**：落 platform_runs（1）+ badcases（N）+ OptGain
- **算法**：解析文件 → 落 platform_runs/badcases；取该 block 上一版 platform_run，按 `doc_id+case_type` 对齐 badcase 集合 → fixed（旧错∩新对）/ regressed（旧对∩新错）/ net
- **仓储**：`save_platform_run` / `save_badcases` / `get_previous_run` / `compare_runs`
- **prompt**：无

### 6.2 diagnose（自动 batch，用 LLM）
- **输入**：一批未诊断 badcases（含 trace）+ 当前 BOM
- **输出**：每 badcase 一条 DiagnosisResult → 落 diagnoses
- **算法**：复用 PoC `opt_stage1.txt` 判定——`trace.context_window→召回` / `model_reasoning→大模型推理` / `prompt 输入输出→模板` / `规则本身→BOM` / `多因→混合`；并判 `root_component` + `severity`；无 trace 降级（trace_available=false，confidence=低）
- **仓储**：`list_undiagnosed_badcases` / `save_diagnosis`
- **prompt**：`prompts/diagnose.txt`（**新建**，从 PoC `opt_stage1.txt` 抽出归因判定部分 + root_component/severity；与 optimize 解耦，单独产出 DiagnosisResult）

### 6.3 optimize（人触发，用 LLM 两阶段）
- **输入**：block_code + from_bom_version_id + diagnosis_ids[]（extraction 类）+ few-shot
- **输出**：BOMDelta → 落 pending_deltas(status=pending)
- **算法**（复刻 PoC 两阶段，产出 delta 而非整版）：
  - Stage1（temp 0.2，fix_target∈{rules,both}）：定义/规则改动
  - Stage2（temp 0.5，fix_target∈{recall_profile,both}）：画像改动，**强制保留上版 positive_examples**
  - sanitize_keywords 程序化过滤（非 LLM，复用 PoC）
  - LLM 自评 regression_warnings
- **仓储**：`save_pending_delta`
- **prompt**：`prompts/opt_stage1.txt`（改规则，吃已确认 diagnosis；基于 PoC 适配）+ `prompts/opt_stage2.txt`（改画像；复用 PoC）

### 6.4 apply（人确认，非 LLM 确定性合成）
- **输入**：approved pending_delta_id + approver
- **输出**：new bom_version_id
- **算法**：
  1. 乐观锁：`clause` 当前最新 bom_version_id == pending_delta.from_bom_version_id？不等 → ConcurrencyError
  2. 取旧 BOM（from_bom_version_id 的 full_bom_json）+ BOMDelta.modifications → 确定性合并新 BOM
  3. 落 bom_versions（bom_source=optimize, previous_bom_id, bom_status=reviewed）
  4. 逐条 Modification 落 rule_modifications（operator/approver/approved_at）
  5. clause.current_version 更新；pending_deltas.status=approved
- **仓储**：`get_pending_delta` / `apply_bom_delta`（核心，事务内五步）/ `reject_pending_delta`
- **prompt**：无

---

## 7. 持久层

### 7.1 新建 `db/tuning_repository.py`

`class TuningRepository(session)`，注入 session、方法只 flush 不 commit（同 PipelineRepository）。方法清单：

| 节点 | 方法 |
|---|---|
| evaluate | `save_platform_run` / `save_badcases` / `get_previous_run` / `compare_runs` |
| diagnose | `list_undiagnosed_badcases` / `save_diagnosis` |
| optimize | `save_pending_delta` / `get_pending_delta` |
| apply | `apply_bom_delta(delta_id, approver)`（核心，docstring 注明必须在调用方事务内）/ `reject_pending_delta` |

apply 落 bom_version/rule_modifications 的逻辑在 TuningRepository 内自包含，不跨类调 PipelineRepository。

### 7.2 alembic 0003 DDL（轻量）

```sql
-- badcases 加 trace 列
ALTER TABLE badcases
  ADD COLUMN trace_json JSON NULL COMMENT '解析后的 StructuredTrace（无 trace 则 NULL，diagnose 降级）';

-- pending_deltas 待审队列
CREATE TABLE pending_deltas (
  id                 INT PRIMARY KEY AUTO_INCREMENT,
  block_code         VARCHAR(64) NOT NULL,
  from_bom_version_id INT NOT NULL COMMENT '乐观锁基线',
  delta_json         JSON NOT NULL COMMENT 'BOMDelta 完整 JSON',
  status             VARCHAR(16) DEFAULT 'pending' COMMENT 'pending/approved/rejected',
  reviewed_by        VARCHAR(32) NULL,
  reviewed_at        DATETIME NULL,
  created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (block_code) REFERENCES clauses(block_code) ON DELETE RESTRICT,
  FOREIGN KEY (from_bom_version_id) REFERENCES bom_versions(id) ON DELETE RESTRICT
);
```

### 7.3 事务边界（沿用 Step 2 UoW）
- Repository 方法只 add/flush，永不 commit/rollback/close
- 每个 service 方法（`run_evaluate` / `run_diagnose` / `run_optimize` / `run_apply`）在自己的 session 上 `try: ... session.commit() / except: session.rollback(); raise`
- HTTP 路由 `Depends(get_db)` 注入 session（第三条事务路径，与前两条同构）

### 7.4 并发控制（乐观锁）
```
apply_service.run_apply(delta_id, approver):
    delta = repo.get_pending_delta(delta_id)
    current_vid = repo.get_current_bom_version_id(delta.block_code)
    if current_vid != delta.from_bom_version_id:
        raise ConcurrencyError(f"基线已变，请基于 v{current} 重新 optimize")
    # 相等 → service 事务内 apply_bom_delta
```
先赢原则：第二个 apply 撞基线已变 → 拒，要求重新 optimize。不用悲观锁（调优低频）。

---

## 8. API 端点（`/api/tuning`）

| 方法 | 路径 | 触发 | 返回要点 |
|---|---|---|---|
| POST | `/api/tuning/evaluate` | 自动 | run_id, accuracy, miss/fp, OptGain |
| GET | `/api/tuning/runs/{block_code}` | — | 跑分历史 |
| POST | `/api/tuning/diagnose/{run_id}` | 自动 | 诊断数、归因分布 |
| GET | `/api/tuning/badcases/{run_id}` | — | badcases + diagnosis + trace + root_component + severity |
| POST | `/api/tuning/optimize` | 人 | delta_id, modifications[], regression_warnings |
| GET | `/api/tuning/deltas/pending/{block_code}` | — | 待审 delta 列表（默认仅 `status=pending`，过滤 rejected/approved 历史，避免待办堆积） |
| GET | `/api/tuning/deltas/{delta_id}` | — | BOMDelta（diff + 关联 diagnosis） |
| POST | `/api/tuning/apply/{delta_id}` | 人 | new_version_id 或 409 ConcurrencyError |
| POST | `/api/tuning/deltas/{delta_id}/reject` | 人 | status=rejected |
| GET | `/api/tuning/metrics/{block_code}` | — | Metrics（全字段） |
| GET | `/api/tuning/metrics` | — | 全局大盘 |

evaluate/diagnose 虽自动但**分别独立端点**（前端可串连跑，也可单独重跑 diagnose）。

---

## 9. 可视化数据模型（过程透明）

全部由 GET 端点供数，前端「调优成效」页消费：
- **evaluate 层**：跑分时间线（accuracy 趋势）+ OptGain 柱状（fixed/regressed）+ 错例清单
- **diagnose 层**：归因分布饼图（5 类）+ root_component 拆分（dq 标灰交新平台）+ 单条 trace 证据展开 + fatal 标红
- **optimize 层**：BOMDelta diff（before/after 并排）+ regression_warnings 顶部告警 + 改动→diagnosis 反向追溯
- **apply 层**：版本链时间线 + rule_modifications 审计（谁改/approved_at）+ bom_status 流转
- **闭环回放**：任意跑分能串 `evaluate→diagnose→optimize→apply→下一轮 evaluate`

---

## 10. 业务洞察落点（5 点）

| 洞察 | 落点 |
|---|---|
| ① Extraction/DQ 解耦 | `DiagnosisResult.root_component`；dq 不进 optimize |
| ② 方向性 Fatal | `DiagnosisResult.severity`；diagnose prompt 判方向/主体/金额反转→fatal；前端标红；大盘 fatal 数从 `Metrics.diagnosis_details` 聚合（不新增 Metrics 字段） |
| ③ 易混淆词 | optimize Stage2 产 KEYWORD/CONFUSION Modification + sanitize 过滤 |
| ④ 防回归（四层） | (1) 强制保留上版 positive_examples (2) regression_warnings (3) sanitize 程序化 (4) 闭环兜底 OptGain.regressed |
| ⑤ 漏抽/误抽不对等 | RunResult.miss/false_positive 分开 + Metrics 聚合 + 前端 P/R 分展 |

---

## 11. 错误处理

| 节点 | 场景 | 处理 |
|---|---|---|
| evaluate | 文件格式错/缺列 | 400 + 字段明细 |
| diagnose | 单条 LLM 失败 | 该 badcase 标 diagnose_failed，不阻塞批次（部分成功 commit） |
| optimize | LLM 失败 / JSON 解析失败 / sanitize 后无有效改动 | Pydantic 严格校验 + 解析重试 ≤2 次；仍失败 → 500，不落 pending_delta |
| 全部 | service 层 | try: commit / except: rollback + HTTPException |

**LLM JSON 解析约定**（实现注意）：所有 LLM 节点（diagnose/optimize）返回的 JSON 用 Pydantic 严格校验，解析失败重试 ≤2 次。`BOMDelta`/`DiagnosisResult` 嵌套较深（`before/after` 是字典），大模型偶发截断或格式损坏，重试 + 严格校验是必备护栏（非可选）。
| apply | 乐观锁冲突 | 409 ConcurrencyError + 提示重 optimize |
| apply | delta 合成失败 | 500，事务回滚（三表不动） |
| 全部 | service 层 | try: commit / except: rollback + HTTPException |

---

## 12. 测试策略

- **`_logic` 纯函数单测**（mock LLM）：diagnose 归因/root_component/severity 判定、optimize 两阶段产出、sanitize、apply 确定性合成（BOMDelta+旧BOM→断言新BOM）、evaluate 集合 diff（两批 badcases→OptGain）
- **乐观锁并发测试**：两 apply 同一 from_bom_version_id，第二个断言 ConcurrencyError
- **仓储测试**（TuningRepository）：需 DB，标 skip 或 sqlite fixture
- **端到端**（跑分→diagnose→optimize→apply）：需 DB+LLM，标 skip，手动跑

---

## 13. 文件落地清单（实现时）

```
backend/src/cc_bom_generator/
├─ schemas/
│  ├─ bom_delta.py            # 新增（BOMDelta/Modification/ModificationType）
│  └─ diagnosis.py            # 改（加 root_component/severity）
├─ enums/
│  └─ diagnosis_enums.py      # 可能加 ModificationType（或放 bom_delta.py）
├─ nodes/tuning/              # 新增（复用 BaseSkill+_logic 模式）
│  ├─ diagnose_logic.py
│  ├─ optimize_logic.py
│  └─ apply_logic.py
├─ db/
│  ├─ tuning_repository.py    # 新增
│  └─ models.py               # 改（Badcase 加 trace_json；加 PendingDelta）
├─ alembic/versions/0003_*.py # 新增（trace_json + pending_deltas）
├─ services/tuning/           # 新增
│  ├─ evaluate_service.py
│  ├─ diagnose_service.py
│  ├─ optimize_service.py
│  └─ apply_service.py
├─ api/routers/
│  └─ tuning.py               # 新增（/api/tuning/*）
└─ prompts/
   ├─ diagnose.txt            # 新增（从 PoC opt_stage1 抽归因部分 + root_component/severity）
   ├─ opt_stage1.txt          # 适配（拆出归因后专注改规则，吃 diagnosis）
   └─ opt_stage2.txt          # 复用 PoC
```

> 上述涉及 `schemas/`、`enums/`、`db/models.py`、`prompts/` 等契约/共享文件改动，实现时按 CLAUDE.md 铁律 9「改契约=停止+通知」开 PR 让杨力 review。
