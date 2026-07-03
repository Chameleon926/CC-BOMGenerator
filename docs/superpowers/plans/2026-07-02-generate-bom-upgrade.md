# generate BOM 精细化升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 generate 产出的 BOM 从「粗规则」升级到「对标旧平台押金/封顶 prompt 的专家级精细度」——分场景绝对拦截(带拦截逻辑) + 毒药词一票否决 + 分场景匹配 + 思维链排雷，示例保持召回锚点不进提示词。

**Architecture:** 扩 BOM 契约承载精细结构（rule+logic / poison_words / reasoning_chain）→ 改 gen_stage1 让 LLM 产精细规则（旧平台押金/封顶 prompt 做 few-shot 范本）→ 改 assemble 在提示词展示新字段（示例仍不放）→ 修回修链让 prompt 与回修后 BOM 同步。

**Tech Stack:** Python 3.9 / Pydantic v2 / 现有 LLM client（call_json）/ 现有 7 Skill 流水线。

**前置阅读：**
- 旧平台 prompt 范本（用户提供，对标精细度）：押金 `FSB00000721`（分场景绝对拦截 4 类+拦截逻辑+核心匹配+判例+毒药词+思维链）、封顶 `FSB00000624`（毒药词筛查+11 条负向排除+正反例）
- `docs/superpowers/specs/2026-07-01-tuning-loop-design.md`（BOM/契约上下文）
- 现状（Explore 已摸清）：示例已不进 prompt（保持）、assemble 模板内嵌在 `_prompt_logic.py`、回修链不含 assemble

---

## 关键设计决策（写 plan 前定死）

### 1. 新旧平台「示例」区别（已确认，本升级不动示例逻辑）
- **旧平台**：正反例 + 分析原因 → 放提示词（判例指引，给 LLM 推理参考）
- **新平台**：正反例 = 召回锚点（`recall_profile.positive_examples` / 新增 `negative_examples`），**不放提示词**（避免 LLM 直接输出示例=幻觉），**无分析原因**
- **现状**：`positive_examples` 已不进 prompt_text（`_format_profile` 跳过）。✅ 升级**保持**，不动。

### 2. 旧平台「判例分析」如何拆进新 BOM
旧平台 prompt 里「反例+正例+分析逻辑」拆成两部分：
- **分析逻辑**（"为什么拦截/为什么提取"）→ 变成 `ExtractionRule.logic`（拦截/匹配逻辑）+ `BOM.reasoning_chain`（排雷思维链）→ **放提示词**，引导 LLM 推理
- **正反例本身** → 变成召回锚点（`positive_examples` / `negative_examples`）→ **不放提示词**，无分析

### 3. 升级后的新平台提示词结构（assemble 产出）
定义 → 分场景绝对拦截(每条带 logic) → 毒药词一票否决 → 分场景核心匹配 → 思维链排雷 → 画像(关键词/混淆词/章节/语义查询，**无示例**) → 输出 JSON Schema。`#合同文本` / `#最终指令` 位置不变。

---

## File Structure（改动文件）

```
backend/src/cc_bom_generator/
├─ schemas/
│  └─ bom.py                    # 改：ExtractionRule 加 logic；ExtractionRules 加 poison_words；BOM 加 reasoning_chain；RecallProfile 加 negative_examples
├─ nodes/skills/
│  ├─ _generate_logic.py        # 改：解析 LLM 返回的精细规则（logic/poison_words/reasoning_chain）
│  └─ _prompt_logic.py          # 改：assemble 展示 poison_words/reasoning_chain/分场景规则带 logic；模板搬 prompts/assemble.txt
├─ prompts/
│  ├─ gen_stage1.txt            # 改：要求 LLM 产分场景规则+logic+毒药词+思维链；押金/封顶 prompt 做 few-shot
│  └─ assemble.txt              # 新增：assemble 模板（从 _prompt_logic 内嵌分离）
└─ nodes/orchestrator.py        # 改：回修链加 PromptAssembleSkill（回修后重 assemble）
backend/tests/skills/
├─ test_bom_upgrade.py          # 新增：契约扩展测试
├─ test_generate_logic_v2.py    # 新增：精细规则解析测试（mock LLM）
└─ test_prompt_assemble_v2.py   # 新增：assemble 展示新字段 + 示例不进 prompt
```

