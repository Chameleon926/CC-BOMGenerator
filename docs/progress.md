# 开发进度跟踪

> 开工前先读这个文件，确认对方当前进度后再开始写代码。
> 每次改完代码必须更新自己的段落。

---

## 🟦 林大宇（feature_lindayu）

### 当前任务
- **B 模块全部完成！** 5 步链路 B1→B5 全部实现，单元测试全通过。
- 下一步：写编排入口（把 B1→B5 串起来，一次调用从 CleanedTestSet 到 FullPrompt）

### 已完成
| 日期 | 模块 | 文件 | 说明 |
|------|------|------|------|
| 06-29 | M1 | contracts/ 全部 6 个文件 | 定义 BOM/TestSet/Diagnosis/Trace/Evaluation 契约 |
| 06-30 | B1 | contracts/cleaned_test_set.py | 新增 CleanedTestSet + FullPrompt 契约 |
| 06-30 | B1 | nodes/keyword_extract.py | jieba分词+词频+过滤+混淆词+聚类正例，4个测试全通过 |
| 06-30 | LLM | llm/client.py | 双格式(OpenAI/Anthropic)，讯飞星辰API实测通过 |
| 06-30 | B2 | nodes/generate.py | 调大模型出定义+规则，付款支持文档实测通过 |
| 06-30 | B3 | nodes/profile_build.py | B1统计+大模型融合画像，9项断言通过 |
| 06-30 | B4 | nodes/verify.py | 规则自检(温度0.0)，精准抓到漏抽风险 |
| 06-30 | B5 | nodes/prompt_assemble.py | 提示词模板拼装，13项断言通过 |

### 阻塞
- 暂无

### 待对方
- 等杨力写完 M5（llm/client.py）后集成到 M6 generate 的调用

---

## 🟩 杨力（feature_yangli）

### 当前任务
- （初次启动）阅读 docs/design/ 设计文档 + 功能模块拆分文档
- M5 llm/client.py —— 独立模块，随时可开工

### 已完成
| 日期 | 模块 | 文件 | 说明 |
|------|------|------|------|
| （待补充） | | | |

### 阻塞
- 暂无

### 待对方
- （待补充）