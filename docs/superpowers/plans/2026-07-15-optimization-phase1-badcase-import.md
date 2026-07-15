# 优化模块 阶段 1 实现计划：badcase 导入 + 判类（地基）

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐 task 实现。步骤用 `- [ ]` 勾选。

**Goal:** 用户上传 badcase 用例集（2 格式）→ 系统识别格式、派生 case_type、对空的 issue_type 启发式自动判类（召回失败/抽取失败）→ 落库，前端可查/改。

**Architecture:** 纯函数做格式识别 + case_type 派生 + 判类（易测）；service 串「解析→取源 BOM 关键词→判类→落库」事务；router 暴露 import/list/update。就地融入现有分层（enums/services/nodes/api），不改生成代码。MySQL。

**Tech Stack:** Python 3.9 + FastAPI + SQLAlchemy + Pydantic v2 + pandas（读 Excel）+ pytest。

**Spec:** `docs/superpowers/specs/2026-07-14-optimization-module-design.md`（§4-§7）。**这是 4 阶段中的阶段 1**（②optimize orchestrator / ③diff+apply / ④前端 UI 各自后续计划）。

---

## 文件结构（本阶段）

| 文件 | 职责 | 新/改 |
|---|---|---|
| `backend/src/cc_bom_generator/enums/issue_type.py` | `IssueType` 枚举（召回失败/抽取失败） | 新 |
| `backend/src/cc_bom_generator/enums/__init__.py` | 导出 IssueType | 改 |
| `backend/alembic/versions/0005_badcase_import_fields.py` | badcases 加 issue_type/auto_judged/context_text；platform_run_id 改 nullable | 新 |
| `backend/src/cc_bom_generator/db/models.py` | Badcase 加 3 列 + platform_run_id nullable | 改 |
| `backend/src/cc_bom_generator/nodes/tuning/__init__.py` | 包标记 | 新 |
| `backend/src/cc_bom_generator/nodes/tuning/_badcase_parse.py` | 格式识别 + 行归一化 + case_type 派生（纯函数） | 新 |
| `backend/src/cc_bom_generator/nodes/tuning/classifier.py` | Classifier Protocol + HeuristicClassifier（纯函数判类） | 新 |
| `backend/src/cc_bom_generator/db/tuning_repository.py` | save_badcases / list_badcases / update_issue_type / get_latest_bom_keywords | 新 |
| `backend/src/cc_bom_generator/services/tuning/__init__.py` | 包标记 | 新 |
| `backend/src/cc_bom_generator/services/tuning/badcase_service.py` | import_badcases / list_badcases / update_issue_type（事务） | 新 |
| `backend/src/cc_bom_generator/api/routers/tuning.py` | POST import / GET list / PUT update（注册到 app.py） | 新 |
| `backend/src/cc_bom_generator/app.py` | include tuning_router | 改 |
| `backend/tests/test_badcase_parse.py` | 格式识别+case_type 单测 | 新 |
| `backend/tests/test_classifier.py` | 启发式判类单测 | 新 |

---

## Task 1: IssueType 枚举

**Files:**
- Create: `backend/src/cc_bom_generator/enums/issue_type.py`
- Modify: `backend/src/cc_bom_generator/enums/__init__.py`

- [ ] **Step 1: 写枚举**

```python
# enums/issue_type.py
"""badcase 问题类型（用户手填 / 系统判类的合法值，唯一事实源）。"""
from enum import Enum


class IssueType(str, Enum):
    """badcase 归因到 optimize 的修复落点。加类型 = 加枚举值 + 路由分支。"""
    RECALL_FAIL = "召回失败"        # 画像/召回锚点问题：关键词没覆盖该用例 → 改 recall_profile
    EXTRACTION_FAIL = "抽取失败"    # BOM 定义+规则问题：召回到了没抽出 → 改 definition/rules
```

- [ ] **Step 2: 导出**

在 `enums/__init__.py` 末尾加：
```python
from .issue_type import IssueType
```

- [ ] **Step 3: 验证 + commit**