**不受影响的 Skill**（本升级不动算法）：FeatureExtractSkill（关键词）、ExampleRetrieveSkill（正例聚类）、RuleCheckSkill（程序化校验）、SelfCheckSkill（自检）。ProfileBuildSkill 仅小改（加产 negative_examples）。

---

# Task 1：BOM 契约扩展

**Files:**
- Modify: `backend/src/cc_bom_generator/schemas/bom.py`
- Test: `backend/tests/skills/test_bom_upgrade.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/skills/test_bom_upgrade.py
"""BOM 精细化契约测试。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.schemas.bom import (
    BOM, ExtractionRule, ExtractionRules, RecallProfile
)


def test_extraction_rule_has_logic():
    r = ExtractionRule(rule="供应商交钱的押金→拦截", logic="谁提供服务谁交钱=资金流向反，非华为对公押金")
    assert r.logic.startswith("谁提供服务")
    assert r.fixes == ""  # fixes 保留（人审用）


def test_extraction_rules_has_poison_words():
    er = ExtractionRules(poison_words=["不少于", "保底", "最低消费"])
    assert er.poison_words == ["不少于", "保底", "最低消费"]
    assert er.absolute_interception_rules == []
    assert er.core_match_rules == []


def test_bom_has_reasoning_chain():
    bom = BOM(clause="押金条款", reasoning_chain=[
        "1. 找动作实体：文本里谁交钱？谁退给谁？",
        "2. 交钱方是供应商/服务商/乙方 → 立即输出 []",
        "3. 退钱方是华为/甲方 → 钱原本是供应商交的 → 输出 []",
    ])
    assert len(bom.reasoning_chain) == 3


def test_recall_profile_has_negative_examples():
    rp = RecallProfile(negative_examples=["供应商应交纳履约保证金", "乙方向甲方支付押金"])
    assert len(rp.negative_examples) == 2
    assert rp.positive_examples == []  # 正例仍存在
```

- [ ] **Step 2: 跑测试验证失败**

Run: `PYTHONPATH=backend python -m pytest backend/tests/skills/test_bom_upgrade.py -v`
Expected: FAIL（`logic` / `poison_words` / `reasoning_chain` / `negative_examples` 字段不存在）

- [ ] **Step 3: 改 bom.py**

修改 `backend/src/cc_bom_generator/schemas/bom.py`：

`ExtractionRule` 加 `logic` 字段（rule 后）：
```python
class ExtractionRule(BaseModel):
    rule: str = Field(..., description="纯规则逻辑（命中/提取条件）, 不改写 platform 预期输出")
    logic: str = Field("", description="拦截/匹配逻辑（为什么这样判，引导 LLM 推理；放提示词）")
    fixes: str = Field("", description="修订依据（人审用，不录入 platform 规则）")
```

`ExtractionRules` 加 `poison_words`（core_match_rules 后）：
```python
class ExtractionRules(BaseModel):
    absolute_interception_rules: List[ExtractionRule] = Field(
        default_factory=list, description="绝对拦截规则（分场景，命中即放弃，针对误抽）"
    )
    core_match_rules: List[ExtractionRule] = Field(
        default_factory=list, description="核心匹配规则（分场景，提取条件，针对漏抽）"
    )
    poison_words: List[str] = Field(
        default_factory=list, description="毒药词（一票否决，命中即判非本条款，如 不少于/保底/最低消费）"
    )
```

`RecallProfile` 加 `negative_examples`（positive_examples 后）：
```python
    negative_examples: List[str] = Field(
        default_factory=list, description="反例参考（召回排除锚点，不进抽取提示词，无分析原因）"
    )
```

`BOM` 加 `reasoning_chain`（recall_profile 后、created_at 前）：
```python
    reasoning_chain: List[str] = Field(
        default_factory=list, description="思维链/排雷步骤（引导 LLM 应用规则，放提示词）"
    )
```

- [ ] **Step 4: 跑测试验证通过 + 回归**

Run: `PYTHONPATH=backend python -m pytest backend/tests/skills/test_bom_upgrade.py backend/tests/test_verify.py backend/tests/test_orchestrator.py::test_rule_check -v`
Expected: 新 4 项 passed + 回归不破（现有用到 ExtractionRule/BOM 的测试仍过，因新字段都有默认值）

- [ ] **Step 5: commit**

