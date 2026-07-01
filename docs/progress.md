# 开发进度跟踪

> 开工前先读这个文件，确认对方当前进度后再开始写代码。
> 每次改完代码必须更新自己的段落。

---

## 🟦 林大宇（feature_lindayu）

### 当前任务
- Step 1 完成（修 recorder + 删旧 nodes + 抽 enums）。
- 下一步：**Step 2 分层重构**（contracts→schemas、recorder→Repository 类、main.py→api/routers + services）
- 再下一步：Step 3 Agent 化（BaseSkill 加 reads/writes、orchestrator 解耦 DB）

### 已完成
| 日期 | 模块 | 文件 | 说明 |
|------|------|------|------|
| 06-29 | M1 | contracts/ 全部 8 个文件 | 定义 BOM/TestSet/Diagnosis/Trace/Evaluation/GenerationState/CleanedTestSet/FullPrompt |
| 06-30 | B1-B5 | nodes/skills/ + _*_logic.py | B模块全链路（关键词→定义规则→画像→自检→组装） |
| 06-30 | LLM | llm/client.py | 双格式(OpenAI/Anthropic)，讯飞星辰API实测通过 |
| 06-30 | 重构 | nodes/orchestrator.py + skills/ | Node/Skill流水线重构(BaseSkill+7个Skill+Orchestrator+回修1次) |
| 06-30 | 测试 | test_orchestrator.py | 编排器测试4项全通过（含回修验证） |
| 06-30 | DB v1 | db/models.py + alembic 0001 | 初始6张表落地MySQL |
| 06-30 | DB v2 | db/models.py v2 + alembic 0002 | 三方审查后12张表（+clause_items/platform_runs/badcases/diagnoses/desensitization_logs），避保留字，加唯一约束 |
| 06-30 | 文档 | 技术设计文档第9章 | 12张表完整字段级说明 |
| 06-30 | 基础 | logging_config.py | 统一日志（log.info/log.error，不用debug/warn） |
| 06-30 | 基础 | db/recorder.py | 管线写库模块（已对齐v2字段名） |
| 06-30 | API | main.py | FastAPI /api/generate 接口 |
| 07-01 | Step1 | recorder.py v2 | 字段对齐models v2（run_status/bom_source/model_name/seq/before_json） |
| 07-01 | Step1 | nodes/ 清理 | 删5个旧函数式文件，逻辑移入 skills/_*_logic.py |
| 07-01 | Step1 | enums/ | 新增8个枚举统一事实源，contracts里的Literal全部替换 |

### 阻塞
- 暂无

### 待对方
- 杨力写 ingest.py + dedup.py + clean.py（A 模块数据预处理），交付 CleanedTestSet

---

## 🟩 杨力（feature_yangli）

### 当前任务
- （首次启动时）阅读 `docs/技术设计-生成场景后端专项.md` + `docs/progress.md` + `CLAUDE.md`
- 负责文件：`nodes/skills/_keyword_logic.py` 不属于你（那是 B 模块内部逻辑）
- **你负责的文件**（见下方协作矩阵）：
  - `nodes/skills/ingest_skill.py`（如用 Skill 模式）或 `services/ingest_service.py`
  - Excel 解析、去重、清洗 → 输出 CleanedTestSet
  - 也可以写 `db/recorder.py` 的优化（session 管理）

### 已完成
| 日期 | 模块 | 文件 | 说明 |
|------|------|------|------|
| （待补充） | | | |

### 阻塞
- 暂无

### 待对方
- 等 Step 2 分层重构完成（contracts→schemas 目录搬移）后再开工，避免路径冲突
