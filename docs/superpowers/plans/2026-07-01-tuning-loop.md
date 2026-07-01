# 调优闭环（diagnose → optimize → apply → evaluate）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 PoC 半自动调优工程化成带严格契约 / 状态机 / 防回归的 4 节点独立 service 闭环。

**Architecture:** 走法 A——4 节点独立 service + DB 链串联（人审断点是一等公民），横向分三批 PR：① 契约+DB 地基 ② 核心 logic+prompt ③ service+API+Repository。事务沿用 Step 2 的 UoW（Repository 只 flush，service 管 commit）。

**Tech Stack:** Python 3.9+ / FastAPI / SQLAlchemy ORM + Alembic / Pydantic v2 / 复用 PoC（`trace_parser.py` / `opt_stage1.txt` / `opt_stage2.txt` / `sanitize_keywords`）。

**前置阅读：** `docs/superpowers/specs/2026-07-01-tuning-loop-design.md`（设计依据）、`CLAUDE.md`（铁律：契约改动开 PR、commit 前同步文档、分支 feature_lindayu）。

---

## File Structure

```
backend/src/cc_bom_generator/
├─ schemas/
│  ├─ bom_delta.py            # 新增：BOMDelta / Modification / ModificationType
│  └─ diagnosis.py            # 改：DiagnosisResult 加 root_component / severity
├─ enums/
│  └─ diagnosis_enums.py      # 改：加 RootComponent / Severity 枚举（或内联 Literal，见 Task 2 决策）
├─ nodes/tuning/              # 新增子包（复用 BaseSkill+_logic 模式，但调优 logic 是纯函数不必继承 BaseSkill）
│  ├─ __init__.py
│  ├─ trace_parser.py         # 从 quick_poc/ 搬运 + 适配（PoC 已验证资产）
│  ├─ diagnose_logic.py       # diagnose 纯函数（LLM 归因）
│  ├─ optimize_logic.py       # optimize 两阶段纯函数 + sanitize
│  └─ apply_logic.py          # BOMDelta + 旧 BOM → 新 BOM 确定性合成
├─ db/
│  ├─ models.py               # 改：Badcase 加 trace_json；加 PendingDelta ORM
│  └─ tuning_repository.py    # 新增：TuningRepository
├─ alembic/versions/0003_*.py # 新增：trace_json 列 + pending_deltas 表
├─ services/tuning/           # 新增子包
│  ├─ __init__.py
│  ├─ evaluate_service.py
│  ├─ diagnose_service.py
│  ├─ optimize_service.py
│  └─ apply_service.py
├─ api/routers/
│  └─ tuning.py               # 新增：/api/tuning/* 11 端点
└─ app.py                     # 改：include_router(tuning_router)
prompts/
├─ diagnose.txt               # 新增（从 PoC opt_stage1 抽归因部分）
├─ opt_stage1.txt             # 已有（适配：拆出归因后专注改规则）
└─ opt_stage2.txt             # 已有（复用）
backend/tests/tuning/         # 新增：调优闭环测试
```

**依赖方向**（单向）：`api → services → nodes/tuning(_logic) → schemas/enums`；`services → db/tuning_repository → db/models`。禁止逆转。

---

# PR 1：契约 + DB 地基（让杨力 review 契约变更）

> 本批改 `schemas/` + `enums/` + `db/models.py` + alembic——全是地基，按铁律 9 单独开 PR。

## Task 1: 新增 `schemas/bom_delta.py`

**Files:**
- Create: `backend/src/cc_bom_generator/schemas/bom_delta.py`
- Test: `backend/tests/tuning/test_bom_delta.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/tuning/test_bom_delta.py
"""BOMDelta 契约测试。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.schemas.bom_delta import (
    BOMDelta, Modification, ModificationType
)
from src.cc_bom_generator.enums import FixTarget


def test_modification_minimal():
    m = Modification(type=ModificationType.KEYWORD, action="add", after={"word": "保函"})
    assert m.type == ModificationType.KEYWORD
    assert m.before is None
    assert m.diagnosis_ids == []


def test_bom_delta_full():
    delta = BOMDelta(
        block_code="FSB0000004",
        from_version=1,
        fix_targets=[FixTarget.RULES],
        modifications=[
            Modification(type=ModificationType.MATCH, action="update",
                         before={"rule": "旧"}, after={"rule": "新"}, reason="漏抽保函"),
        ],
        regression_warnings=["删关键词'付款'可能影响条款B"],
    )
    assert delta.block_code == "FSB0000004"
    assert len(delta.modifications) == 1
    assert delta.modifications[0].type == ModificationType.MATCH
    assert delta.regression_warnings[0].startswith("删关键词")
```

- [ ] **Step 2: 跑测试验证失败**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_bom_delta.py -v`
Expected: FAIL `No module named ...bom_delta`

- [ ] **Step 3: 实现 bom_delta.py**

```python
# backend/src/cc_bom_generator/schemas/bom_delta.py
"""optimize 产出的 BOM 改动清单契约（对齐 db.rule_modifications 审计表）。"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional

from ..enums import FixTarget


class ModificationType(str, Enum):
    DEFINITION = "definition"
    INTERCEPTION = "interception"
    MATCH = "match"
    KEYWORD = "positive_keywords"
    CONFUSION = "confusion_words"
    PROFILE = "profile"


class Modification(BaseModel):
    type: ModificationType
    action: str = Field("update", description="add/update/delete")
    target: str = Field("", description="定位锚点（某条 rule 文本 / 某关键词原文）")
    before: Optional[dict] = Field(None, description="改前片段（对齐 rule_modifications.before_json）")
    after: Optional[dict] = Field(None, description="改后片段（对齐 rule_modifications.after_json）")
    reason: str = Field("", description="改动依据")
    diagnosis_ids: List[str] = Field(default_factory=list, description="反向追溯到触发 badcase")


class BOMDelta(BaseModel):
    block_code: str
    from_version: int = Field(..., description="基于的版本号（存库时 service 转 from_bom_version_id）")
    fix_targets: List[FixTarget]
    modifications: List[Modification] = Field(default_factory=list)
    coverage_note: str = Field("", description="LLM 自评覆盖率影响")
    regression_warnings: List[str] = Field(default_factory=list, description="防回归告警")
```

- [ ] **Step 4: 跑测试验证通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_bom_delta.py -v`
Expected: 2 passed

- [ ] **Step 5: commit**

```bash
git add backend/src/cc_bom_generator/schemas/bom_delta.py backend/tests/tuning/
git commit -m "feat(schemas): 新增 BOMDelta 契约（optimize 产出/apply 输入/审计源）[调优-PR1]"
```

---

## Task 2: `DiagnosisResult` 加 root_component / severity

**Files:**
- Modify: `backend/src/cc_bom_generator/schemas/diagnosis.py`
- Modify: `backend/src/cc_bom_generator/enums/diagnosis_enums.py`
- Test: `backend/tests/tuning/test_diagnosis_ext.py`

**决策**：root_component / severity 用**枚举**（放 diagnosis_enums.py，保持 enums 唯一事实源风格），不内联 Literal。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/tuning/test_diagnosis_ext.py
"""DiagnosisResult 扩展字段测试。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.schemas.diagnosis import DiagnosisResult
from src.cc_bom_generator.enums import (
    DiagnosisCategory, CaseType, RootComponent, Severity,
)