```bash
git add backend/src/cc_bom_generator/schemas/bom.py backend/tests/skills/test_bom_upgrade.py
git commit -m "feat(schemas): BOM 精细化契约（ExtractionRule.logic/poison_words/reasoning_chain/negative_examples）[generate-升级-T1]"
```

---

# Task 2：gen_stage1 改造（LLM 产精细规则 + 思维链 + 毒药词 + few-shot）

**Files:**
- Modify: `prompts/gen_stage1.txt`（要求 LLM 产精细结构）
- Modify: `backend/src/cc_bom_generator/nodes/skills/_generate_logic.py`（解析新字段）
- Test: `backend/tests/skills/test_generate_logic_v2.py`

**算法设计（DefinitionRuleSkill 升级后）**：
- **输入**：`cleaned`（正例）+ `keywords`（B1 抽的，辅助）+ `current_bom`（回修时种子）
- **调 LLM**：gen_stage1.txt（temp 0.2），喂 `{{clause}}` `{{cands}}` `{{current_bom}}` `{{few_shot}}`（押金/封顶 prompt 精简版做范本）
- **LLM 产出**（JSON）：`semantic_definition` + `extraction_rules{absolute_interception_rules[]{rule,logic}, core_match_rules[]{rule,logic}, poison_words[]}` + `reasoning_chain[]` + `coverage_check`
- **程序化兜底**：`_sanitize_poison_words`（毒药词去重/去空/统一格式）
- **写到 state**：`bom.semantic_definition` / `bom.extraction_rules`（含 logic/poison_words）/ `bom.reasoning_chain`

- [ ] **Step 1: 写失败测试（mock LLM 返回精细结构）**

```python
# backend/tests/skills/test_generate_logic_v2.py
"""gen_stage1 精细规则解析测试（mock LLM）。"""
import sys, os, json
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.nodes.skills._generate_logic import generate_definition_and_rules
from src.cc_bom_generator.schemas.cleaned_test_set import CleanedTestSet


def _mock_cleaned():
    return CleanedTestSet(clause="华为向供应商支付押金条款", block_code="FSB00000721",
                          positive_values=["甲方向乙方支付押金", "Party A shall pay deposit"])


@patch("src.cc_bom_generator.nodes.skills._generate_logic.call_json")
def test_parse_fine_grained_rules(mock_call):
    mock_call.return_value = {
        "semantic_definition": "华为主动向供应商支付的押金/保证金",
        "extraction_rules": {
            "absolute_interception_rules": [
                {"rule": "供应商主动付款→拦截", "logic": "提供服务方交钱=资金流向反"},
                {"rule": "华为退款/扣款→拦截", "logic": "华为退钱说明钱本是供应商交的"},
            ],
            "core_match_rules": [
                {"rule": "甲方向乙方支付押金/deposit→提取", "logic": "甲方(华为)主动付，方向对"},
            ],
            "poison_words": ["履约保证金", "不少于", "保底"],
        },
        "reasoning_chain": ["1.找动作实体谁交钱", "2.供应商交→[]", "3.华为退→[]"],
    }
    bom = generate_definition_and_rules(_mock_cleaned(), keywords=["押金", "deposit"])
    assert "华为主动" in bom.semantic_definition
    assert len(bom.extraction_rules.absolute_interception_rules) == 2
    assert bom.extraction_rules.absolute_interception_rules[0].logic.startswith("提供服务方")
    assert bom.extraction_rules.poison_words == ["履约保证金", "不少于", "保底"]
    assert len(bom.reasoning_chain) == 3


@patch("src.cc_bom_generator.nodes.skills._generate_logic.call_json")
def test_poison_words_dedup(mock_call):
    mock_call.return_value = {
        "semantic_definition": "x",
        "extraction_rules": {"absolute_interception_rules": [], "core_match_rules": [],
                             "poison_words": ["保底", "保底", " 不少于 ", ""]},
        "reasoning_chain": [],
    }
    bom = generate_definition_and_rules(_mock_cleaned())
    assert bom.extraction_rules.poison_words == ["保底", "不少于"]  # 去重+去空+trim
```

- [ ] **Step 2: 跑测试验证失败**

Run: `PYTHONPATH=backend python -m pytest backend/tests/skills/test_generate_logic_v2.py -v`
Expected: FAIL（解析逻辑不产 logic/poison_words/reasoning_chain）

