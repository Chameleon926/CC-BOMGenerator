# quick_poc · 规则编排智能体（PoC）

> Excel + 选模式 → 提示词 → 外网大模型 → 业务可读 BOM。
> PoC **默认只生成提示词**（不调 API），用户复制到外网模型跑。

## 完整流程（业务照着做）

**① 选 Excel + 模式 → 生成提示词**
```bash
python quick_poc/run_excel.py 初始测试集.xlsx --mode generate   # 场景①：只有期望值，生成首版 BOM
python quick_poc/run_excel.py 跑批结果.xlsx   --mode optimize   # 场景②：有实际值/是否匹配，优化
```
控制台逐条款打印每一步：**候选去重（去掉哪些/组装多少）→ badcase 数 → Stage1/Stage2 提示词**；提示词也存到 `output/<条款>_prompts.txt`。

**② 跑 Stage1**：把 `output/<条款>_prompts.txt` 里的 **Stage1 提示词**复制到外网模型（Gemini/Claude/ChatGPT）→ 把返回 JSON 存为 `stage1.json`。

**③ 跑 Stage2**：把 Stage1 的 JSON 粘到 **Stage2 提示词**的 `<<<>>>` 占位处 → 发给模型 → 返回存为 `stage2.json`。

**④ 合并成业务可读 BOM**
```bash
python quick_poc/rule_pipeline.py --combine quick_poc/data/imported/<条款>.yaml stage1.json stage2.json
```
→ `output/<条款>_BOM_readable.md`：**业务定义 / 抽取规则(拦截+匹配) / 召回画像(关键词·易混淆·章节·语义查询·正例) / Badcase诊断**，业务直接看懂、配进平台。

## 两个模式

| `--mode` | 输入 Excel | 产出 |
|---|---|---|
| `generate` | 只有期望值 | 首版 BOM（定义+规则+画像） |
| `optimize` | 期望值 + 实际值 + 是否匹配（+ 可选 trace） | 优化后 BOM + Badcase 归因诊断 |

`run_excel` 自动按列识别：有"是否匹配/实际值"列 → optimize 圈出 `是否匹配=否` 为 badcase；否则 generate。

## Trace 字段选择（optimize，可选）

trace 很长，按需在 yaml 里 `trace_fields` 选要哪些（默认全要），省 token：
```yaml
trace_fields: [reasoning, context_window]   # 只带这两个进提示词
```
可选：`current_rules`（当前规则/画像）、`context_window`（合同原文窗口）、`model_extracted`（模型抽取）、`reasoning`（推理）、`chunks`（可用chunk）。
> trace 由 `trace_input`/`trace_output` 两 txt 提供；`run_excel` 生成的 yaml 无 trace，需要时手动补（覆盖率缺口诊断才准）。

## 去重（自动）

组装前对候选期望值做近义去重（`difflib`，防 49/50 重复淹没+爆 token），控制台打印"去掉哪些/组装多少条"。yaml `dedup_threshold`（默认 0.8）可调。

## 想自动调模型（可选）

PoC 默认出提示词。要自动调：填 `config/llm.yaml`（`cp config/llm.example.yaml config/llm.yaml`），再加 `--api`：
```bash
python quick_poc/run_excel.py 测试集.xlsx --mode optimize --api
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `run_excel.py` | **主入口**：Excel + 模式 → 提示词（一步到位） |
| `rule_pipeline.py` | 引擎：yaml→提示词/调模型；`--combine` 合并结果为可读 BOM |
| `import_excel.py` | 仅 Excel→yaml（不跑） |
| `trace_parser.py` | trace 解析（txt，输入/输出两文件，错误报行号） |
| `dedup.py` | 近义去重 |
| `prompts/` | 所有提示词（纯文本+`{{var}}`占位，改它不改代码） |
| `config/llm.yaml` | 模型配置（api_key/base_url/model） |