def test_root_component_default_extraction():
    d = DiagnosisResult(case_id="b1", case_type=CaseType.MISS, category=DiagnosisCategory.RECALL)
    assert d.root_component == RootComponent.EXTRACTION
    assert d.severity == Severity.NORMAL


def test_severity_fatal_for_directional():
    d = DiagnosisResult(
        case_id="b2", case_type=CaseType.FALSE_POSITIVE,
        category=DiagnosisCategory.BOM,
        root_component=RootComponent.EXTRACTION, severity=Severity.FATAL,
        reason="资金方向抽反",
    )
    assert d.severity == Severity.FATAL
```

- [ ] **Step 2: 跑测试验证失败**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_diagnosis_ext.py -v`
Expected: FAIL `cannot import name 'RootComponent'`

- [ ] **Step 3: 加枚举到 diagnosis_enums.py**

在 `backend/src/cc_bom_generator/enums/diagnosis_enums.py` 末尾追加（保持现有枚举不动）：

```python
class RootComponent(str, Enum):
    """归因路由：问题在抽取层还是 DQ 校验层。"""
    EXTRACTION = "extraction"   # 抽取规则/模型/画像 → 进 optimize
    DQ = "dq"                   # 新平台 DQ 漏拦 → 交新平台团队，不进 optimize


class Severity(str, Enum):
    """错例严重性。fatal = 方向/主体/金额反转（业务致命）。"""
    NORMAL = "normal"
    FATAL = "fatal"
```

并在 `enums/__init__.py` 的导出加 `RootComponent, Severity`。

- [ ] **Step 4: 改 DiagnosisResult 加字段**

修改 `backend/src/cc_bom_generator/schemas/diagnosis.py`：import 加 `RootComponent, Severity`，`DiagnosisResult` 末尾加两字段：

```python
    root_component: RootComponent = Field(RootComponent.EXTRACTION, description="归因路由：extraction→进 optimize；dq→交新平台")
    severity: Severity = Field(Severity.NORMAL, description="normal/fatal（方向·主体·金额反转=fatal）")
```

- [ ] **Step 5: 跑测试验证通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_diagnosis_ext.py -v`
Expected: 2 passed
同时回归：`PYTHONPATH=backend python -m pytest backend/tests/test_verify.py -v`（用到 DiagnosisResult 的旧测试不破）

- [ ] **Step 6: commit**

```bash
git add backend/src/cc_bom_generator/schemas/diagnosis.py backend/src/cc_bom_generator/enums/ backend/tests/tuning/test_diagnosis_ext.py
git commit -m "feat(schemas): DiagnosisResult 加 root_component/severity（归因路由+严重性分级）[调优-PR1]"
```

---

## Task 3: db/models.py 改 + alembic 0003

**Files:**
- Modify: `backend/src/cc_bom_generator/db/models.py`（Badcase 加 trace_json；加 PendingDelta 类）
- Create: `backend/alembic/versions/0003_badcase_trace_and_pending_deltas.py`
- Test: `backend/tests/tuning/test_models_0003.py`（冒烟：import + 字段存在）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/tuning/test_models_0003.py
"""alembic 0003 ORM 结构冒烟测试。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.db.models import Badcase, PendingDelta


def test_badcase_has_trace_json():
    assert hasattr(Badcase, "trace_json"), "Badcase 应有 trace_json 列"


def test_pending_delta_fields():
    cols = {c.name for c in PendingDelta.__table__.columns}
    assert {"id", "block_code", "from_bom_version_id", "delta_json", "status", "reviewed_by", "reviewed_at", "created_at"} <= cols
```

- [ ] **Step 2: 跑测试验证失败**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_models_0003.py -v`
Expected: FAIL `cannot import name 'PendingDelta'`

- [ ] **Step 3: 改 models.py**

在 `Badcase` 类加一列（`reason` 列之后）：

```python
    trace_json = Column(JSON, nullable=True, comment="解析后的 StructuredTrace（无 trace 则 NULL）")
