# quick_poc · 规则编排智能体（两个场景）

## 怎么用（在哪填什么）

**一个条款 = 一个 yaml 文件。** 复制模板 → 改名 → 填字段 → 跑。

| 你要填的 | yaml 字段 | 场景 |
|---|---|---|
| 条款名称 | `clause:` | ①② |
| 当前语义定义 + 规则（旧 BOM） | `current_bom:`（粘贴现有） | ①② |
| 测试集期望值（选正例用） | `positive_candidates:`（列表） | ①② |
| 数量 / 语言 | `keyword_count` / `section_count` / `query_count` / `language_hint` | ①② |
| **Badcase**（期望/抽取/原文） | `badcases:`（每条 type/expected/actual/text） | ② |
| **Trace**（每条 badcase 的） | 每个 badcase 的 `trace:`（粘原文窗口/reasoning/prompt I/O） | ② |

模板：场景①用 `data/sample_generate.yaml`，场景②用 `data/sample_slice.yaml`。

```bash
cd E:/Python_Project/CC-BOMGenerator
cp config/llm.example.yaml config/llm.yaml   # 填 api_key / base_url / model
pip install -r quick_poc/requirements.txt

# 场景① 初始生成（无 badcase）
python quick_poc/rule_pipeline.py 你的条款.yaml --mode generate

# 场景② 已跑优化（有 badcase + trace）
python quick_poc/rule_pipeline.py 你的条款.yaml --mode optimize
```

输出：终端打印两阶段 JSON + 最终 BOM；存档到 `output/new_bom_<mode>_<时间>.json`。

## 从 Excel/CSV 批量导入（推荐，免手填）

测试集是 Excel/CSV 时，一键转成 yaml（一个条款一个文件），再批量跑：

```bash
python quick_poc/import_excel.py 你的测试集.xlsx         # 或 .csv
# → 生成 quick_poc/data/imported/<条款>.yaml（每条款一个）
python quick_poc/rule_pipeline.py quick_poc/data/imported/   # 批量跑全部
```

**列名自动识别**（中/英、大小写空格无关）：

| 字段 | 英文列名 | 中文列名 | 必需 |
|---|---|---|---|
| 期望值 | `expected_value` | 期望值 / 期望结果 | ✅ |
| 语义块编码 | `block_code` | 语义块编码 | 二选一 |
| 语义块名称 | `block_name` | 语义块名称 / 条款名称 | 二选一 |
| 文档ID | `doc_id` | 文档ID / 文档编号 | |
| 文档名称 | `doc_name` | 文档名称 | |
| 抽取值 | `actual_value` | 抽取值 / 实际值 | 可选 |
| 合同原文 | `text` | 合同原文 / 原文 | 可选 |

- **只有期望值** → 生成 `generate` yaml（场景①初始生成）。
- **有抽取值** → 自动识别 badcase（期望≠抽取：误抽/漏抽），生成 `optimize` yaml（场景②）。
- 生成的 yaml 自带 `mode` 字段，批量跑自动用对场景；trace 仍可手动补进 badcase。

## 两个场景