- [ ] **Step 3: 改 gen_stage1.txt**

读现有 `prompts/gen_stage1.txt`，改要求 LLM 产出的 JSON 结构为：
```
{
  "semantic_definition": "...（自然语言定义，结尾附排除说明）",
  "extraction_rules": {
    "absolute_intersection_rules": [{"rule":"分场景拦截条件", "logic":"为什么拦截（资金流向/语义特征）"}, ...],
    "core_match_rules": [{"rule":"分场景匹配条件", "logic":"为什么提取"}, ...],
    "poison_words": ["一票否决词，如 不少于/保底/最低消费/履约保证金"]
  },
  "reasoning_chain": ["排雷步骤1：找动作实体", "步骤2：判断方向", ...],
  "coverage_check": "覆盖率自评"
}
```

prompt 关键约束（写进 gen_stage1.txt）：
- 绝对拦截必须**分场景**（参考押金 prompt 的 4 类：供应商付款/退款推演/一票否决词/自然人），每条带 `logic`（拦截依据）
- 核心匹配分场景，每条带 `logic`
- 毒药词：本条款最易误抽的"一票否决"词（参考封顶 prompt 的 不少于/保底/最低消费）
- 思维链：LLM 抽取时应执行的"排雷步骤"（参考押金 prompt 的"输出前终极排雷思考链"）
- **正反例不要在规则里写**（示例是召回锚点，另存，不进提示词）

few-shot 喂法：在 gen_stage1.txt 末尾加 `{{few_shot}}` 占位，渲染时注入**精简版**押金/封顶 prompt（只保留"分场景拦截+logic+毒药词+思维链"结构，去掉具体合同文本/示例），让 LLM 学精细度。few_shot 文本作为常量在 `_generate_logic.py` 里（不入库的范本）。

- [ ] **Step 4: 改 _generate_logic.py**

读现有 `_generate_logic.py`，改 `generate_definition_and_rules`：
- `call_json` 返回后，解析 `extraction_rules.absolute_interception_rules`（每条带 logic）→ `ExtractionRule(rule, logic)`
- 解析 `poison_words` → `bom.extraction_rules.poison_words`（经 `_sanitize_poison_words` 去重去空 trim）
- 解析 `reasoning_chain` → `bom.reasoning_chain`
- 加 `_sanitize_poison_words(words)`：`list(dict.fromkeys(w.strip() for w in words if w.strip()))`（去重保序去空）

- [ ] **Step 5: 跑测试通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/skills/test_generate_logic_v2.py -v`
Expected: 2 passed

- [ ] **Step 6: commit**

```bash
git add prompts/gen_stage1.txt backend/src/cc_bom_generator/nodes/skills/_generate_logic.py backend/tests/skills/test_generate_logic_v2.py
git commit -m "feat(generate): gen_stage1 产精细规则(分场景+logic)+毒药词+思维链，押金/封顶 few-shot [generate-升级-T2]"
```

---

# Task 3：assemble 改造（展示精细字段 + 模板分离 + 示例仍不放）

**Files:**
- Create: `prompts/assemble.txt`（从 _prompt_logic 内嵌模板分离）
- Modify: `backend/src/cc_bom_generator/nodes/skills/_prompt_logic.py`（渲染 assemble.txt + 展示 poison_words/reasoning_chain/logic）
- Test: `backend/tests/skills/test_prompt_assemble_v2.py`

**算法设计（PromptAssembleSkill 升级后）**：
- **输入**：`bom`（含精细规则 + reasoning_chain）
- **不调 LLM**：纯模板渲染 `assemble.txt`
- **组装**：定义 → 分场景绝对拦截(每条 rule+logic) → **毒药词一票否决** → 分场景核心匹配(rule+logic) → **思维链排雷** → 画像(关键词/混淆词/章节/语义查询，**无 positive_examples/negative_examples**) → 输出 JSON Schema
- **写到 state**：`full_prompt.prompt_text`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/skills/test_prompt_assemble_v2.py
"""assemble 精细字段展示 + 示例不进 prompt 测试。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.nodes.skills._prompt_logic import assemble_prompt
from src.cc_bom_generator.schemas.bom import BOM, ExtractionRule, ExtractionRules, RecallProfile


def _bom():
    return BOM(
        clause="押金条款", block_code="FSB00000721",
        semantic_definition="华为主动向供应商支付的押金",
        extraction_rules=ExtractionRules(
            absolute_interception_rules=[ExtractionRule(rule="供应商交钱→拦", logic="资金流向反")],
            core_match_rules=[ExtractionRule(rule="甲方付押金→提", logic="方向对")],
            poison_words=["不少于", "保底"],
        ),
        reasoning_chain=["1.找谁交钱", "2.供应商交→[]"],
        recall_profile=RecallProfile(
            positive_keywords=["押金"], confusion_words=["退款"],
            section_hints=["付款条款"], semantic_queries=["谁付押金"],
            positive_examples=["这是正例不应进prompt"], negative_examples=["这是反例不应进prompt"],
        ),
    )


def test_prompt_has_poison_words_and_logic():
    p = assemble_prompt(_bom())
    assert "毒药词" in p.prompt_text or "不少于" in p.prompt_text
    assert "资金流向反" in p.prompt_text  # logic 进了 prompt


def test_prompt_has_reasoning_chain():
    p = assemble_prompt(_bom())
    assert "找谁交钱" in p.prompt_text  # reasoning_chain 进了


def test_examples_not_in_prompt():
    p = assemble_prompt(_bom())
    assert "这是正例不应进prompt" not in p.prompt_text  # 正例不进
    assert "这是反例不应进prompt" not in p.prompt_text  # 反例不进
```