```bash
cd backend && PYTHONPATH=. python -c "from src.cc_bom_generator.enums import IssueType; print([i.value for i in IssueType])"
# 期望: ['召回失败', '抽取失败']
git add backend/src/cc_bom_generator/enums/issue_type.py backend/src/cc_bom_generator/enums/__init__.py
git commit -m "feat(enums): IssueType 召回失败/抽取失败（优化模块）"
```

---

## Task 2: Badcase 加列 + alembic 0005

**Files:**
- Modify: `backend/src/cc_bom_generator/db/models.py`（Badcase 类）
- Create: `backend/alembic/versions/0005_badcase_import_fields.py`

- [ ] **Step 1: 改 Badcase 模型**

`models.py` Badcase 类：`platform_run_id` 改 `nullable=True`（直接导入的 badcase 无 platform_run）；加 3 列：
```python
    platform_run_id = Column(Integer, ForeignKey("platform_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    # ... 现有 case_type/expected/actual/coverage/trace_json 不变 ...
    issue_type = Column(String(16), nullable=True, comment="召回失败/抽取失败（见 enums.IssueType）；NULL=未判")
    auto_judged = Column(Boolean, server_default="0", comment="是否系统自动判类（前端复核提示）")
    context_text = Column(Text, nullable=True, comment="上下文原文（2 格式都没有，留字段备用）")
```

- [ ] **Step 2: 写迁移 0005**

```python
# alembic/versions/0005_badcase_import_fields.py
"""badcases 加 issue_type/auto_judged/context_text + platform_run_id 改 nullable

Revision ID: 0005
Revises: 0004
"""
revision = "0005"
down_revision = "0004"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("badcases", sa.Column("issue_type", sa.String(16), nullable=True, comment="召回失败/抽取失败"))
    op.add_column("badcases", sa.Column("auto_judged", sa.Boolean, server_default="0", comment="是否系统自动判类"))
    op.add_column("badcases", sa.Column("context_text", sa.Text, nullable=True))
    op.alter_column("badcases", "platform_run_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    op.alter_column("badcases", "platform_run_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("badcases", "context_text")
    op.drop_column("badcases", "auto_judged")
    op.drop_column("badcases", "issue_type")
```

- [ ] **Step 3: 跑迁移 + 验证 + commit**

```bash
cd backend && PYTHONPATH=. python -m alembic upgrade head
# 期望: Running upgrade 0004 -> 0005
PYTHONPATH=. python -c "from src.cc_bom_generator.db.models import Badcase; print('issue_type' in [c.name for c in Badcase.__table__.columns])"
# 期望: True
git add backend/src/cc_bom_generator/db/models.py backend/alembic/versions/0005_badcase_import_fields.py
git commit -m "feat(db): badcases 加 issue_type/auto_judged/context_text + platform_run_id nullable（alembic 0005）"
```

---

## Task 3: badcase 解析（格式识别 + case_type 派生，纯函数）

