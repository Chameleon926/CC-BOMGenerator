# 反例（误抽值）注入生成管线设计

> **状态：已确认（交互 + 算法 + 数据模型全部对齐），待开发**
> **更新日期：2026-07-30**

---

## 1. 核心思路

当前生成只用正例（"抽什么"）。反例（误抽值）告诉 LLM **"别抽什么"**——一正一反，规则一次生成就更紧，减少"生成→跑分发现误抽→优化"的迭代次数。

**对称设计**：提示词里正例有【正向抽取示例】（锚定匹配规则），反例有【反向拦截示例】（锚定拦截规则/毒药词），结构完全镜像。

## 2. 数据来源

用户在**用例库**的负例行填 `actual_value`（误抽值 = 大模型不该抽但实际抽了的内容）：

```
用例库 → 条款详情 → 负例行（expected_value 空）→ 点编辑 → 填 actual_value
    │
    ▼ generate 时从 test_cases 查该 block_code 的 actual_value 非空的负例
    │
    ▼ 传入 GenerationState.misextract_values
    │
    └─ 进入生成管线（见 §4）
```

## 3. 三层配置（生成弹窗）

用户点「生成」→ 弹窗配置：

```
┌─ 生成 BOM · 收入分成 ──────────────────────────┐
│ 条款：收入分成  FSB0000007（17 个正例）        │
│                                                │
│ ┌─ 召回画像配置 ─────────────────────────────┐ │
│ │ 召回正例数量：[5 ▾]  （召回锚点，上限=去重正例数）│ │
│ └────────────────────────────────────────────┘ │
│                                                │
│ ┌─ 提示词示例配置（进最终提示词）─────────────┐ │
│ │ 正向示例数：[5 ▾]  建议 ≤5，最多 10        │ │
│ │ 反向示例数：[3 ▾]  建议 ≤5，最多 10        │ │
│ │              （当前有 3 条误抽值可用）       │ │
│ └────────────────────────────────────────────┘ │
│                                                │
│ ┌─ 其他 ──────────────────────────────────────┐ │
│ │ ☐ 跳过自检（快速测试用）                    │ │
│ └────────────────────────────────────────────┘ │
│                                                │
│                  [取消]  [生成]                 │
└────────────────────────────────────────────────┘
```

### 三个配置的职责（确认版）

| 配置 | 控制什么 | 默认值 | 上限 | 约束 |
|---|---|---|---|---|
| **召回正例数量** | recall_profile.positive_examples（召回锚点） | 5 | min(20, 去重正例总数) | — |
| **正向示例数** | 提示词【正向抽取示例】条数 | 5 | 10 | **≤ 召回正例数量** |
| **反向示例数** | 提示词【反向拦截示例】条数 | min(可用误抽数, 5) | 10 | ≤ 去重后可用误抽数 |

### 约束规则（前端 + 后端双重校验）

```
正向示例数 ≤ 召回正例数量（必须，否则截断）
反向示例数 ≤ 去重后误抽值数量（必须，没误抽时 = 0）
反向示例数 = 0 → 提示词不显示【反向拦截示例】段
```

## 4. 生成管线改动（逐节点）

### 数据模型新增

```python
# schemas/bom.py
class InterceptionExample(BaseModel):
    """典型反例（误抽内容）+ 分析理由（锚定拦截规则）。与 TypicalExample 对称。"""
    value: str = Field(..., description="误抽内容")
    reason: str = Field("", description="分析理由：为何排除（引用拦截规则/毒药词）")

class BOM(BaseModel):
    ...
    typical_examples: List[TypicalExample]          # 已有：正例+理由（锚定匹配规则）
    interception_examples: List[InterceptionExample] # 新增：反例+理由（锚定拦截规则）
```

```python
# schemas/generation_state.py
class GenerationState(BaseModel):
    ...
    misextract_values: List[str]  # 新增：用户填的误抽值（从 test_cases 查 actual_value）
```

```sql
-- alembic 0008: test_cases 加 actual_value 列
ALTER TABLE test_cases ADD COLUMN actual_value TEXT COMMENT '误抽值（用户填）';
```

### 4.0 generate 端点（入口）

```python
# 从 test_cases 查该 block_code 的误抽值
misextract = [
    tc.actual_value for tc in db.query(TestCase)
    .filter_by(block_code=block_code)
    .filter(TestCase.actual_value != None, TestCase.actual_value != "")
    .all()
]
state = GenerationState(
    ...,
    misextract_values=misextract,
)
```

### 4.1 Skill ② ExampleRetrieve（正例选取 + **反例选取新增**）

正例选取不变（TF-IDF + KMeans 聚类选 num_examples 个）。

**新增反例选取**（在正例选完后）：