- [ ] **Step 2: 跑测试验证失败**

Run: `PYTHONPATH=backend python -m pytest backend/tests/skills/test_prompt_assemble_v2.py -v`
Expected: FAIL（poison_words/reasoning_chain/logic 没进 prompt）

- [ ] **Step 3: 建 prompts/assemble.txt**

把 `_prompt_logic.py` 的 `_TEMPLATE` 搬到 `prompts/assemble.txt`，加 `{{poison_words}}` `{{reasoning_chain}}` 段，规则段加 logic 展示。结构（占位符）：
```
你是一个专业的合同条款抽取助手。请从合同原文窗口中抽取语义块：{{clause}}（{{block_code}}）

目标定义：
{{definition}}

【抽取规则 — 必须严格遵守】
### 绝对拦截（命中即放弃，分场景）
{{interception_rules}}   # 每条：规则 + 【拦截逻辑】
### 毒药词（一票否决，命中即判非本条款）
{{poison_words}}
### 核心匹配（满足任一即提取，分场景）
{{match_rules}}          # 每条：规则 + 【匹配逻辑】

【排雷思维链】（抽取前必走）
{{reasoning_chain}}

【目标画像】
正向关键词：{{positive_keywords}}
易混淆词：{{confusion_words}}
章节提示：{{section_hints}}
语义查询：{{semantic_queries}}

# 抽取完整性与边界原则
精准截取...（保留原有 3 条边界原则）

输出 JSON Schema：
{{output_schema}}   # blockExtractions[]
```

**不放** positive_examples / negative_examples。

- [ ] **Step 4: 改 _prompt_logic.py**

把 `assemble_prompt` 改为 `render_prompt("assemble", ...)` + `_format_rules_with_logic` + `_format_poison_words` + `_format_reasoning_chain`。删 `_TEMPLATE` 常量（搬到 assemble.txt）。`_format_profile` 保持不放 examples（现状已对）。

- [ ] **Step 5: 跑测试通过**

Run: `PYTHONPATH=backend python -m pytest backend/tests/skills/test_prompt_assemble_v2.py backend/tests/test_prompt_assemble.py -v`
Expected: 新 3 项 passed + 旧 test_prompt_assemble.py 不破（或按新结构调整旧测试断言）

- [ ] **Step 6: commit**

```bash
git add prompts/assemble.txt backend/src/cc_bom_generator/nodes/skills/_prompt_logic.py backend/tests/skills/test_prompt_assemble_v2.py
git commit -m "feat(generate): assemble 展示精细规则(分场景+logic)+毒药词+思维链，模板分离 assemble.txt，示例不放 [generate-升级-T3]"
```

---

# Task 4：回修链修（回修后重 assemble，prompt 与 BOM 同步）

**Files:**
- Modify: `backend/src/cc_bom_generator/nodes/orchestrator.py`（`_default_retry_skills` 加 PromptAssembleSkill）

- [ ] **Step 1: 读现状确认**