**Files:**
- Create: `backend/src/cc_bom_generator/nodes/tuning/__init__.py`（空包标记）
- Create: `backend/src/cc_bom_generator/nodes/tuning/_badcase_parse.py`
- Test: `backend/tests/test_badcase_parse.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_badcase_parse.py
# -*- coding: utf-8 -*-
from src.cc_bom_generator.nodes.tuning._badcase_parse import detect_format, derive_case_type, parse_rows

def test_detect_format_internal():
    cols = ["文档ID","文件名","块/项名称","块/项编码","期望值","实际值","相似度","是否匹配"]
    assert detect_format(cols) == "internal"

def test_detect_format_online():
    cols = ["提示词名称","文档ID","属性类型","语义块编码","语义块名称","语义项编码","语义项名称","抽取结果","期望结果","每个测试用例的得分"]
    assert detect_format(cols) == "online"

def test_detect_format_unknown():
    assert detect_format(["a","b"]) == "unknown"

def test_derive_case_type_miss():
    assert derive_case_type(expected="预期", actual="") == "miss"

def test_derive_case_type_false_positive():
    assert derive_case_type(expected="", actual="多抽的") == "false_positive"

def test_derive_case_type_correct_has_similarity():
    assert derive_case_type(expected="a", actual="a", similarity=0.5) == "correct"

def test_derive_case_type_mismatch_zero_sim_is_fp():
    # 都非空 + 相似度≈0 → 错抽，归并 false_positive（按 spec）
    assert derive_case_type(expected="a", actual="b", similarity=0.0) == "false_positive"

def test_parse_rows_internal_filters_correct():
    rows = [
        {"文档ID":"d1","块/项编码":"FSB1","期望值":"x","实际值":"","相似度":0},        # miss
        {"文档ID":"d2","块/项编码":"FSB1","期望值":"x","实际值":"x","相似度":0.8},    # correct → 丢弃
    ]
    parsed = parse_rows(rows, "internal", block_code="FSB1")
    assert len(parsed) == 1
    assert parsed[0]["case_type"] == "miss"
    assert parsed[0]["doc_id"] == "d1"
    assert parsed[0]["issue_type"] is None  # 解析阶段不判 issue_type，留 None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. python -m pytest tests/test_badcase_parse.py -v
# 期望: FAIL（模块不存在）
```

- [ ] **Step 3: 实现**

```python
# nodes/tuning/_badcase_parse.py
"""badcase 解析纯函数：格式识别 + 行归一化 + case_type 派生。无副作用，易测。"""
from __future__ import annotations
from typing import Any, List, Optional

_CORRECT_SIMILARITY_THRESHOLD = 0.0  # >0 即正确（业务认"包含算对"）

_INTERNAL_COLS = {"文档id", "块项编码", "期望值", "实际值", "相似度"}
_ONLINE_COLS = {"提示词名称", "属性类型", "抽取结果", "期望结果", "每个测试用例的得分"}


def detect_format(columns: List[str]) -> str:
    norm = {str(c).replace(" ", "").replace("/", "").replace("_", "").lower() for c in columns}
    if _INTERNAL_COLS.issubset(norm):
        return "internal"
    if _ONLINE_COLS.issubset(norm):
        return "online"
    return "unknown"


def derive_case_type(expected: str, actual: str, similarity: Optional[float] = None) -> str:
    """miss / false_positive / correct。"""
    e, a = (expected or "").strip(), (actual or "").strip()
    if e and not a:
        return "miss"
    if not e and a:
        return "false_positive"
    if e and a:
        # 都非空：相似度>0 = correct；≈0/无 = 错抽(归并 fp)
        if similarity is not None and similarity > _CORRECT_SIMILARITY_THRESHOLD:
            return "correct"
        return "false_positive"
    return "correct"  # 都空，不当 badcase


def _norm_key(s: str) -> str:
    return str(s).replace(" ", "").replace("/", "").replace("_", "").lower()


def parse_rows(rows: List[dict], fmt: str, block_code: str) -> List[dict]:
    """把原始行归一化为 badcase dict（含 doc_id/block_code/expected/actual/similarity/case_type/issue_type=None）。
    丢弃 case_type==correct 的行（非 badcase）。"""
    out = []
    for r in rows:
        if fmt == "internal":
            bc = r.get(_find(r, ["块/项编码", "块项编码", "block_code"])) or block_code
            doc_id = r.get(_find(r, ["文档id", "文档ID", "doc_id"])) or ""
            expected = str(r.get(_find(r, ["期望值", "期望结果", "expected_value"])) or "")
            actual = str(r.get(_find(r, ["实际值", "抽取结果", "actual_value"])) or "")
            sim = _to_float(r.get(_find(r, ["相似度", "得分"])))
        else:  # online
            bc = r.get(_find(r, ["语义块编码", "block_code"])) or block_code
            doc_id = r.get(_find(r, ["文档id", "文档ID", "doc_id"])) or ""
            expected = str(r.get(_find(r, ["期望结果", "期望值"])) or "")
            actual = str(r.get(_find(r, ["抽取结果", "实际值"])) or "")
            sim = _to_float(r.get(_find(r, ["每个测试用例的得分", "得分", "相似度"])))
        ct = derive_case_type(expected, actual, sim)
        if ct == "correct":
            continue
        out.append({
            "doc_id": doc_id, "block_code": bc or block_code,
            "expected": expected, "actual": actual,
            "similarity": sim, "case_type": ct, "issue_type": None,
        })
    return out


def _find(row: dict, candidates: List[str]) -> str:
    """自适应列名查找（返回行里实际存在的列名）。"""
    nk = {_norm_key(k): k for k in row.keys()}
    for c in candidates:
        k = _norm_key(c)
        if k in nk:
            return nk[k]
    return candidates[0]  # 兜底（get 返回 None）


def _to_float(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", ) else None
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. python -m pytest tests/test_badcase_parse.py -v
# 期望: 8 passed
```

