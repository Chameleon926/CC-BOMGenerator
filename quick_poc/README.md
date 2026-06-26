# quick_poc · 规则编排智能体（两个场景）

## 两个场景

| 场景 | `--mode` | 输入 | 做什么 | 要 Trace？ |
|---|---|---|---|---|
| **① 初始生成** | `generate` | 条款名 + 种子定义/规则 + 测试集期望值（**无 Badcase**） | 直接生成首版 BOM | 不需要 |
| **② 已跑优化** | `optimize`（默认） | 当前 BOM + Badcase(期望/抽取) + 准确率 + Trace(多样) | 诊断(5类) → 优化 BOM | 需要，越全越准 |

> **核心区分**：误抽/漏抽（症状）只要期望值+抽取值就能定；**5 类归因（病因）必须靠 Trace**——
> 召回 vs BOM 看原文窗口、BOM vs 推理看 reasoning、Prompt模板看提示词 I/O。

两场景都走**两步法**：召回画像(发散) → 抽取规则(收敛)，同一对话上下文连贯。

## 运行

```bash
cd E:/Python_Project/CC-BOMGenerator
cp .env.example .env                 # 填 LLM_API_KEY（LLM_BASE_URL 留空=默认端点；LLM_MODEL 填模型名）
pip install -r quick_poc/requirements.txt

# 场景① 初始生成
python quick_poc/rule_pipeline.py quick_poc/data/sample_generate.yaml --mode generate

# 场景② 已跑优化
python quick_poc/rule_pipeline.py quick_poc/data/sample_slice.yaml --mode optimize
```

输出：终端打印两阶段 JSON + 最终 BOM；存档到 `quick_poc/output/new_bom_<mode>_<时间>.json`。

## 输出契约

### Stage 1
- **generate**：`{ "recall_profile": {...} }`
- **optimize**：`{ "diagnosis": [...], "recall_profile": {...} }`

```json
"diagnosis": [{"case_id","case_type":"miss|false_positive","category":"5类之一","reason"}]
"recall_profile": {"positive_keywords","confusion_words","section_hints","semantic_queries","positive_examples"}
```
> `positive_examples`：从 `positive_candidates`（测试集期望值）挑**差异最大**的 3-5 条，禁止编造/近义重复。
> （PoC 用 LLM 判断；正式工具升级为 去重 + embedding/MMR。）

### Stage 2
```json
{
  "semantic_definition": "...",
  "extraction_rules": {
    "absolute_interception_rules": [{"rule","fixes"}],
    "core_match_rules": [{"rule","fixes"}]
  },
  "self_consistency_check / coverage_check": "..."
}
```

### 最终 BOM（配进平台）= `clause` + `semantic_definition` + `recall_profile` + `extraction_rules`（optimize 另含 `diagnosis`）

## 手工闭环（准确率 = 真实平台金标准）

1. 拿 `output/new_bom_*.json`，把定义/规则/画像录入新平台 BOM 定义中心。
2. 用一批**没给大模型看过的**测试数据（hold-out）跑评测。
3. 看指标：**漏抽减少 + 没引入新误抽（回归）** = 通过 ✅ → 进入正式开发。

## 模型配置（根目录 `.env`，PoC 与正式工具共用）

- `LLM_API_KEY`：你的 key
- `LLM_BASE_URL`：**留空 = 默认端点**；接 Gemini/自建/代理填对应地址
- `LLM_MODEL`：模型名（gpt-4o-mini / gemini-2.5-flash / 自建模型名）

> 单步法版本见 `../poc/`；本目录是两步法、双场景增强版。