读 `orchestrator.py` 的 `_default_retry_skills`（当前：DefinitionRule → ProfileBuild → RuleCheck → SelfCheck，**不含 PromptAssemble**）。

- [ ] **Step 2: 改 _default_retry_skills 加 PromptAssembleSkill**

```python
def _default_retry_skills(self) -> List[BaseSkill]:
    from .skills.definition_rule import DefinitionRuleSkill
    from .skills.profile_build_skill import ProfileBuildSkill
    from .skills.rule_check import RuleCheckSkill
    from .skills.self_check import SelfCheckSkill
    from .skills.prompt_assemble_skill import PromptAssembleSkill
    return [DefinitionRuleSkill(), ProfileBuildSkill(), RuleCheckSkill(), SelfCheckSkill(), PromptAssembleSkill()]
```

这样回修后 BOM（精细规则）重新 assemble → prompt_text 与回修后 BOM 同步。

- [ ] **Step 3: 跑回归测试**

Run: `PYTHONPATH=backend python -m pytest backend/tests/test_orchestrator.py::test_rule_check backend/tests/test_orchestrator.py::test_extract_rule_keywords -v`
Expected: passed（回修链加 assemble 不影响这两个不写库测试）

- [ ] **Step 4: commit**

```bash
git add backend/src/cc_bom_generator/nodes/orchestrator.py
git commit -m "fix(orchestrator): 回修链加 PromptAssembleSkill，回修后 prompt 与 BOM 同步 [generate-升级-T4]"
```

---

# Task 5：画像加 negative_examples（反例召回锚点）

**Files:**
- Modify: `prompts/gen_stage2.txt`（要求 LLM 产 negative_examples）
- Modify: `backend/src/cc_bom_generator/nodes/skills/_profile_logic.py`（解析 negative_examples）

- [ ] **Step 1: 写测试**（mock LLM 产 negative_examples，断言 `bom.recall_profile.negative_examples`）

- [ ] **Step 2: 改 gen_stage2.txt**（JSON 输出加 `negative_examples[]`，注明"反例，召回排除用，不进提示词，无分析"）

- [ ] **Step 3: 改 _profile_logic.py**（`_merge_profile` 解析 negative_examples → `RecallProfile.negative_examples`）

- [ ] **Step 4: 跑测试 + commit**

```bash
git commit -m "feat(generate): 画像加 negative_examples 反例召回锚点 [generate-升级-T5]"
```

---

# Task 6：端到端验证

- [ ] **Step 1: 重启后端**（TaskStop 旧服务 + 起新 uvicorn）
- [ ] **Step 2: 跑 generate**（curl POST /generate 上传 `test/docs/procurement_payment_support_documents.xlsx`）
- [ ] **Step 3: 验证 BOM 精细化**（GET /runs/{id}/result）：`extraction_rules.absolute_interception_rules` 每条有 logic、`poison_words` 非空、`reasoning_chain` 非空
- [ ] **Step 4: 验证提示词**（result.full_prompt.prompt_text）：含毒药词段、思维链段、规则带 logic、**不含 positive_examples**
- [ ] **Step 5: 派 2 个专家 agent 审视产出**（合同商务专家审规则业务正确性；agent 架构专家审算法/提示词结构）—— 见下方"专家审视"

---

## 专家审视（用户要求：合同商务数据业务专家 + agent 架构业务专家，逐节点）

实施完 Task 1-5 后，派两个子 agent 并行审视：

**Agent A — 合同商务数据业务专家**（审业务规则正确性）：
- 拿押金/封顶旧 prompt 做"金标准"，对比 generate 升级后产出的 BOM 规则
- 逐节点审：定义是否准确 / 绝对拦截分场景是否覆盖（供应商付款/退款/一票否决/自然人等）/ 毒药词是否抓全 / 匹配规则是否漏场景 / 思维链是否能引导正确推理
- 输出：业务正确性评分 + 漏判/误判清单

**Agent B — agent 架构业务专家**（审算法/架构）：
- 审每个 Skill 的算法设计：FeatureExtract（关键词算法）/ DefinitionRule（gen_stage1 精细化 + few-shot 喂法）/ ProfileBuild（融合）/ RuleCheck（程序化校验）/ SelfCheck / assemble（组装顺序 + 示例隔离）
- 审 BOM 契约扩展是否合理（logic/poison_words/reasoning_chain 字段）/ 回修链 / 提示词结构
- 输出：架构合理性评估 + 算法改进建议