- [ ] **Step 5: commit**

```bash
git add backend/src/cc_bom_generator/nodes/tuning/__init__.py backend/src/cc_bom_generator/nodes/tuning/_badcase_parse.py backend/tests/test_badcase_parse.py
git commit -m "feat(tuning): badcase 解析纯函数（格式识别+case_type 派生，8 测试）"
```

---

## Task 4: HeuristicClassifier（启发式判类，纯函数）

**Files:**
- Create: `backend/src/cc_bom_generator/nodes/tuning/classifier.py`
- Test: `backend/tests/test_classifier.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_classifier.py
# -*- coding: utf-8 -*-
from src.cc_bom_generator.nodes.tuning.classifier import HeuristicClassifier
from src.cc_bom_generator.enums import IssueType

KW = ["分成", "收入", "结算"]

def test_fp_is_extraction_fail():
    c = HeuristicClassifier(recall_keywords=KW)
    assert c.classify({"case_type": "false_positive", "expected": "", "actual": "x"}) == IssueType.EXTRACTION_FAIL

def test_miss_with_keyword_hit_is_extraction_fail():
    c = HeuristicClassifier(recall_keywords=KW)
    # 期望值命中关键词 → 召回到了没抽出 → 抽取失败
    assert c.classify({"case_type": "miss", "expected": "收入分成比例", "actual": ""}) == IssueType.EXTRACTION_FAIL

def test_miss_without_keyword_is_recall_fail():
    c = HeuristicClassifier(recall_keywords=KW)
    # 期望值没命中任何召回关键词 → 召回失败
    assert c.classify({"case_type": "miss", "expected": "某罕见表述xyz", "actual": ""}) == IssueType.RECALL_FAIL

def test_miss_no_keywords_returns_none():
    # 无源 BOM 关键词 → miss 无法判 → None（待人工）
    c = HeuristicClassifier(recall_keywords=[])
    assert c.classify({"case_type": "miss", "expected": "收入", "actual": ""}) is None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. python -m pytest tests/test_classifier.py -v
# 期望: FAIL
```

- [ ] **Step 3: 实现**

```python
# nodes/tuning/classifier.py
"""badcase 判类策略（可插拔）。默认 HeuristicClassifier（无上下文降级启发式）。
未来加 LlmDiagnoseClassifier 实现 Classifier 协议即可，零改调用方。"""
from __future__ import annotations
from typing import List, Optional, Protocol

from ...enums import IssueType


class Classifier(Protocol):
    """判类策略接口。"""
    def classify(self, badcase: dict) -> Optional[IssueType]: ...


class HeuristicClassifier:
    """启发式判类（无上下文，按期望值关键词覆盖）。

    - false_positive（误抽/错抽）→ EXTRACTION_FAIL（规则匹配过头）
    - miss + 期望值命中≥1 召回关键词 → EXTRACTION_FAIL（召回到了没抽出）
    - miss + 未命中 → RECALL_FAIL（画像没覆盖）
    - miss + 无关键词可用 → None（无法判，待人工）
    """

    def __init__(self, recall_keywords: List[str]):
        self.recall_keywords = [k for k in (recall_keywords or []) if k]

    def classify(self, badcase: dict) -> Optional[IssueType]:
        ct = badcase.get("case_type")
        if ct == "false_positive":
            return IssueType.EXTRACTION_FAIL
        if ct == "miss":
            if not self.recall_keywords:
                return None  # 无关键词，无法判召回覆盖
            expected = (badcase.get("expected") or "")
            if any(kw and kw in expected for kw in self.recall_keywords):
                return IssueType.EXTRACTION_FAIL
            return IssueType.RECALL_FAIL
        return None
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. python -m pytest tests/test_classifier.py -v
# 期望: 4 passed
```