```python
if state.misextract_values:
    # Step 1: 去重（TF-IDF 相似度 > 0.9 的合并取 1 条）
    unique = _dedup_similar(state.misextract_values, threshold=0.9)
    # Step 2: 按与去重后全部正例的最大 TF-IDF 相似度排序（越像正例越危险）
    scored = [(v, _max_similarity(v, state.cleaned.positive_values)) for v in unique]
    scored.sort(key=lambda x: x[1], reverse=True)
    # Step 3: 取 TOP N（N = 用户配的反向示例数，默认 min(数量, 5)）
    state.selected_misextract = [v for v, _ in scored[:state.num_interception_examples]]
else:
    state.selected_misextract = []
```

**关键：相似度参照池 = 去重后的全部正例（positive_values），不是只参照进提示词的 5 个。**

### 4.2 Skill ③ DefinitionRule（定义+规则生成）

**gen_stage1.txt prompt 增强**（只加一段，不动现有结构）：

```
【不应抽出的内容（误抽案例）】
{{misextract_text}}

以下内容不属于本条款，但容易被误匹配。生成规则时必须确保：
1. 拦截规则能拦住这些内容
2. 毒药词包含这些内容的特征词（正例中没有的）
3. 匹配规则不会匹配这些内容
```

`misextract_text` = `state.selected_misextract` 的 TOP 5（动态，0~5 个）。
**无 misextract 时此段不显示**，走现有流程不受影响。

### 4.3 Skill ④ ProfileBuild（召回画像）

从 misextract 提特征词 → 排除正例中也有的 → 安全的加入 confusion_words：

```python
if state.misextract_values:
    neg_words = {分词 from all misextract}
    pos_words = {分词 from all positive_values}
    safe_confusion = [w for w in neg_words if w not in pos_words]  # 正例没有的才安全
    ambiguous = [w for w in neg_words if w in pos_words]  # 正例也有的 = 歧义词
    # safe_confusion → 加入 confusion_words
    # ambiguous → 不加入 confusion_words（防漏召回），在 Skill ③ prompt 里提示
```

### 4.4 Skill ⑤ RuleCheck（规则校验 + **反向校验新增**）

正向校验（现有）：正例不被拦截规则误杀。
**反向校验（新增）**：误抽内容**全部**（不只进 prompt 的 TOP N）跑匹配规则 → 不应命中：

```python
for actual in state.misextract_values:  # 全量，不只 TOP N
    matched_by = [kw for kw in match_keywords if kw and len(kw) >= 2 and kw in actual]
    if matched_by:
        flags.append(f"误抽内容仍被匹配规则命中：{matched_by}（规则太宽）")
```

### 4.5 Skill ⑥ SelfCheck（自检 prompt 增强）

verify.txt 加一段（放**全部去重后**的误抽内容，不自限于 TOP N）：

```
【历史误抽内容】
请检查当前规则是否会误抽以下内容。如果会，标记红旗。

{全部去重后误抽内容}
```

**与 Skill③⑦⑧ 的区别**：
- Skill③⑦⑧ 的反例进**最终提示词**（抽取平台 LLM 看）→ TOP N（用户配，防幻觉）
- Skill⑥ 的反例是**内部自检**（我们的 LLM 检查规则）→ 尽可能多，去重后全放，按 token 预算截断（~10 条上限）
- Skill⑤ 的反例是**程序化校验**（不过 LLM）→ **全量**，零 token 成本

### 4.6 Skill ⑦ ExampleAnnotate（正例标注 + **反例标注新增**）

当前只标正例（`{"reasons": [...]}`）。扩展为同时标正反：

```
LLM prompt 分两段：
1. 正例（锚定匹配规则）："依据匹配规则『X』命中..."
2. 反例（锚定拦截规则/毒药词）："依据拦截规则『Y』排除..."

返回：
{
  "positive_reasons": [...],
  "negative_reasons": [...]
}
```

产出：
- `state.bom.typical_examples = [TypicalExample(value, reason)]`（现有）
- `state.bom.interception_examples = [InterceptionExample(value, reason)]`（新增）

### 4.7 Skill ⑧ PromptAssemble（提示词组装 + **反向示例段新增**）

assemble.txt 加【反向拦截示例】段（对称于【正向抽取示例】）：

```
【反向拦截示例】
以下示例不应被抽出，用于理解不应触发的边界。
{{interception_examples}}

【示例使用规则】
正例/反例都只用于理解语义边界，不得复制为抽取结果。
最终结果只能来自下方当前合同原文窗口。
```

`interception_examples` 动态生成：
- 0 个 → 整段不显示
- 1~5 个 → 显示对应数量

**关键：误抽内容绝不进最终提示词的正文区（只在【反向拦截示例】段出现），防止 LLM 幻觉直接输出。**

## 5. 最终提示词结构（完整）