两个 agent 的审视结果回流到 plan，发现的问题新建 task 修。

---

## Self-Review

**1. Spec 覆盖**：
- BOM 精细化（logic/poison_words/reasoning_chain/negative_examples）→ Task 1 ✅
- gen_stage1 产精细规则 + 思维链 + 毒药词 + few-shot → Task 2 ✅
- assemble 展示新字段 + 示例不放 → Task 3 ✅
- 回修链 prompt/BOM 同步 → Task 4 ✅
- negative_examples 召回锚点 → Task 5 ✅
- 示例不放提示词（用户强调）→ 现状已满足 + Task 3 测试断言保证 ✅
- #合同文本 / #最终指令 不变 → assemble.txt 保留位置 ✅

**2. 占位扫描**：Task 5 Step 1-3 简写（测试/prompt/解析），实现时按 Task 1-4 模式补全代码（同模式，非占位）。其余 task 有完整代码/规范。

**3. 类型一致**：`ExtractionRule.logic` / `ExtractionRules.poison_words` / `BOM.reasoning_chain` / `RecallProfile.negative_examples` 在 Task 1 定义，Task 2/3/5 使用一致。

**4. 关键风险**：
- gen_stage1 prompt 改造质量决定精细规则好坏（需迭代 + few-shot 喂好）→ Task 2 是核心，专家 Agent A 重点审
- 旧测试（test_prompt_assemble.py）可能因 assemble 结构变而破 → Task 3 Step 5 回归，按新结构调断言

---

# 🔧 专家审视修正（实施前必读）

两个专家 agent 审视（合同商务 6/10 + agent 架构 7/10），抓出以下漏点。**实施时必须按下述修正补，否则升级对标金标准会塌**。

## P0 致命漏点（两个专家一致）

### M1. RuleCheck / SelfCheck 不能「不动」（原 plan 核心误判）
- **问题**：原 plan 列 RuleCheck/SelfCheck「不受影响」。但押金核心风险是「资金流向反」（供应商交钱被抽成华为押金），RuleCheck 纯字面命中**抓不到语义方向**；SelfCheck 不知道 poison_words/reasoning_chain，无法自检方向反/毒药词误伤。
- **修正**：
  - **新增 Task 4b：RuleCheck 升级** —— 读 `bom.extraction_rules.poison_words`，校验「每个正例不含任何毒药词」（毒药词命中正例=硬错误，说明毒药词选错）；按 `scene` 分桶统计拦截覆盖率（配合 M4）。
  - **新增 Task 4c：SelfCheck 升级** —— 改 `verify.txt`，强制 LLM 自检时**走完 `bom.reasoning_chain`**，重点查三类业务致命错：①资金/方向是否反 ②主体是否错位（自然人 vs 法人）③毒药词是否误伤正例。

### M2. 回修链种子不带新字段（回修退化，最高优先级）
- **问题**：`_build_retry_bom_text`（orchestrator.py）只拼 `rule` 文本，没拼 logic/poison_words/reasoning_chain/scene_judgments → 回修时 gen_stage1 看不到上轮精细字段，**回修产出退化回粗规则，精细化白做**。
- **修正**：Task 4 必须**同步改 `_build_retry_bom_text`**（拼 logic/poison_words/reasoning_chain/scene_judgments）+ `_collect_retry_feedback`（把 SelfCheck red_flags 注入回修 prompt，不只是 log）。**和 Task 2 一起做**（同改回修链路）。

### M3. gen_stage1 输出稳定性（深嵌套 JSON）
- **问题**：一次产 定义+分场景规则(带 logic)+毒药词+思维链，JSON 嵌套 3 层、字段多，`call_json` 只 retry 1 次，讯飞星辰截断/格式损坏概率高。
- **修正**：Task 2 把 gen_stage1 的 `call_json` retry 提到 **2** + prompt 补「带占位值的完整 JSON 骨架示例」（纯结构示例，非 few-shot 风格）。few-shot 硬性 **cap ≤800 字**（只留场景标题+logic 示例+毒药词示例+思维链步骤标题）。

## P1 重要漏点