- [ ] **Step 5: commit**

```bash
git add backend/src/cc_bom_generator/nodes/tuning/classifier.py backend/tests/test_classifier.py
git commit -m "feat(tuning): HeuristicClassifier 启发式判类（可插拔 Classifier，4 测试）"
```

---

## Task 5: TuningRepository（badcase 持久化 + 取源 BOM 关键词）

**Files:**
- Create: `backend/src/cc_bom_generator/db/tuning_repository.py`

- [ ] **Step 1: 实现（UoW 模式，只 flush 不 commit，同 PipelineRepository）**

```python
# db/tuning_repository.py
"""调优仓储（badcase / pending_delta）。Session 注入，只 flush 不 commit（事务由 service 管）。"""
from __future__ import annotations
from typing import List, Optional

from sqlalchemy.orm import Session

from .models import Badcase, BomVersion, Clause


class TuningRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_badcases(self, rows: List[dict]) -> int:
        for r in rows:
            self.session.add(Badcase(
                block_code=r["block_code"],
                doc_id=r.get("doc_id"),
                case_type=r["case_type"],
                expected=r.get("expected"),
                actual=r.get("actual"),
                issue_type=r.get("issue_type"),       # None 或 IssueType.value
                auto_judged=r.get("auto_judged", False),
                context_text=r.get("context_text"),
            ))
        self.session.flush()
        return len(rows)

    def list_badcases(self, block_code: str = "") -> List[Badcase]:
        q = self.session.query(Badcase)
        if block_code:
            q = q.filter(Badcase.block_code == block_code)
        return q.order_by(Badcase.id.desc()).all()

    def get_badcase(self, badcase_id: int) -> Optional[Badcase]:
        return self.session.get(Badcase, badcase_id)

    def update_issue_type(self, badcase_id: int, issue_type: str, auto_judged: bool = False) -> None:
        bc = self.session.get(Badcase, badcase_id)
        if bc:
            bc.issue_type = issue_type
            bc.auto_judged = auto_judged
            self.session.flush()

    def get_latest_bom_keywords(self, block_code: str) -> List[str]:
        """取该条款最新 bom_version 的召回关键词（判类用）。无 BOM 返回 []。"""
        clause = self.session.query(Clause).filter_by(block_code=block_code).first()
        if not clause:
            return []
        bom = (
            self.session.query(BomVersion)
            .filter_by(block_code=block_code)
            .order_by(BomVersion.version.desc())
            .first()
        )
        if not bom or not bom.full_bom_json:
            return []
        return (bom.full_bom_json.get("recall_profile") or {}).get("positive_keywords") or []
```

- [ ] **Step 2: import 冒烟 + commit**

```bash
cd backend && PYTHONPATH=. python -c "from src.cc_bom_generator.db.tuning_repository import TuningRepository; print('OK')"
git add backend/src/cc_bom_generator/db/tuning_repository.py
git commit -m "feat(db): TuningRepository（badcase 持久化 + 取源 BOM 关键词）"
```

---

## Task 6: badcase_service（import 流程：解析→判类→落库，事务）

**Files:**
- Create: `backend/src/cc_bom_generator/services/tuning/__init__.py`（空包标记）
- Create: `backend/src/cc_bom_generator/services/tuning/badcase_service.py`

- [ ] **Step 1: 实现**