```

在文件末尾（`DesensitizationLog` 之后）加新类：

```python
class PendingDelta(Base):
    """待审 BOMDelta 队列（optimize 产出，apply 确认后转正式 bom_version）。"""
    __tablename__ = "pending_deltas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    block_code = Column(String(64), ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False, index=True)
    from_bom_version_id = Column(Integer, ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=False, comment="乐观锁基线版本")
    delta_json = Column(JSON, nullable=False, comment="BOMDelta 完整 JSON")
    status = Column(String(16), server_default="pending", comment="pending/approved/rejected")
    reviewed_by = Column(String(32), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
```

- [ ] **Step 4: 跑测试验证通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_models_0003.py -v`
Expected: 2 passed

- [ ] **Step 5: 写 alembic 0003 迁移**

参考现有 `backend/alembic/versions/0002_*.py` 的结构，新建 `0003_badcase_trace_and_pending_deltas.py`：

```python
"""badcases 加 trace_json + pending_deltas 表

Revision ID: 0003
Revises: <填 0002 的 revision id>
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("badcases",
        sa.Column("trace_json", sa.JSON, nullable=True, comment="解析后的 StructuredTrace"))
    op.create_table(
        "pending_deltas",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_code", sa.String(64), sa.ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("from_bom_version_id", sa.Integer, sa.ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("delta_json", sa.JSON, nullable=False),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("reviewed_by", sa.String(32), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("pending_deltas")
    op.drop_column("badcases", "trace_json")
```

- [ ] **Step 6: 跑迁移验证**

Run（需本地 MySQL）：`cd backend && PYTHONPATH=. alembic upgrade head`
Expected: 迁移成功，`pending_deltas` 表 + `badcases.trace_json` 列存在（用 Navicat 确认）
（无 DB 环境则跳过本步，在 Step 7 标注）

- [ ] **Step 7: commit**

```bash
git add backend/src/cc_bom_generator/db/models.py backend/alembic/versions/0003_*.py backend/tests/tuning/test_models_0003.py
git commit -m "feat(db): Badcase 加 trace_json + pending_deltas 表（alembic 0003）[调优-PR1]"
```

---

## Task 4: PR1 文档同步 + 开 PR

- [ ] **Step 1: 更新 `docs/progress.md`** 林大宇已完成表加 3 行（Task1/2/3）+ 当前任务说明"调优 PR1（契约+DB）完成，待杨力 review"

- [ ] **Step 2: 更新 `CLAUDE.md` 协作矩阵**：`schemas/` 行注明含 bom_delta.py；`db/models.py` 注明含 PendingDelta

- [ ] **Step 3: push + 开 PR**

```bash
git push origin feature_lindayu
# 用 gh CLI 开 PR，标题「调优闭环 PR1：契约+DB 地基」，@杨力 review
```

⚠️ **阻塞点**：PR1 改契约 + DB，按铁律 9 **等杨力 review 通过后再开 PR2**。

---

# PR 2：核心 logic + prompt（杨力 review 契约后继续）

## Task 5: 搬 PoC trace_parser → nodes/tuning/

**Files:**
- Create: `backend/src/cc_bom_generator/nodes/tuning/__init__.py`
- Create: `backend/src/cc_bom_generator/nodes/tuning/trace_parser.py`（从 `quick_poc/trace_parser.py` 搬 + 改 import）
- Test: `backend/tests/tuning/test_trace_parser.py`

- [ ] **Step 1: 读 PoC 原文件确认逻辑**

读 `quick_poc/trace_parser.py`（`load_trace` + `extract_structured` 两函数，支持两文件/合并文件/单文件，递归找 reasoning，按 marker 切 prompt 段）。

- [ ] **Step 2: 写失败测试（用 PoC 已有 sample 数据）**

```python
# backend/tests/tuning/test_trace_parser.py
"""trace_parser 冒烟测试（基于 PoC sample）。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.nodes.tuning.trace_parser import extract_structured
from src.cc_bom_generator.schemas.trace import StructuredTrace


def test_extract_structured_returns_schema():
    # 用 PoC 的 sample trace（若 quick_poc/data/ 有现成文件则读；否则构造最小 input/output）
    input_json = {"context_window": "...合同原文..."}
    output_json = {"reasoning": "模型推理...", "extracted": "..."}
    st = extract_structured(input_json, output_json)
    assert isinstance(st, StructuredTrace)
    assert st.model_extracted is not None or st.context_window is not None
```

- [ ] **Step 3: 跑验证失败** → `No module named ...tuning.trace_parser`

- [ ] **Step 4: 搬运实现**

把 `quick_poc/trace_parser.py` 内容复制到 `nodes/tuning/trace_parser.py`，改：
- 顶部 import：返回类型用 `from ...schemas.trace import StructuredTrace`
- `extract_structured` 返回 `StructuredTrace(...)`（字段对齐 schemas/trace.py）
- 保持 PoC 的解析逻辑（递归找 reasoning、按 marker 切 prompt、控长度）不变

- [ ] **Step 5: 跑测试通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_trace_parser.py -v`
Expected: PASS

- [ ] **Step 6: commit**

```bash
git add backend/src/cc_bom_generator/nodes/tuning/ backend/tests/tuning/test_trace_parser.py
git commit -m "feat(tuning): 搬 PoC trace_parser 到 nodes/tuning/[调优-PR2]"
```

---

## Task 6: diagnose_logic + prompts/diagnose.txt

**Files:**
- Create: `backend/src/cc_bom_generator/nodes/tuning/diagnose_logic.py`
- Create: `prompts/diagnose.txt`（从 PoC `opt_stage1.txt` 抽归因判定部分 + 加 root_component/severity）
- Test: `backend/tests/tuning/test_diagnose_logic.py`

- [ ] **Step 1: 写失败测试（mock LLM client）**

```python
# backend/tests/tuning/test_diagnose_logic.py
"""diagnose_logic 测试（mock LLM）。"""
import sys, os, json
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.nodes.tuning.diagnose_logic import diagnose_badcase
from src.cc_bom_generator.schemas.diagnosis import DiagnosisResult
from src.cc_bom_generator.schemas.bom import BOM
from src.cc_bom_generator.schemas.trace import StructuredTrace
from src.cc_bom_generator.enums import DiagnosisCategory, CaseType, RootComponent, Severity


def _mock_bom():
    return BOM(clause="付款支持文档", block_code="FSB0000004",
               semantic_definition="...", extraction_rules=None, recall_profile=None)

def _mock_trace():
    return StructuredTrace(context_window="合同原文窗口", model_extracted="抽出的文本",
                           model_reasoning="模型推理", current_rules_profile="当前规则")


@patch("src.cc_bom_generator.nodes.tuning.diagnose_logic.call_llm")
def test_diagnose_returns_classification(mock_call):
    # mock LLM 返回结构化归因 JSON
    mock_call.return_value = json.dumps({
        "category": "召回问题", "reason": "窗口未召回付款排程",
        "suggested_fix": "放宽匹配规则", "fix_target": "rules",
        "root_component": "extraction", "severity": "normal",
    })
    diag = diagnose_badcase(bom=_mock_bom(), trace=_mock_trace(),
                            expected="付款排程", actual="")
    assert isinstance(diag, DiagnosisResult)
    assert diag.category == DiagnosisCategory.RECALL
    assert diag.root_component == RootComponent.EXTRACTION
    assert diag.severity == Severity.NORMAL
    assert diag.trace_available is True


@patch("src.cc_bom_generator.nodes.tuning.diagnose_logic.call_llm")
def test_diagnose_fatal_for_direction(mock_call):
    mock_call.return_value = json.dumps({
        "category": "BOM问题", "reason": "资金方向抽反",
        "suggested_fix": "加方向约束", "fix_target": "rules",
        "root_component": "extraction", "severity": "fatal",
    })
    diag = diagnose_badcase(bom=_mock_bom(), trace=_mock_trace(),
                            expected="华为向供应商付款", actual="供应商向华为付款")
    assert diag.severity == Severity.FATAL


@patch("src.cc_bom_generator.nodes.tuning.diagnose_logic.call_llm")
def test_diagnose_dq_routed_out(mock_call):
    mock_call.return_value = json.dumps({
        "category": "BOM问题", "reason": "DQ 校验漏拦",
        "suggested_fix": "新平台 DQ 加校验", "fix_target": "rules",
        "root_component": "dq", "severity": "normal",
    })
    diag = diagnose_badcase(bom=_mock_bom(), trace=_mock_trace(), expected="x", actual="y")
    assert diag.root_component == RootComponent.DQ  # 调用方据此不进 optimize
```

- [ ] **Step 2: 跑验证失败** → `cannot import name 'diagnose_badcase'`

- [ ] **Step 3: 写 prompts/diagnose.txt**

基于 `quick_poc/prompts/opt_stage1.txt`（如果路径不同，先 `grep -r "opt_stage1" quick_poc/` 定位），抽出归因判定部分，加入：
- 5 类判定规则（context_window→召回 / model_reasoning→大模型推理 / prompt→模板 / 规则→BOM / 多因→混合）
- root_component 判定（问题在抽取层=DQ 校验漏拦→dq）
- severity 判定（方向/主体/金额反转→fatal）
- 输出 JSON schema：`{category, reason, suggested_fix, fix_target, root_component, severity}`
- 用 `{{bom_definition}}` `{{trace_context}}` `{{trace_reasoning}}` `{{expected}}` `{{actual}}` 占位（与代码分离约定）

- [ ] **Step 4: 实现 diagnose_logic.py**

```python
# backend/src/cc_bom_generator/nodes/tuning/diagnose_logic.py
"""diagnose 纯函数：trace + badcase + BOM → DiagnosisResult（LLM 归因）。"""
from __future__ import annotations
import json
from pathlib import Path

from ...llm.client import call_llm  # 复用现有 LLM 客户端（按实际签名调整）
from ...schemas.bom import BOM
from ...schemas.diagnosis import DiagnosisResult
from ...schemas.trace import StructuredTrace
from ...enums import DiagnosisCategory, CaseType, ConfidenceLevel, FixTarget, RootComponent, Severity
from ...logging_config import get_logger

log = get_logger("tuning.diagnose")

_PROMPT_PATH = Path(__file__).resolve().parents[4] / "prompts" / "diagnose.txt"
_MAX_RETRIES = 2


def _render_prompt(bom: BOM, trace: StructuredTrace, expected: str, actual: str) -> str:
    tpl = _PROMPT_PATH.read_text(encoding="utf-8")
    return (tpl
            .replace("{{bom_definition}}", bom.semantic_definition or "")
            .replace("{{trace_context}}", trace.context_window or "")
            .replace("{{trace_reasoning}}", trace.model_reasoning or "")
            .replace("{{expected}}", expected or "")
            .replace("{{actual}}", actual or ""))


def _parse_diag(raw: str, case_id: str, case_type: CaseType, trace_available: bool) -> DiagnosisResult:
    data = json.loads(raw)  # 重试在调用层
    return DiagnosisResult(
        case_id=case_id, case_type=case_type,
        category=DiagnosisCategory(data["category"]),
        reason=data.get("reason", ""), suggested_fix=data.get("suggested_fix", ""),
        fix_target=FixTarget(data.get("fix_target", "rules")),
        root_component=RootComponent(data.get("root_component", "extraction")),
        severity=Severity(data.get("severity", "normal")),
        confidence=ConfidenceLevel.LOW if not trace_available else ConfidenceLevel.MEDIUM,
        trace_available=trace_available,
    )


def diagnose_badcase(bom: BOM, trace: StructuredTrace | None,
                     expected: str, actual: str,
                     case_id: str = "", case_type: CaseType = CaseType.MISS) -> DiagnosisResult:
    """对单个 badcase 归因。无 trace 则降级（confidence=低）。"""
    trace_available = trace is not None and bool(trace.context_window or trace.model_reasoning)
    prompt = _render_prompt(bom, trace or StructuredTrace(), expected, actual)
    last_err = None
    for i in range(_MAX_RETRIES + 1):
        try:
            raw = call_llm(prompt, temperature=0.2)  # 按实际 client 签名调整
            return _parse_diag(raw, case_id, case_type, trace_available)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            last_err = e
            log.error(f"diagnose JSON 解析失败(第{i+1}次): {e}")
    raise RuntimeError(f"diagnose 解析重试 {_MAX_RETRIES+1} 次仍失败: {last_err}")
```

- [ ] **Step 5: 跑测试通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_diagnose_logic.py -v`
Expected: 3 passed

- [ ] **Step 6: commit**

```bash
git add backend/src/cc_bom_generator/nodes/tuning/diagnose_logic.py prompts/diagnose.txt backend/tests/tuning/test_diagnose_logic.py
git commit -m "feat(tuning): diagnose_logic + prompts/diagnose.txt（LLM 归因+路由+严重性）[调优-PR2]"
```

---

## Task 7: optimize_logic（两阶段 + sanitize）

**Files:**
- Create: `backend/src/cc_bom_generator/nodes/tuning/optimize_logic.py`
- Modify: `prompts/opt_stage1.txt` / `prompts/opt_stage2.txt`（适配：吃 diagnosis，产出 Modification 列表）
- Test: `backend/tests/tuning/test_optimize_logic.py`

- [ ] **Step 1: 写失败测试（mock LLM，两阶段）**

```python
# backend/tests/tuning/test_optimize_logic.py
"""optimize_logic 两阶段测试（mock LLM）。"""
import sys, os, json
from unittest.mock import patch, side_effect
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.nodes.tuning.optimize_logic import optimize_bom, sanitize_keywords
from src.cc_bom_generator.schemas.bom import BOM, ExtractionRules
from src.cc_bom_generator.schemas.bom_delta import BOMDelta, ModificationType
from src.cc_bom_generator.schemas.diagnosis import DiagnosisResult
from src.cc_bom_generator.enums import DiagnosisCategory, CaseType, FixTarget


def test_sanitize_keywords_drops_overfit():
    # 含数字 / 含整句标点 / 超长(>8中文字) 丢
    raw = ["发票", "金额100万", "付款，支持", "这是一个超长的关键词测试"]
    clean = sanitize_keywords(raw)
    assert "发票" in clean
    assert "金额100万" not in clean
    assert all("，" not in k for k in clean)


@patch("src.cc_bom_generator.nodes.tuning.optimize_logic.call_llm")
def test_optimize_produces_delta(mock_call):
    # Stage1 返回规则改动，Stage2 返回画像改动
    mock_call.side_effect = [
        json.dumps({"modifications": [
            {"type": "match", "action": "update", "before": {"rule": "旧"},
             "after": {"rule": "新"}, "reason": "漏抽保函"}],
            "coverage_note": "覆盖率提升"}),
        json.dumps({"modifications": [
            {"type": "positive_keywords", "action": "add", "after": {"word": "保函"}, "reason": "补关键词"}],
            "regression_warnings": []}),
    ]
    bom = BOM(clause="付款支持文档", block_code="FSB0000004", version=1,
              extraction_rules=ExtractionRules())
    diags = [DiagnosisResult(case_id="b1", case_type=CaseType.MISS, category=DiagnosisCategory.RECALL,
                             fix_target=FixTarget.RULES)]
    delta = optimize_bom(bom=bom, diagnoses=diags)
    assert isinstance(delta, BOMDelta)
    assert delta.from_version == 1
    types = [m.type for m in delta.modifications]
    assert ModificationType.MATCH in types
    assert ModificationType.KEYWORD in types  # Stage2 产出
```

- [ ] **Step 2: 跑验证失败** → `cannot import name 'optimize_bom'`

- [ ] **Step 3: 适配 prompts**

修改 `prompts/opt_stage1.txt`：输入加 `{{diagnoses_json}}`（已确认归因），输出改为 `{modifications: [...], coverage_note}`（ Modification 列表，含 type/action/before/after/reason）。
修改 `prompts/opt_stage2.txt`：输入加 Stage1 结果，强调**强制保留上版 positive_examples**，输出 `{modifications: [...], regression_warnings: [...]}`。
（两 prompt 已存在，本步是改内容；若 PoC 路径不同先 `grep -r "opt_stage" quick_poc/` 定位）

- [ ] **Step 4: 实现 optimize_logic.py**

```python
# backend/src/cc_bom_generator/nodes/tuning/optimize_logic.py
"""optimize 两阶段纯函数：diagnosis + BOM → BOMDelta（LLM + 程序化 sanitize）。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import List

from ...llm.client import call_llm
from ...schemas.bom import BOM
from ...schemas.bom_delta import BOMDelta, Modification, ModificationType
from ...schemas.diagnosis import DiagnosisResult
from ...enums import FixTarget
from ...logging_config import get_logger

log = get_logger("tuning.optimize")
_PROMPTS = Path(__file__).resolve().parents[4] / "prompts"
_MAX_RETRIES = 2

_RULE_TARGETS = {FixTarget.RULES, FixTarget.BOTH}
_PROFILE_TARGETS = {FixTarget.RECALL_PROFILE, FixTarget.BOTH}


def sanitize_keywords(keywords: List[str]) -> List[str]:
    """复刻 PoC sanitize：丢含数字/整句标点/超长(>8中文字)的过拟合词。"""
    clean = []
    for kw in keywords:
        if any(c.isdigit() for c in kw):
            continue
        if any(c in kw for c in "，,；;。.!！"):
            continue
        if len(kw) > 8:
            continue
        clean.append(kw)
    return clean


def _call_with_retry(prompt: str, temp: float) -> dict:
    last = None
    for i in range(_MAX_RETRIES + 1):
        try:
            return json.loads(call_llm(prompt, temperature=temp))
        except (json.JSONDecodeError, ValueError) as e:
            last = e
            log.error(f"optimize JSON 解析失败(第{i+1}次): {e}")
    raise RuntimeError(f"optimize 解析重试失败: {last}")


def optimize_bom(bom: BOM, diagnoses: List[DiagnosisResult], few_shot: str = "") -> BOMDelta:
    """两阶段产出 BOMDelta。Stage1 改规则，Stage2 改画像（强制保留上版正例）。"""
    fixes = _RULE_TARGETS & {d.fix_target for d in diagnoses}
    mods: List[Modification] = []

    if fixes:
        s1 = _call_with_retry(_render_stage1(bom, diagnoses, few_shot), temp=0.2)
        mods += [Modification(**m) for m in s1.get("modifications", [])]
    if _PROFILE_TARGETS & {d.fix_target for d in diagnoses}:
        s2 = _call_with_retry(_render_stage2(bom, s1 if fixes else {}, few_shot), temp=0.5)
        mods += [Modification(**m) for m in s2.get("modifications", [])]
        # sanitize 关键词类改动
        for m in mods:
            if m.type == ModificationType.KEYWORD and m.after and "word" in m.after:
                m.after["word"] = sanitize_keywords([m.after["word"]])[0] if sanitize_keywords([m.after["word"]]) else m.after["word"]

    return BOMDelta(
        block_code=bom.block_code, from_version=bom.version,
        fix_targets=list({d.fix_target for d in diagnoses}),
        modifications=mods,
        coverage_note=s1.get("coverage_note", "") if fixes else "",
        regression_warnings=s2.get("regression_warnings", []) if (_PROFILE_TARGETS & {d.fix_target for d in diagnoses}) else [],
    )


def _render_stage1(bom, diagnoses, few_shot) -> str:
    tpl = (_PROMPTS / "opt_stage1.txt").read_text(encoding="utf-8")
    return (tpl.replace("{{bom_json}}", bom.model_dump_json())
              .replace("{{diagnoses_json}}", json.dumps([d.model_dump(mode="json") for d in diagnoses], ensure_ascii=False))
              .replace("{{few_shot}}", few_shot))

def _render_stage2(bom, stage1_out, few_shot) -> str:
    tpl = (_PROMPTS / "opt_stage2.txt").read_text(encoding="utf-8")
    return (tpl.replace("{{bom_json}}", bom.model_dump_json())
              .replace("{{stage1_json}}", json.dumps(stage1_out, ensure_ascii=False))
              .replace("{{positive_examples}}", json.dumps(bom.recall_profile.positive_examples, ensure_ascii=False))
              .replace("{{few_shot}}", few_shot))
```

- [ ] **Step 5: 跑测试通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_optimize_logic.py -v`
Expected: 2 passed

- [ ] **Step 6: commit**

```bash
git add backend/src/cc_bom_generator/nodes/tuning/optimize_logic.py prompts/opt_stage1.txt prompts/opt_stage2.txt backend/tests/tuning/test_optimize_logic.py
git commit -m "feat(tuning): optimize_logic 两阶段+sanitize（产出 BOMDelta）[调优-PR2]"
```

---

## Task 8: apply_logic（BOMDelta 确定性合成新 BOM）

**Files:**
- Create: `backend/src/cc_bom_generator/nodes/tuning/apply_logic.py`
- Test: `backend/tests/tuning/test_apply_logic.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/tuning/test_apply_logic.py
"""apply_logic 确定性合成测试（无 LLM）。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.nodes.tuning.apply_logic import apply_delta_to_bom
from src.cc_bom_generator.schemas.bom import BOM, ExtractionRules, ExtractionRule, RecallProfile
from src.cc_bom_generator.schemas.bom_delta import BOMDelta, Modification, ModificationType
from src.cc_bom_generator.enums import FixTarget


def _base_bom():
    return BOM(clause="付款支持文档", block_code="FSB0000004", version=1,
               semantic_definition="旧定义",
               extraction_rules=ExtractionRules(
                   core_match_rules=[ExtractionRule(rule="旧匹配规则")]),
               recall_profile=RecallProfile(positive_examples=["正例A"]))


def test_apply_updates_definition():
    delta = BOMDelta(block_code="FSB0000004", from_version=1, fix_targets=[FixTarget.RULES],
        modifications=[Modification(type=ModificationType.DEFINITION, action="update",
                                    before={"text": "旧定义"}, after={"text": "新定义"})])
    new_bom = apply_delta_to_bom(_base_bom(), delta)
    assert new_bom.semantic_definition == "新定义"
    assert new_bom.version == 2  # 版本号自增


def test_apply_preserves_positive_examples():
    delta = BOMDelta(block_code="FSB0000004", from_version=1, fix_targets=[FixTarget.RECALL_PROFILE],
        modifications=[Modification(type=ModificationType.KEYWORD, action="add", after={"word": "保函"})])
    new_bom = apply_delta_to_bom(_base_bom(), delta)
    assert "正例A" in new_bom.recall_profile.positive_examples  # 防回归：保留上版正例


def test_apply_match_rule_update():
    delta = BOMDelta(block_code="FSB0000004", from_version=1, fix_targets=[FixTarget.RULES],
        modifications=[Modification(type=ModificationType.MATCH, action="update",
                                    target="旧匹配规则", before={"rule": "旧匹配规则"},
                                    after={"rule": "新匹配规则"})])
    new_bom = apply_delta_to_bom(_base_bom(), delta)
    rules = [r.rule for r in new_bom.extraction_rules.core_match_rules]
    assert "新匹配规则" in rules and "旧匹配规则" not in rules
```

- [ ] **Step 2: 跑验证失败** → `cannot import name 'apply_delta_to_bom'`

- [ ] **Step 3: 实现 apply_logic.py**

```python
# backend/src/cc_bom_generator/nodes/tuning/apply_logic.py
"""apply 纯函数：BOMDelta + 旧 BOM → 新 BOM（确定性结构合成，无 LLM）。"""
from __future__ import annotations
import copy

from ...schemas.bom import BOM, ExtractionRule
from ...schemas.bom_delta import BOMDelta, Modification, ModificationType


def apply_delta_to_bom(old: BOM, delta: BOMDelta) -> BOM:
    """按 modifications 确定性合并出新 BOM（版本号 +1，previous_bom_version 记旧版）。"""
    new = copy.deepcopy(old)
    new.previous_bom_version = old.version
    new.version = old.version + 1

    for m in delta.modifications:
        _apply_one(new, m)
    return new


def _apply_one(bom: BOM, m: Modification) -> None:
    if m.type == ModificationType.DEFINITION:
        if m.after and "text" in m.after:
            bom.semantic_definition = m.after["text"]
    elif m.type == ModificationType.INTERCEPTION:
        _apply_rule_list(bom.extraction_rules.absolute_interception_rules, m)
    elif m.type == ModificationType.MATCH:
        _apply_rule_list(bom.extraction_rules.core_match_rules, m)
    elif m.type == ModificationType.KEYWORD:
        _apply_word_list(bom.recall_profile.positive_keywords, m)
    elif m.type == ModificationType.CONFUSION:
        _apply_word_list(bom.recall_profile.confusion_words, m)
    elif m.type == ModificationType.PROFILE:
        pass  # section_hints/semantic_queries 等：按 m.after 的 key 合并（实现时按需扩展）


def _apply_rule_list(rules: list, m: Modification) -> None:
    if m.action == "add" and m.after:
        rules.append(ExtractionRule(rule=m.after.get("rule", "")))
    elif m.action == "update":
        for r in rules:
            if r.rule == (m.before or {}).get("rule", m.target) and m.after:
                r.rule = m.after.get("rule", r.rule)
    elif m.action == "delete":
        rules[:] = [r for r in rules if r.rule != (m.before or {}).get("rule", m.target)]


def _apply_word_list(words: list, m: Modification) -> None:
    if m.action == "add" and m.after and "word" in m.after:
        w = m.after["word"]
        if w and w not in words:
            words.append(w)
    elif m.action == "delete" and m.before and "word" in m.before:
        w = m.before["word"]
        words[:] = [x for x in words if x != w]
```

- [ ] **Step 4: 跑测试通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_apply_logic.py -v`
Expected: 3 passed

- [ ] **Step 5: commit**

```bash
git add backend/src/cc_bom_generator/nodes/tuning/apply_logic.py backend/tests/tuning/test_apply_logic.py
git commit -m "feat(tuning): apply_logic 确定性合成新 BOM（无 LLM）[调优-PR2]"
```

---

## Task 9: PR2 文档同步 + 开 PR

- [ ] **Step 1: progress.md 加 PR2 进度（Task5-8）**
- [ ] **Step 2: push + 开 PR2**（标题「调优闭环 PR2：核心 logic + prompt」）

---

# PR 3：service + API + TuningRepository

## Task 10: db/tuning_repository.py

**Files:**
- Create: `backend/src/cc_bom_generator/db/tuning_repository.py`
- Test: `backend/tests/tuning/test_tuning_repository.py`（需 DB，标 skip）

- [ ] **Step 1: 写仓储测试（结构 + skip 无 DB 时）**

```python
# backend/tests/tuning/test_tuning_repository.py
"""TuningRepository 测试（需 DB，无 DB 跳过）。"""
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.db.tuning_repository import TuningRepository


def test_methods_exist():
    """无 DB 也能跑：方法签名冒烟。"""
    methods = [m for m in dir(TuningRepository) if not m.startswith("_")]
    for required in ["save_platform_run", "save_badcases", "get_previous_run",
                     "compare_runs", "list_undiagnosed_badcases", "save_diagnosis",
                     "save_pending_delta", "get_pending_delta", "apply_bom_delta",
                     "reject_pending_delta", "get_current_bom_version_id"]:
        assert required in methods, f"缺方法 {required}"


@pytest.mark.skip(reason="需真 DB，手动跑")
def test_apply_optimistic_lock():
    """两个 apply 同一 from_bom_version_id，第二个应 ConcurrencyError。"""
    from src.cc_bom_generator.db import session_scope, PipelineRepository
    # ... 构造旧 BOM + pending_delta，apply 两次，第二次断言 ConcurrencyError
```

- [ ] **Step 2: 跑验证失败** → `cannot import name 'TuningRepository'`

- [ ] **Step 3: 实现 tuning_repository.py**

```python
# backend/src/cc_bom_generator/db/tuning_repository.py
"""调优闭环仓储（注入 session，只 flush 不 commit，事务由 service 管）。"""
from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from .models import (
    Badcase, BomVersion, PlatformRun, Diagnosis, PendingDelta, Clause,
)
from ..schemas.bom_delta import BOMDelta
from ..schemas.diagnosis import DiagnosisResult
from ..schemas.evaluation import OptGain
from ..logging_config import get_logger

log = get_logger("db.tuning_repository")


class TuningRepository:
    def __init__(self, session: Session):
        self.session = session

    # ---- evaluate ----
    def save_platform_run(self, block_code, bom_version_id, accuracy, miss, fp, total, platform_batch) -> int:
        run = PlatformRun(block_code=block_code, bom_version_id=bom_version_id,
                          accuracy=accuracy, miss_count=miss, fp_count=fp,
                          total_samples=total, platform_batch=platform_batch)
        self.session.add(run); self.session.flush()
        log.info(f"platform_run 保存: id={run.id}, block={block_code}, acc={accuracy}")
        return run.id

    def save_badcases(self, platform_run_id: int, badcases: List[dict]) -> List[int]:
        ids = []
        for bc in badcases:
            obj = Badcase(platform_run_id=platform_run_id, block_code=bc["block_code"],
                          doc_id=bc.get("doc_id", ""), case_type=bc["case_type"],
                          expected=bc.get("expected", ""), actual=bc.get("actual", ""),
                          overall_coverage=bc.get("overall_coverage"),
                          segment_coverage=bc.get("segment_coverage"),
                          reason=bc.get("reason", ""), trace_json=bc.get("trace_json"))
            self.session.add(obj); self.session.flush(); ids.append(obj.id)
        log.info(f"badcases 批量保存: run={platform_run_id}, count={len(ids)}")
        return ids

    def get_previous_run(self, block_code: str, before_run_id: int) -> Optional[PlatformRun]:
        return (self.session.query(PlatformRun)
                .filter(PlatformRun.block_code == block_code, PlatformRun.id < before_run_id)
                .order_by(PlatformRun.id.desc()).first())

    def compare_runs(self, old_id: int, new_id: int, block_code: str) -> OptGain:
        old_set = {(b.doc_id, b.case_type) for b in self.session.query(Badcase).filter_by(platform_run_id=old_id)}
        new_set = {(b.doc_id, b.case_type) for b in self.session.query(Badcase).filter_by(platform_run_id=new_id)}
        fixed = len(old_set - new_set)      # 旧错 → 新对
        regressed = len(new_set - old_set)  # 旧对 → 新错
        return OptGain(block_code=block_code,
                       from_version=0, to_version=0,  # service 层填版本号
                       fixed=fixed, regressed=regressed, net=fixed - regressed)

    # ---- diagnose ----
    def list_undiagnosed_badcases(self, platform_run_id: int) -> List[Badcase]:
        rows = (self.session.query(Badcase).filter_by(platform_run_id=platform_run_id).all())
        return [b for b in rows if self.session.query(Diagnosis).filter_by(badcase_id=b.id).first() is None]

    def save_diagnosis(self, badcase_id: int, diag: DiagnosisResult) -> int:
        d = Diagnosis(badcase_id=badcase_id, category=diag.category.value,
                      root_cause=diag.reason, suggested_fix=diag.suggested_fix,
                      fix_target=diag.fix_target.value, confidence=diag.confidence.value,
                      trace_available=diag.trace_available)
        self.session.add(d); self.session.flush()
        log.info(f"diagnosis 保存: badcase={badcase_id}, category={diag.category.value}")
        return d.id

    # ---- optimize ----
    def save_pending_delta(self, block_code: str, from_bom_version_id: int, delta: BOMDelta) -> int:
        pd = PendingDelta(block_code=block_code, from_bom_version_id=from_bom_version_id,
                          delta_json=delta.model_dump(mode="json"))
        self.session.add(pd); self.session.flush()
        log.info(f"pending_delta 保存: id={pd.id}, block={block_code}")
        return pd.id

    def get_pending_delta(self, delta_id: int) -> Optional[PendingDelta]:
        return self.session.get(PendingDelta, delta_id)

    # ---- apply ----
    def get_current_bom_version_id(self, block_code: str) -> Optional[int]:
        clause = self.session.query(Clause).filter_by(block_code=block_code).first()
        if not clause or not clause.current_version:
            return None
        bv = (self.session.query(BomVersion)
              .filter_by(block_code=block_code, version=clause.current_version).first())
        return bv.id if bv else None

    def apply_bom_delta(self, delta_id: int, approver: str, new_bom_json: dict,
                         modifications: list, from_version: int) -> int:
        """必须在调用方事务内调用：落新 bom_version + 批量 rule_modifications + 状态机。
        调用方（service）负责：乐观锁校验 + 合成新 BOM（apply_logic）+ commit。"""
        from .models import BomVersion, RuleModification
        pd = self.session.get(PendingDelta, delta_id)
        # 新 bom_version
        new_bv = BomVersion(block_code=pd.block_code, version=from_version + 1,
                            bom_source="optimize", previous_bom_id=pd.from_bom_version_id,
                            bom_status="reviewed", full_bom_json=new_bom_json)
        self.session.add(new_bv); self.session.flush()
        # 批量 rule_modifications（审计）
        from .models import RuleModification
        for m in modifications:
            self.session.add(RuleModification(
                bom_version_id=new_bv.id, modification_type=m["type"],
                reason=m.get("reason", ""), before_json=m.get("before"), after_json=m.get("after"),
                operator=approver, approver=approver, approved_at=datetime.now()))
        # 状态机
        clause = self.session.query(Clause).filter_by(block_code=pd.block_code).first()
        if clause: clause.current_version = from_version + 1
        pd.status = "approved"; pd.reviewed_by = approver; pd.reviewed_at = datetime.now()
        log.info(f"apply_bom_delta: delta={delta_id} → new bom_version={new_bv.id}")
        return new_bv.id

    def reject_pending_delta(self, delta_id: int, reviewer: str) -> None:
        pd = self.session.get(PendingDelta, delta_id)
        if pd:
            pd.status = "rejected"; pd.reviewed_by = reviewer; pd.reviewed_at = datetime.now()
```

- [ ] **Step 4: 跑测试通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/tuning/test_tuning_repository.py::test_methods_exist -v`
Expected: PASS（skip 的 DB 测试手动跑）

- [ ] **Step 5: commit**

```bash
git add backend/src/cc_bom_generator/db/tuning_repository.py backend/tests/tuning/test_tuning_repository.py
git commit -m "feat(db): TuningRepository（调优仓储 11 方法）[调优-PR3]"
```

---

## Task 11: services/tuning/*（4 service）

**Files:**
- Create: `backend/src/cc_bom_generator/services/tuning/__init__.py`
- Create: `evaluate_service.py` / `diagnose_service.py` / `optimize_service.py` / `apply_service.py`

每个 service 复用 Step 2 的 UoW 模式（`try: ... session.commit() / except: rollback; raise`）。核心结构示例（`apply_service`，含乐观锁）：

```python
# backend/src/cc_bom_generator/services/tuning/apply_service.py
"""apply 业务编排：乐观锁校验 + 合成新 BOM + 事务落库。"""
from __future__ import annotations
from sqlalchemy.orm import Session
from ...db.tuning_repository import TuningRepository
from ...db.repository import PipelineRepository  # 读旧 bom_version.full_bom_json
from ...nodes.tuning.apply_logic import apply_delta_to_bom
from ...schemas.bom import BOM
from ...logging_config import get_logger

log = get_logger("services.apply")


class ConcurrencyError(Exception):
    """乐观锁冲突：基线版本已变。"""


def run_apply(session: Session, delta_id: int, approver: str) -> int:
    repo = TuningRepository(session)
    pipe_repo = PipelineRepository(session)
    pd = repo.get_pending_delta(delta_id)
    if not pd:
        raise ValueError(f"pending_delta {delta_id} 不存在")

    # 乐观锁：当前最新 bom_version_id 必须等于 delta 的基线
    current_vid = repo.get_current_bom_version_id(pd.block_code)
    if current_vid != pd.from_bom_version_id:
        raise ConcurrencyError(
            f"基线已变（delta 基于 v{pd.from_bom_version_id}，当前最新 v{current_vid}），请基于最新版本重新 optimize")

    from ...schemas.bom_delta import BOMDelta
    delta = BOMDelta(**pd.delta_json)
    old_bom = BOM(**pipe_repo.get_bom_full_json(pd.from_bom_version_id))  # 见下方补充
    new_bom = apply_delta_to_bom(old_bom, delta)

    try:
        new_id = repo.apply_bom_delta(
            delta_id, approver,
            new_bom_json=new_bom.model_dump(mode="json"),
            modifications=[m.model_dump(mode="json") for m in delta.modifications],
            from_version=delta.from_version)
        session.commit()
        log.info(f"apply 成功: delta={delta_id} → bom_version={new_id}")
        return new_id
    except Exception:
        session.rollback(); raise
```

> **补充**：`PipelineRepository` 需加一个 `get_bom_full_json(bom_version_id) -> dict`（读 BomVersion.full_bom_json）。在 Task 10 完成后补到 PipelineRepository 或 TuningRepository（建议 TuningRepository 加 `get_bom_version(bom_version_id)`）。

- [ ] 其余 3 个 service（evaluate/diagnose/optimize）按同样 UoW 模式实现：
  - `evaluate_service.run_evaluate(session, file, block_code, bom_version_id)`：解析文件 → `repo.save_platform_run` + `save_badcases` + `compare_runs` → 返回 RunResult + OptGain
  - `diagnose_service.run_diagnose(session, run_id)`：`repo.list_undiagnosed_badcases` → 逐个 `diagnose_badcase`（单条失败标 failed 不阻塞）→ `repo.save_diagnosis` → commit
  - `optimize_service.run_optimize(session, block_code, from_bom_version_id, diagnosis_ids)`：取 diagnosis + 当前 BOM → `optimize_bom` → `repo.save_pending_delta` → 返回 delta_id

- [ ] 每个 service 配测试（mock repo / logic），TDD 同前。
- [ ] **commit**：`feat(services/tuning): 4 service + 乐观锁 + UoW 事务 [调优-PR3]`

---

## Task 12: api/routers/tuning.py（11 端点）

**Files:**
- Create: `backend/src/cc_bom_generator/api/routers/tuning.py`
- Modify: `backend/src/cc_bom_generator/app.py`（include_router）

- [ ] **Step 1: 实现 router**（按 spec 第 8 段表，11 端点。结构同 `api/routers/generate.py`）

```python
# backend/src/cc_bom_generator/api/routers/tuning.py
"""/api/tuning 调优闭环路由。"""
from __future__ import annotations
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from ..deps import get_db
from ...services.tuning import evaluate_service, diagnose_service, optimize_service, apply_service

router = APIRouter()


@router.post("/tuning/evaluate")
async def evaluate(file: UploadFile = File(...), block_code: str = Form(...), bom_version_id: int = Form(...), db: Session = Depends(get_db)):
    try:
        return await evaluate_service.run_evaluate(db, file, block_code, bom_version_id)
    except Exception as e:
        raise HTTPException(400 if "格式" in str(e) else 500, detail=str(e))


@router.get("/tuning/runs/{block_code}")
def runs(block_code: str, db: Session = Depends(get_db)):
    from ...db.tuning_repository import TuningRepository
    return evaluate_service.list_runs(TuningRepository(db), block_code)


@router.post("/tuning/diagnose/{run_id}")
def diagnose(run_id: int, db: Session = Depends(get_db)):
    return diagnose_service.run_diagnose(db, run_id)


@router.get("/tuning/badcases/{run_id}")
def badcases(run_id: int, db: Session = Depends(get_db)):
    from ...db.tuning_repository import TuningRepository
    return diagnose_service.list_badcases(TuningRepository(db), run_id)


@router.post("/tuning/optimize")
def optimize(body: dict, db: Session = Depends(get_db)):
    return optimize_service.run_optimize(db, body["block_code"], body["from_bom_version_id"], body.get("diagnosis_ids", []))


@router.get("/tuning/deltas/pending/{block_code}")
def pending_deltas(block_code: str, db: Session = Depends(get_db)):
    from ...db.tuning_repository import TuningRepository
    return optimize_service.list_pending(TuningRepository(db), block_code)  # 默认仅 status=pending


@router.get("/tuning/deltas/{delta_id}")
def delta_detail(delta_id: int, db: Session = Depends(get_db)):
    from ...db.tuning_repository import TuningRepository
    return optimize_service.get_delta_detail(TuningRepository(db), delta_id)


@router.post("/tuning/apply/{delta_id}")
def apply(delta_id: int, body: dict, db: Session = Depends(get_db)):
    try:
        return {"new_version_id": apply_service.run_apply(db, delta_id, body["approver"])}
    except apply_service.ConcurrencyError as e:
        raise HTTPException(409, detail=str(e))


@router.post("/tuning/deltas/{delta_id}/reject")
def reject(delta_id: int, body: dict, db: Session = Depends(get_db)):
    from ...db.tuning_repository import TuningRepository
    TuningRepository(db).reject_pending_delta(delta_id, body["reviewer"]); db.commit()
    return {"status": "rejected"}


@router.get("/tuning/metrics/{block_code}")
def metrics_block(block_code: str, db: Session = Depends(get_db)):
    from ...db.tuning_repository import TuningRepository
    return evaluate_service.aggregate_metrics(TuningRepository(db), block_code)


@router.get("/tuning/metrics")
def metrics_all(db: Session = Depends(get_db)):
    from ...db.tuning_repository import TuningRepository
    return evaluate_service.aggregate_metrics_all(TuningRepository(db))
```

- [ ] **Step 2: 改 app.py 挂 router**

在 `app.py` 的 `create_app` 加：
```python
from .api.routers.tuning import router as tuning_router
app.include_router(tuning_router, prefix="/api")
```

- [ ] **Step 3: 路由冒烟测试**

```python
PYTHONPATH=backend python -c "
from src.cc_bom_generator.app import create_app
app = create_app()
paths = sorted(r.path for r in app.routes if hasattr(r,'path'))
assert '/api/tuning/evaluate' in paths
assert '/api/tuning/metrics' in paths
print('tuning routes ok:', [p for p in paths if 'tuning' in p])"
```
Expected: 列出 11 个 tuning 端点

- [ ] **Step 4: commit**

```bash
git add backend/src/cc_bom_generator/api/routers/tuning.py backend/src/cc_bom_generator/app.py
git commit -m "feat(api): /api/tuning 11 端点 [调优-PR3]"
```

---

## Task 13: 端到端验证 + 收尾

- [ ] **Step 1: TestClient 冒烟 `/api/tuning/metrics`**（不碰 DB 的 GET 或 mock）

```python
PYTHONPATH=backend python -c "
from fastapi.testclient import TestClient
from src.cc_bom_generator.app import create_app
c = TestClient(create_app())
r = c.get('/api/tuning/metrics')  # 大盘（可能空，但应 200 不报错）
print('metrics status:', r.status_code)"
```

- [ ] **Step 2: 乐观锁并发测试**（Task 10 skip 的那个，若有 DB 手动跑）
- [ ] **Step 3: progress.md 标「调优闭环 PR3 完成」+ 当前任务更新**
- [ ] **Step 4: CLAUDE.md 目录树加 nodes/tuning/ + services/tuning/ + api/routers/tuning.py**
- [ ] **Step 5: push + 开 PR3**（标题「调优闭环 PR3：service + API + Repository」）

---

## 总体验证清单

1. **契约**：`schemas/bom_delta.py` 存在；`DiagnosisResult` 有 root_component/severity
2. **DB**：alembic 0003 应用后 `badcases.trace_json` + `pending_deltas` 表存在
3. **logic 单测全绿**：diagnose/optimize/apply/trace_parser/sanitize（不连 DB/LLM，mock）
4. **仓储方法齐全**：TuningRepository 11 方法
5. **路由**：11 个 `/api/tuning/*` 端点注册
6. **乐观锁**：并发 apply 第二个 ConcurrencyError
7. **防回归**：apply 保留上版 positive_examples（test_apply_preserves_positive_examples）

## Self-Review

- **Spec 覆盖**：spec 13 节 → PR1 覆盖第 5 节（契约）+ 7.2（DDL）；PR2 覆盖第 6 节（4 节点 logic）+ prompts；PR3 覆盖第 7（仓储）+ 8（API）+ 9（可视化数据由 GET 端点供数）+ 11（错误处理，service 层 try/commit/rollback）。第 10 节业务洞察落点由 diagnose（root_component/severity）+ optimize（sanitize/regression_warnings）+ evaluate（OptGain）实现。✓ 无遗漏。
- **类型一致**：`ModificationType.KEYWORD="positive_keywords"` 与 spec 一致；`apply_bom_delta` 签名（delta_id, approver, new_bom_json, modifications, from_version）service 调用一致；`from_bom_version_id`（DB）vs `from_version`（BOMDelta）转换在 service 层。✓
- **placeholder 扫描**：service 层 evaluate/diagnose/optimize 给了结构与示例（apply 完整），其余标明"按同样 UoW 模式"——这是 DRY 指引（apply 是完整范本），非占位。prompts 内容指向 PoC 文件复用（避免重写）。
