# quick_poc · 两步法规则编排智能体

## 为什么拆两步

> **召回画像（发散：找同义词/易混淆词）与抽取规则（收敛：边界/拦截排他）在认知上冲突。**
> 拆开后，先让模型做"归因 + 召回画像"，再基于结论做"规则精炼"，杜绝逻辑混乱。

```
Stage 1  Recall_Agent  →  逐条归因(5类) + 召回画像      （发散）
Stage 2  Rule_Agent    →  语义定义 + 抽取规则(拦截/匹配)  （收敛，接 Stage1 上下文）
Combine  最终新 BOM    →  配进平台跑准确率
```

## 运行

```bash
cd E:/Python_Project/CC-BOMGenerator
cp .env.example .env                 # 填 LLM_API_KEY（LLM_BASE_URL 留空=默认端点；LLM_MODEL 填你的模型）
pip install -r quick_poc/requirements.txt
# 把 quick_poc/data/sample_slice.yaml 换成真实低准确率条款的数据
python quick_poc/rule_pipeline.py quick_poc/data/sample_slice.yaml
```

输出：终端打印两阶段 JSON + 最终 BOM；并存档到 `quick_poc/output/new_bom_<时间>.json`。

## 输出契约

### Stage 1（诊断 + 召回画像）
```json
{
  "diagnosis": [{"case_id","case_type":"miss|false_positive","category":"5类之一","reason"}],
  "recall_profile": {"positive_keywords","confusion_words","section_hints","semantic_queries","positive_examples"}
}
```
> `positive_examples`：从 yaml 的 `positive_candidates`（测试集期望值）中挑选**互相差异最大**的 3-5 条，禁止编造、禁止挑近义重复。（PoC 用 LLM 判断；正式工具升级为 去重 + embedding/MMR。）

### Stage 2（定义 + 抽取规则）
```json
{
  "semantic_definition": "...",
  "extraction_rules": {
    "absolute_interception_rules": [{"rule","fixes"}],
    "core_match_rules": [{"rule","fixes"}]
  },
  "self_consistency_check": "..."
}
```

### 最终 BOM（配进平台）= `clause` + `semantic_definition` + `recall_profile` + `extraction_rules`

## 手工闭环（准确率 = 真实平台金标准）

1. 拿 `output/new_bom_*.json` 里的新定义/规则/画像，**录入新平台 BOM 定义中心**。
2. 用一批**没给大模型看过的**测试数据（hold-out）跑评测。
3. 看指标：**漏抽减少 + 没引入新误抽（回归）** = 通过 ✅ → 可进入正式开发。

## 模型配置

全部走根目录 `.env`（PoC 与正式工具共用）：
- `LLM_API_KEY`：你的 key
- `LLM_BASE_URL`：**留空 = 默认端点**；接 Gemini/自建/代理填对应地址
- `LLM_MODEL`：模型名（gpt-4o-mini / gemini-2.5-flash / 自建模型名）

> 单步法版本见 `../poc/`；本目录是两步法增强版。