```python
# services/tuning/badcase_service.py
"""badcase 业务编排：导入(解析+判类+落库) / 列表 / 改 issue_type。事务边界在此。"""
from __future__ import annotations
from typing import List

import pandas as pd
from sqlalchemy.orm import Session

from ...db.tuning_repository import TuningRepository
from ...nodes.tuning._badcase_parse import detect_format, parse_rows
from ...nodes.tuning.classifier import HeuristicClassifier


def import_badcases(session: Session, file_path: str, block_code: str) -> dict:
    """读 Excel → 识别格式 → 归一化+派生 case_type → 启发式判类（空 issue_type）→ 落库。"""
    df = pd.read_excel(file_path).fillna("") if file_path.endswith((".xlsx", ".xls")) else pd.read_csv(file_path).fillna("")
    rows = df.to_dict(orient="records")
    fmt = detect_format(list(df.columns))
    if fmt == "unknown":
        raise ValueError(f"识别不了 badcase 格式（列：{list(df.columns)[:6]}...）")

    parsed = parse_rows(rows, fmt, block_code=block_code)
    repo = TuningRepository(session)
    keywords = repo.get_latest_bom_keywords(block_code)
    classifier = HeuristicClassifier(recall_keywords=keywords)

    for r in parsed:
        if not r.get("issue_type"):
            judged = classifier.classify(r)
            if judged is not None:
                r["issue_type"] = judged.value
                r["auto_judged"] = True
            # 判不了（miss 无关键词）→ issue_type 留 None，auto_judged=False（待人工）

    n = repo.save_badcases(parsed)
    session.commit()
    auto_n = sum(1 for r in parsed if r.get("auto_judged"))
    return {"format": fmt, "imported": n, "auto_judged": auto_n, "block_code": block_code}


def list_badcases(session: Session, block_code: str = "") -> List[dict]:
    repo = TuningRepository(session)
    return [_to_dict(b) for b in repo.list_badcases(block_code)]


def update_issue_type(session: Session, badcase_id: int, issue_type: str) -> None:
    repo = TuningRepository(session)
    repo.update_issue_type(badcase_id, issue_type, auto_judged=False)  # 手改 → auto_judged=False
    session.commit()


def _to_dict(b) -> dict:
    return {
        "id": b.id, "block_code": b.block_code, "doc_id": b.doc_id,
        "case_type": b.case_type,
        "expected": b.expected, "actual": b.actual,
        "issue_type": b.issue_type, "auto_judged": bool(b.auto_judged),
    }
```

> 注：`badcases` 表已有 `doc_id` 列（models.py:229），导入时落库 + 列表返回。

- [ ] **Step 2: import 冒烟 + commit**

```bash
cd backend && PYTHONPATH=. python -c "from src.cc_bom_generator.services.tuning.badcase_service import import_badcases; print('OK')"
git add backend/src/cc_bom_generator/services/tuning/__init__.py backend/src/cc_bom_generator/services/tuning/badcase_service.py
git commit -m "feat(tuning): badcase_service 导入流程（解析→取关键词→判类→落库，事务）"
```

---

## Task 7: tuning 路由 + 注册 + 冒烟

**Files:**
- Create: `backend/src/cc_bom_generator/api/routers/tuning.py`
- Modify: `backend/src/cc_bom_generator/app.py`（include tuning_router）

- [ ] **Step 1: 写路由**

```python
# api/routers/tuning.py
"""/api/tuning 优化模块路由（阶段1：badcase 导入/列表/改 issue_type）。"""
from __future__ import annotations
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_db
from ...services.tuning.badcase_service import import_badcases, list_badcases, update_issue_type

router = APIRouter()


@router.post("/tuning/badcases/import")
async def import_badcases_api(
    file: UploadFile = File(..., description="badcase Excel（内部/现网 2 格式之一）"),
    block_code: str = Form(..., description="条款编码"),
    db: Session = Depends(get_db),
):
    """上传 badcase → 自动识别格式 + 派生 case_type + 启发式判类 → 落库。"""
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        result = import_badcases(db, str(tmp_path), block_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)
    return result


@router.get("/tuning/badcases")
def list_badcases_api(block_code: str = "", db: Session = Depends(get_db)):
    return {"badcases": list_badcases(db, block_code)}


class IssueTypeUpdate(BaseModel):
    issue_type: str  # 召回失败 / 抽取失败


@router.put("/tuning/badcases/{badcase_id}")
def update_issue_type_api(badcase_id: int, body: IssueTypeUpdate, db: Session = Depends(get_db)):
    update_issue_type(db, badcase_id, body.issue_type)
    return {"status": "ok", "badcase_id": badcase_id}
```