### M4. 缺 `scene` 字段（分场景归属）
- **问题**：ExtractionRule 只有 {rule,logic,fixes}，无场景分类。金标准押金 4 场景/封顶 11 排除需要场景归属（回修/评估才能定位「哪个场景漏了」）。
- **修正**：Task 1 加 `ExtractionRule.scene: str = ""`（场景名，如「供应商主动付款」「退款推演陷阱」）。gen_stage1 要求每条 rule 带 scene，且 scene 可枚举。

### M5. 缺判例分析承载（推理引导丢失）
- **问题**：旧平台「判例（反例+分析逻辑）」引导 LLM 推理。新平台把分析拆进 logic/reasoning_chain、案例踢出提示词 → **分析脱离案例，推理力度打折**。
- **修正**：Task 1 加 `BOM.scene_judgments: List[SceneJudgment]`，`SceneJudgment = {scene, negative_case(脱敏短句), positive_case(脱敏短句), analysis(分析逻辑)}`。**判例分析进提示词**（引导推理），判例原文走召回锚点不进。assemble 展示 scene_judgments。
  > 这是「示例不进提示词」原则的精确边界：**示例原文不进（防幻觉），但脱敏后的「判例分析」进（保推理引导）**。

### M6. few-shot 外置 + 异构条款
- **问题**：few-shot 硬编码 `_generate_logic.py` 违反 prompt/代码分离铁律；只喂押金/封顶 → LLM 对其他条款强套模板，产**虚假毒药词**。
- **修正**：few-shot 放 `prompts/_fewshot_*.txt`（≤800字，render_prompt 注入）；喂 **3-5 类异构条款**（方向敏感型=押金 / 数量承诺型=封顶 / 普通匹配型=违约金 / 时间区间型=质保期）。gen_stage1 加约束「**本条款无『一票否决』语义时，poison_words 必须为空数组**」+ 内嵌「业务场景分类框架」（方向反转/退款推演/数量承诺/主体资格/相邻条款混淆）让 LLM 按框架穷举。

## P2 顺手修

- **M7**. `bom._coverage_check = ...` 在 Pydantic v2 报错（latent bug）→ 删行改 `log.info`，或 BOM 加 `coverage_check: str = ""` 字段（后者利于调优追溯，推荐）。
- **M8**. `_format_rules` 现有 bug（用拦截规则存在性决定匹配规则标题「下面3点」）→ Task 3 **重写** `_format_rules`，不新旧并存。
- **M9**. `poison_words` 规范化下沉 `ExtractionRules.model_validator`（去重+trim+去空），契约自守（optimize/apply 路径也守）。
- **M10**. `ExtractionRule.logic` 加 `max_length=120`（防 LLM 写长段稀释规则权重）。

## 修正后的 task 顺序

```
Task 1（契约：+ scene/scene_judgments + M9 model_validator + M10 logic max_length）
  ↓
Task 2（gen_stage1：M3 retry=2+骨架 / M6 few-shot 外置+异构 / M7 修 _coverage_check）
  ↓
Task 4（回修链：M2 改 _build_retry_bom_text 带 logic/poison/reasoning/scene_judgments + red_flags 注入）—— 与 Task 2 同批
  ↓
Task 4b（RuleCheck 升级：M1 读 poison_words 校验误杀 + 按 scene 分桶覆盖率）
Task 4c（SelfCheck 升级：M1 verify.txt 走 reasoning_chain，自检方向反/主体错/毒药词误伤）
  ↓
Task 3（assemble：M8 重写 _format_rules + 展示 scene_judgments + 毒药词/易混淆词分层）
Task 5（画像 negative_examples）
  ↓
Task 6（端到端 + 回归案例）
```

## Task 6 回归案例（新增，验业务正确性）

| 案例 | 输入 | 期望 | 验证点 |
|---|---|---|---|
| 押金方向反 | 「供应商应交纳履约保证金…华为退给供应商」 | generate **不抽**（返回 [] 或拦截） | reasoning_chain + SelfCheck 抓资金流向反 |
| 封顶保底混淆 | 「甲方承诺采购金额不少于 2 亿元」 | generate **不抽** | 毒药词「不少于」一票否决 |
| 履约保证金 | 「供应商交纳履约保证金 10 万」 | generate **不抽** | 毒药词「履约保证金」+ 拦截场景 |

> 原 Task 6 只验「字段非空」，现加「**业务正确**」回归（押金方向反 / 封顶保底混淆 / 履约保证金），确保升级真的对标金标准。