```
目标定义
【抽取规则】拦截 / 毒药词 / 匹配
【判例分析】
【排雷思维链】
【目标画像】关键词 / 易混淆词 / 章节提示 / 语义查询
【正向抽取示例】正例 + 分析理由（锚定匹配规则）     ← 已有
【反向拦截示例】反例 + 分析理由（锚定拦截规则）     ← 新增（动态，0~5 个）
【示例使用规则】正反例都不可复制为抽取结果
--- 合同原文窗口 ---
--- 输出格式 ---
```

## 6. 前端改动

### 6.1 生成弹窗（LibraryView.vue）

从当前简单的「正例数量」一个字段 → 三字段分组（召回 / 提示词 / 其他），约束：
- 正向示例数 max = 召回正例数量
- 反向示例数 max = 去重后误抽数（无则禁用 + 提示"无可用的误抽值"）
- 反向示例数 = 0 时灰色/禁用

### 6.2 用例库负例编辑

用例库详情页（CaseDetailView）负例行加「编辑」按钮 → 填 actual_value（误抽值）。
PUT `/api/cases/{test_case_id}` 更新 actual_value。

### 6.3 任务详情页

详情页新增「反向拦截示例」卡片（对称于「典型正例」卡片）：
- 显示 interception_examples（value + 分析理由）
- 支持编辑（同 typical_examples 的编辑模式）

## 7. 实现清单（按依赖序）

```
① 数据层（已完成 schema，待 migration）
├─ bom.py: InterceptionExample + BOM.interception_examples ✅
├─ models.py: test_cases.actual_value ✅
├─ generation_state.py: misextract_values + num_interception_examples
└─ alembic 0008: test_cases 加 actual_value

② 生成端点（generate.py）
├─ 查 test_cases 的 actual_value → 传 misextract_values
├─ 新参数：num_prompt_positives / num_interception_examples
└─ 正向 ≤ 召回约束校验

③ Skill ②（example_retrieve）
├─ 反例去重 + 相似度排序 + TOP N 选取
└─ _dedup_similar / _max_similarity 纯函数（TDD）

④ Skill ③（_generate_logic + gen_stage1.txt）
├─ prompt 加【不应抽出内容】段（动态）
└─ 歧义词提示

⑤ Skill ④（_profile_logic）
├─ confusion_words 从 misextract 提取（排除正例也有的）
└─ gen_stage2.txt 不改（LLM 产 confusion_words 时有正例排除逻辑兜底）

⑥ Skill ⑤（rule_check）
└─ 反向校验：全量 misextract 不应被匹配规则命中

⑦ Skill ⑥（self_check + verify.txt）
└─ prompt 加历史误抽检查段（TOP N）

⑧ Skill ⑦（example_annotate）
├─ prompt 扩展：正例理由（匹配规则）+ 反例理由（拦截规则）
├─ _example_annotate_logic: 反向一致性校验
└─ 产 typical_examples + interception_examples

⑨ Skill ⑧（_prompt_logic + assemble.txt）
├─ _format_interception_examples 格式化
└─ assemble.txt 加【反向拦截示例】段（动态）

⑩ 前端
├─ 生成弹窗三字段分组 + 约束
├─ 用例库负例编辑（actual_value）
├─ PUT /api/cases/{test_case_id} 端点
├─ 任务详情页「反向拦截示例」卡片
└─ api/generate.js 加新参数
```

## 8. 不受影响的部分

- **生成场景**：无误抽值时完全走现有流程（misextract_values 空 → 所有新增逻辑跳过）
- **优化场景**：暂不做（太复杂，需对接召回/抽取模块接口）
- **提示词复制**：用户复制出去的提示词会包含【反向拦截示例】段（这是设计意图，帮抽取平台的大模型理解边界）

## 9. 各节点反例用量总结（三层）

| 用途 | 放多少 | 去哪 | 为什么 |
|---|---|---|---|
| **Skill③ 定义+规则** | TOP N（用户配正向示例数，默认 5） | gen_stage1.txt prompt | 引导 LLM 写更严的规则，少而精 |
| **Skill④ 召回画像** | 全量（程序化提词） | confusion_words | 提词后排除正例也有的 → 安全进 confusion |
| **Skill⑤ 规则校验** | **全量**（不过 LLM） | 程序化反向校验 | 纯代码，零 token，全量过 |
| **Skill⑥ 自检** | **全部去重后**（上限 ~10，按 token 截断） | verify.txt prompt | 内部 LLM 检查规则，尽可能多，不防幻觉 |
| **Skill⑦ 正例标注** | TOP N（同 Skill③） | example_annotate.txt prompt | 只标注进提示词的那几条 |
| **Skill⑧ 提示词组装** | TOP N（同 Skill③） | assemble.txt 最终提示词 | 进抽取平台提示词，防幻觉，必须少 |

**原则**：越靠近"最终用户提示词"的（⑧⑦③）→ 越少（防幻觉）；越靠近"内部验证"的（⑤⑥）→ 越多（求全面）。