- [ ] **Step 2: 注册到 app.py**

在 `app.py` 的 import 块加：
```python
from .api.routers.tuning import router as tuning_router
```
在 include_router 块加（config_router 后）：
```python
    app.include_router(tuning_router, prefix="/api")
```

- [ ] **Step 3: 冒烟（路由注册 + 真实导入）**

```bash
cd backend && PYTHONPATH=. python -c "
from src.cc_bom_generator.app import create_app
app = create_app()
routes = sorted({r.path for r in app.routes if hasattr(r,'path') and '/tuning/' in r.path})
print(routes)
"
# 期望: ['/api/tuning/badcases', '/api/tuning/badcases/import']  （+ PUT /{id} 不在 path 集合里因 path 含变量，正常）
```

重启后端，用 testdataset 风格造一个迷你 badcase Excel（或直接 curl 上传真 badcase 文件）测 import：
```bash
# 重启后端
# 造 mini badcase（内部格式）:
PYTHONPATH=. python -c "
import pandas as pd
pd.DataFrame({'文档ID':['d1','d2'],'文件名':['t.xlsx','t.xlsx'],'块/项名称':['收入分成','收入分成'],'块/项编码':['FSB0000007','FSB0000007'],'期望值':['收入分成比例','某罕见表述'],'实际值':['',''],'相似度':[0,0],'是否匹配':['否','否']}).to_excel('_mini_badcase.xlsx', index=False)
print('造好 _mini_badcase.xlsx')
"
curl -s -F "file=@_mini_badcase.xlsx" -F "block_code=FSB0000007" http://127.0.0.1:8000/api/tuning/badcases/import
# 期望: {"format":"internal","imported":2,"auto_judged":1,"block_code":"FSB0000007"}  （d1 命中"收入"→抽取失败自动判；d2 未命中→召回失败自动判，都 auto_judged）
curl -s "http://127.0.0.1:8000/api/tuning/badcases?block_code=FSB0000007"
# 期望: 2 条 badcase，带 issue_type
rm -f _mini_badcase.xlsx
```

- [ ] **Step 4: commit**

```bash
git add backend/src/cc_bom_generator/api/routers/tuning.py backend/src/cc_bom_generator/app.py
git commit -m "feat(api): /api/tuning badcase 导入/列表/改 issue_type 端点（阶段1 冒烟通过）"
```

---

## 阶段 1 验证清单（全部 ✅ 才算完成）
- [ ] IssueType 枚举 + 导出
- [ ] alembic 0005 跑通（badcases 加 3 列 + platform_run_id nullable）
- [ ] test_badcase_parse.py 8 项绿（格式识别 + case_type 4 分支 + parse 过滤 correct）
- [ ] test_classifier.py 4 项绿（fp→抽取失败 / miss+关键词→抽取失败 / miss 无关键词→召回失败 / miss 无源BOM→None）
- [ ] tuning_repository / badcase_service import 冒烟
- [ ] tuning 路由注册 + 真实 badcase 导入冒烟（format 识别 + auto_judged 判类生效）
- [ ] 7 个原子 commit + progress.md 同步

## 阶段 1 之后（各自独立计划）
- **阶段 2**：optimize orchestrator + skills（classify_skill/optimize_rules/optimize_profile/assemble_delta）+ pipeline_runs mode=optimize run + alembic 0006（source_bom_version_id + pending_deltas 索引）
- **阶段 3**：render_diff 纯函数 + apply_service（apply_bom_delta 乐观锁 + ConcurrencyError）
- **阶段 4**：前端优化任务 UI（OptimizeRunsView/Detail + BomDiff + badcase 导入页）