| 场景 | `--mode` | 输入 | 要 Trace？ |
|---|---|---|---|
| **① 初始生成** | `generate` | 名称 + 种子定义/规则 + 期望值（无 Badcase） | 不需要 |
| **② 已跑优化** | `optimize`（默认） | 当前 BOM + Badcase(期望/抽取/**Trace**) + 准确率 | 需要，越全越准 |

> 误抽/漏抽（症状）只要有期望值+抽取值就能定；**5 类归因（病因）必须靠 Trace**——
> 召回看原文窗口、推理看 reasoning、Prompt模板看提示词 I/O。无 Trace 时只能低置信猜测类别。

两场景都走**两步法**：召回画像(发散) → 抽取规则(收敛)，同一对话上下文连贯。

## 去重 & 手动跑（省 token / 无需 API）

**组装前自动近义去重**：候选期望值里 49/50 高度相似时，先用 `difflib` 字符相似度贪心去重（默认阈值 `0.8`，yaml 里 `dedup_threshold` 可调），防 prompt 过长/爆 token、防重复淹没模型。去重会打印 `候选去重：50 → 3`。
> 正式工具升级为 embedding + MMR（更准，Phase 2 向量库）。

**`--print-prompt` 手动模式**（不想配 API / 想用外网模型）：
```bash
python quick_poc/rule_pipeline.py 你的条款.yaml --mode optimize --print-prompt
```
直接渲染并打印 **Stage1 + Stage2 两段提示词**（存到 `output/<名>_prompts.txt`），**不调 API**：
1. 复制 Stage1 提示词 → 粘到外网模型（Gemini/Claude/ChatGPT）→ 拿回 JSON；
2. 把 JSON 粘到 Stage2 提示词的 `<<<>>>` 占位处 → 再发给模型 → 拿到最终 BOM。

此模式**无需 `config/llm.yaml`、也不用装 openai**（懒加载）。

## Trace 诊断（场景② 增强）

覆盖率型漏抽（阈值固定 80% 调不了）必须靠 trace 才能定位"是哪条规则害的"。Trace 支持 **txt** 读取：

- **输入/输出两文件**（新平台 trace 本就分开）：badcase 里写 `trace_input: xxx_input.txt` + `trace_output: xxx_output.txt`
- **或合并文件**（含"输入:"/"输出:" 标记）：`trace: xxx.txt`
- 路径相对 yaml 所在目录。

解析器自动抽出关键字段喂诊断：**当前规则/画像、合同原文窗口、模型抽取+reasoning、可用 chunks**。
诊断做**覆盖率缺口 + 边界规则冲突**分析（例：期望含付款排程，但规则要求剔除付款日 → 冲突 → 放宽该剔除规则，让模型把期望完整 span 抽出来达标）。

**格式错误会精确报位置**，例如：
`[xxx_input.txt（输入）] 第 4 行 第 1 列 JSON 解析失败：Expecting value | 附近内容：行3/行4`

> trace 为新平台导出的 JSON：输入含 `normalizedTarget`/`_fallback_chunks`/`perWindowPrompts`，输出含 `blockExtractionResults`。粘到 .txt 即可，带不带"输入:/输出:"标记都行。

## 提示词管理

**提示词与代码分离**：所有 prompt 在 `prompts/`（纯文本 + `{{var}}` 占位），代码只加载渲染，不在代码里硬编码。

```
prompts/
├─ system.txt       # 系统人设
├─ recall.txt       # 召回画像规则（数量/语言占位，两场景共用）
├─ opt_stage1.txt   # 场景② 阶段1：诊断+召回画像
├─ opt_stage2.txt   # 场景② 阶段2：定义+规则
├─ gen_stage1.txt   # 场景① 阶段1：召回画像生成
└─ gen_stage2.txt   # 场景① 阶段2：定义+规则
```
改 prompt 直接编辑这些 txt，无需动代码。

## 输出契约

**Stage 1** — generate：`{"recall_profile":{...}}`；optimize：`{"diagnosis":[...],"recall_profile":{...}}`
```json
"diagnosis": [{"case_id","case_type":"miss|false_positive","category":"5类之一","reason"}]
"recall_profile": {"positive_keywords","confusion_words","section_hints","semantic_queries","positive_examples"}
```
- `positive_keywords`：默认 **10**（`keyword_count` 可配），**短词/短语、严禁整句**（精确匹配用，整句必被过滤）；按文本语言补英文（中文为主，可用 `language_hint` 强制）。
- `section_hints`：默认 **6**（`section_count` 可配），预测章节名。
- `semantic_queries`：默认 **3**（`query_count` 可配），自然语言定义，用于向量语义匹配。
- `positive_examples`：从 `positive_candidates` 挑差异最大的 3-5 条，禁止编造（PoC 用 LLM 判断；正式工具升级为 去重+embedding/MMR）。

**Stage 2**
```json
{"semantic_definition","extraction_rules":{"absolute_interception_rules":[{"rule","fixes"}],"core_match_rules":[{"rule","fixes"}]},"self_consistency_check/coverage_check"}
```

**最终 BOM**（配进平台）= `clause` + `semantic_definition` + `recall_profile` + `extraction_rules`（optimize 另含 `diagnosis`）

## 手工闭环（准确率 = 真实平台金标准）

1. 拿 `output/new_bom_*.json`，把定义/规则/画像录入新平台 BOM 定义中心。
2. 用一批**没给大模型看过的**测试数据（hold-out）跑评测。
3. 看指标：**漏抽减少 + 没引入新误抽（回归）** = 通过 ✅ → 进入正式开发。

## 模型配置（`config/llm.yaml`，PoC 与正式工具共用）

复制模板填写（`llm.yaml` 已 gitignore，绝不入库；各自填各自的）：
```bash
cp config/llm.example.yaml config/llm.yaml
```
```yaml
api_key: "sk-..."        # 必填
base_url: ""             # 留空=默认端点；接 Gemini/自建/代理填地址
model: "gpt-4o-mini"     # 必填
temperature: 0.3         # 可选
```

> 本目录是规则编排智能体的 PoC（两步法、双场景、提示词外置、结构化 Trace 诊断）。
