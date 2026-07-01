# CC-BOMGenerator

> 语义 BOM 规则编译器与自动调优平台 —— 独立于新旧主平台的 Python「规则实验室」。
> PoC 已在新平台验证通过（52%→72%）。当前进入正式开发阶段。

---

## 👥 协作约定（两人 Claude Code 并行开发）

本仓库由两位开发者各自用 Claude Code 协同开发。请严格遵守：

1. **单一事实源 = 本仓库**
   Claude 会话记忆是易失的；仓库才是持久的。所有重要决策（架构、契约、约定）必须落到仓库文件：本 `CLAUDE.md`、`docs/design/` 设计文档、`docs/` 开发指南、`src/.../contracts/`。**不要把关键信息只留在会话里。**

2. **契约先行（Contract-First）—— 这是并行开发的核心范式**
   - 动手实现任何节点前，**先在 `src/cc_bom_generator/contracts/` 定义并提交该节点的输入/输出 Pydantic schema**。
   - 契约是协作边界：A 实现 `generate`、B 实现 `diagnose`，彼此只看对方的契约，不读对方实现内部。
   - **改契约 = 开 PR 让对方 review**。契约变更属于「高影响变更」，必须显式同步，不能默默改。
   - 当前 6 个契约文件已定义：`bom.py`、`test_set.py`、`diagnosis.py`、`trace.py`、`evaluation.py`、`__init__.py`。开工前 `git pull` 拿到最新版。

3. **分支 + PR 工作流**
   - `main` = 集成分支（已评审通过的稳定内容），**不直接推**。
   - 个人分支：`feature_lindayu`、`feature_yangli` —— 各自在自己分支开发。
   - **开工前必做：`git pull origin main`**。
   - 流程：个人分支 → 开 PR → 对方 review → 合入 `main`。
   - 合并前用 `/code-review` 自审，复杂改动用 `superpowers:requesting-code-review` 互审。
   - 小步提交，逻辑单元完成即 commit + push。
   - **CC 行为拦截器**：每次被要求写代码或修改文件前，Claude Code 必须在底层隐式执行 `git branch`。如果检测到当前处于 `main` 分支，CC 必须**拒绝执行任何写操作**，并强制中断流程，提醒开发者切换到 `feature_lindayu` 等个人分支。绝对禁止在 `main` 分支产生任何 commit。

4. **开工先 `git pull`，按模块分工**
   - **每次开始工作前，第一步必须是 `git pull origin main`**，拉取对方最新改动。
   - 避免两人同时改同一文件；按 `docs/技术设计-生成场景后端专项.md` 的文件映射表划分 ownership。
   - 拉取后若有冲突，优先保护契约文件与设计文档的权威性。
   - 开发进度同步：**每次开工先看 `docs/progress.md`**。
   - **标准开工触发器**：当开发者在终端输入带有"开工"、"开始开发"、"今天继续"等意图的指令时，Claude Code 必须自动按顺序串行执行以下 3 步，无需等待确认：
     ① 执行 `git pull origin main` 拉取最新代码；
     ② 读取并总结 `docs/progress.md`，报告对方的最新进度；
     ③ 读取 `docs/技术设计-生成场景后端专项.md` 和 `contracts/`，对比是否有影响当前模块的变更。全部完成后，向开发者输出简报再开始写代码。

5. **脱敏与数据合规**
   - 真实合同数据、含敏感信息的评测集**不入库**（见 `.gitignore` 的 `data/raw` 等）。
   - 共享样例放 `data/samples/`，且必须已脱敏。
   - **外网路径**自动执行脱敏后方可出网；**内网路径**不脱敏。

6. **开发文档位置（当前有效）**
   - `docs/技术设计-生成场景后端专项.md` —— **当前主力技术文档**：A/B 模块分工 + 算法建议 + 文件映射表 + 新平台工作流
   - `docs/progress.md` —— 两人各自维护的开发进度
   - `docs/archive/` —— 历史归档，不直接用，需要时参考
   - 两位 Claude 开工前必须读前两个文件。

7. **开工前必须读技术文档（即使以前读过）**
   每次启动 Claude、每次开始新任务前，必须先读：
   - `docs/技术设计-生成场景后端专项.md` —— 当前主力技术文档
   - `docs/progress.md` —— 进度跟踪
   - `backend/src/cc_bom_generator/contracts/` —— 契约定义（即使没变也要确认）
   这一步不可跳过。**不读就直接改代码属于违规操作，会被 review 时打回**。

8. **进度跟踪纪律**
   - 每次修改代码后，**必须更新 `docs/progress.md`**：改了哪些文件、完成了什么功能、卡在什么地方、下一项是什么。
   - 提交时必须显式标注改动的模块编号（M1-M9）和文件路径。
   - 林大宇和杨力各自维护自己的进度段落，**不覆盖对方的内容**。
   - 每次开工前先读 `docs/progress.md`，确认对方当前进度后再开始写代码。

9. **改契约 = 停止 + 通知**
   - 任何涉及 `src/cc_bom_generator/contracts/` 的改动，必须先停止代码工作，通知对方（发消息或开 PR），等对方确认后再继续。
   - 这条没有例外。**契约是协作边界，改契约不通知等于拆桥**。
   - **Auto 模式熔断器**：即使 Claude Code 当前运行在 auto/acceptEdits 模式，一旦判定需要修改 `src/.../contracts/` 或 `backend/src/cc_bom_generator/contracts/` 目录下的契约文件，CC 必须**强行挂起（Suspend）当前自动流程**。向终端抛出高亮警告说明原因，并强制等待开发者输入明确授权（如"同意修改"）后才能继续。严禁静默修改契约。

---

## 🏗️ 架构：节点（skill）流水线，每个节点有 I/O 契约

```
ingest(数据加载) → anonymize(脱敏) → generate(BOM生成) → diagnose(诊断) → optimize(优化) → apply(应用) → evaluate(评估)
```

| 节点 | 输入 | 输出 |
|---|---|---|
| ingest | Excel / Chunk | TestSet（文档→语义块→语义项+上下文） |
| anonymize | 原始文本 | 脱敏文本 + MappingTable |
| generate | TestSet + 语义名称 | BOM（定义/规则/画像/正反例） |
| diagnose | trace + badcase + 当前BOM | Diagnosis（category 5 类 + root_cause） |
| optimize | Diagnosis + 当前BOM + few-shot | BOMDelta |
| apply | BOMDelta + 当前BOM | 新版本 BOM |
| evaluate | 跑分结果 + BOM 版本 | Metrics + Diff |

**错误分类体系（5 类，对齐新平台）**：召回问题 / 混合问题 / BOM 问题 / Prompt 模板待优化 / 大模型推理问题。

---

## 📁 目录结构

```
CC-BOMGenerator/
├─ backend/                    # Python 后端（FastAPI）
│  ├─ src/cc_bom_generator/
│  │  ├─ enums/                # ✅ 枚举唯一事实源（BomSource/BOMStatus/DiagnosisCategory 等 8 个）
│  │  ├─ contracts/            # Pydantic 契约（8 个文件，引用 enums 不内联枚举）
│  │  ├─ nodes/                # 编排层
│  │  │  ├─ base.py            # BaseSkill 基类
│  │  │  ├─ orchestrator.py     # 管线编排器（含回修+写库）
│  │  │  ├─ pipeline.py        # 入口（调 orchestrator）
│  │  │  └─ skills/            # 唯一实现：7 个 Skill + 5 个内部 logic（_*_logic.py）
│  │  ├─ db/                   # SQLAlchemy ORM（12 张表）+ recorder + Alembic
│  │  ├─ llm/                  # LLM 客户端（双格式 OpenAI/Anthropic）
│  │  ├─ logging_config.py     # 统一日志（log.info/log.error）
│  │  └─ main.py               # FastAPI 入口（待拆为 api/routers/）
│  ├─ requirements.txt
│  ├─ alembic/                 # 迁移脚本（0001 初始 + 0002 v2 schema）
│  └─ tests/                  # 单元测试
├─ frontend/                   # Vue 前端
├─ config/
│  └─ llm.yaml                 # 模型配置（gitignore，各自填）
├─ prompts/                    # 提示词（纯文本 + {{var}}，与代码分离）
├─ quick_poc/                  # PoC 验证代码（已冻结）
├─ docs/
│  ├─ 技术设计-生成场景后端专项.md  # 主力技术文档（含第9章数据库设计）
│  └─ progress.md              # 开发进度跟踪
├─ CLAUDE.md
├─ .gitignore
└─ README.md
```

### 文件协作矩阵（谁写什么，不要碰对方的文件）

```
文件/目录                              林大宇    杨力    说明
enums/                                林大宇    ❌      枚举唯一事实源，改=PR+通知
contracts/                            林大宇    ❌      Pydantic 契约，改=PR+通知
nodes/orchestrator.py                 林大宇    ❌      编排器
nodes/pipeline.py                     林大宇    ❌      管线入口
nodes/base.py                         林大宇    ❌      BaseSkill 基类
nodes/skills/                         林大宇    ❌      B模块 Skill + 内部 logic
db/models.py                          林大宇    ❌      ORM 表定义
db/recorder.py                        林大宇    可优化   写库逻辑（杨力可提PR优化session管理）
db/__init__.py                        林大宇    ❌      Engine + Session
llm/client.py                         林大宇    可优化   LLM 客户端（杨力可提PR加超时/重试）
logging_config.py                      林大宇    ❌      日志配置
main.py                               林大宇    ❌      API 入口（Step 2 后拆为 api/routers/）
services/ingest_service.py             ❌        杨力    A模块：Excel解析→CleanedTestSet（Step 2后创建）
alembic/                              林大宇    ❌      迁移脚本
prompts/*.txt                          两人都改  互相通知
config/llm.yaml                       各自填    各自填  不入库、互不影响
tests/test_*.py                        各自写    各自写  谁的模块谁写测试
```

> **规矩：不要碰对方目录的文件。需要改对方的文件=开 PR + 通知。**
│  └─ alembic/
├─ frontend/                   # Vue 前端
│  ├─ src/
│  │  ├─ views/                # 条款工作台/调优成效/设置
│  │  ├─ components/           # 复用组件
│  │  ├─ api/                  # 后端接口调用
│  │  └─ router/               # 路由
│  ├─ package.json
│  └─ vite.config.ts           # 代理 /api → backend:8000
├─ config/
│  └─ llm.yaml                 # 模型配置（gitignore，各自填）
├─ prompts/                    # 提示词（纯文本 + {{var}}，与代码分离）
├─ quick_poc/                  # PoC 验证代码（已冻结）
├─ docs/
│  ├─ design/                  # 设计文档 HTML
│  ├─ progress.md              # 开发进度
│  └─ 功能模块拆分-按文件粒度.md
├─ CLAUDE.md
├─ .gitignore
├─ README.md
└─ requirements.txt            # 公共依赖（可选）
```

---

## 🧰 技术栈

- **语言**：Python 3.11+
- **后端**：FastAPI
- **前端**：Vue 3 + Vite（**不用 Streamlit**，已废弃）
- **脱敏**：Presidio（本地 NER）+ 规则替换
- **LLM 客户端**：OpenAI 兼容（可配 api_key + base_url + 模型）
- **数据库**：MySQL（utf8mb4）+ JSON 列；**SQLAlchemy ORM + Alembic 迁移**
- **DB 驱动**：PyMySQL
- **契约**：Pydantic v2
- **测试**：pytest / vitest
- **IDE**：PyCharm / VSCode（`.idea/` 已 gitignore）

---

## 📝 代码约定

- 契约一律用 **Pydantic v2**；节点输入输出必须是已定义的契约类型。
- **提示词与代码分离**：prompt 放 `prompts/`（纯文本 + `{{var}}` 占位），代码只加载渲染，不在代码里硬编码 prompt。
- 标识符用英文；注释与业务文档用中文、贴近合同业务语言。
- 每个节点必须可独立单元测试（给定输入契约，断言输出契约）。
- 不引入未经设计文档确认的重型依赖（向量库等 Phase 2 再评估）。
- `config/llm.yaml` 已 gitignore，内含 api-key / model / 数据库密码，绝不入库。
- **开工前先 `git pull origin main`**，拿到最新契约和开发文档再开始。

---

## ✅ 当前进度

- [x] PoC 验证通过（52%→72%）
- [x] 方案评审通过（领导采纳）
- [x] 设计文档全套（业务/技术/Agent/功能拆解/原型）
- [x] 开发文档（协作指南 + 模块拆分）
- [x] contracts 定义（6 个 Pydantic 文件）
- [ ] nodes/ 节点实现（ingest → generate → diagnose → evaluate）
- [ ] db/models + Alembic 迁移
- [ ] llm/client 客户端
- [ ] Vue3 前端（工作台/调优成效/设置）
- [ ] 集成联调 + 回归测试

---

## ▶️ 运行

```bash
# 后端（FastAPI）
cd backend
PYTHONPATH=. uvicorn src.main:app --reload --port 8000

# 前端（Vue3，后端接口验证通过后再开发）
cd frontend
npm run dev

# PoC 验证（已冻结）
python quick_poc/rule_pipeline.py quick_poc/data/sample_slice.yaml --mode optimize --print-prompt
```

---

## 📚 关键文档索引

| 文档 | 路径 | 说明 |
|---|---|---|
| **生成场景后端专项** | `docs/技术设计-生成场景后端专项.md` | **当前主力文档**：A/B 模块分工 + 算法建议 + 文件映射表 |
| 协作指南 | `docs/开发文档-协作指南.md` | 分支、IDE、DB、代码约定 |
| 模块拆分 | `docs/功能模块拆分-按文件粒度.md` | M1-M9，每模块拆到文件/类/输入/输出 |
| 领导汇报 | `docs/design/leadership-brief.html` | 8 页 HTML PPT |
| 交互原型 | `docs/design/prototype-redesign.html` | Vue3 前端设计参考 |
| 技术设计 | `docs/design/technical-design.html` | 架构/数据模型/分期 |
| 进度跟踪 | `docs/progress.md` | 两人各自维护的开发进度 |

---

## 🚢 部署方案

支持两种模式：

### 本地开发（日常开发用）

```bash
# 后端
cd backend
python -m venv .venv
pip install -r requirements.txt
cp ../config/llm.example.yaml ../config/llm.yaml   # 填 api_key/model/数据库
PYTHONPATH=. uvicorn src.main:app --reload --port 8000

# 前端（后端接口验证通过后再开发）
cd frontend
npm install
npm run dev    # → http://localhost:5173，自动代理 /api → backend:8000
```

**本地 MySQL**：localhost:3306，密码各自配置，直接用 Navicat 连。

### Docker 一键部署（验证/演示/上线用）

```bash
docker-compose up -d
# → MySQL(3306) + 后端(8000) + 前端(80) 全部起来
# → 前端访问 http://localhost
# → 后端 API http://localhost:8000/docs (FastAPI 自动文档)
```

**文件清单**：

| 文件 | 说明 |
|---|---|
| `docker-compose.yml` | 三服务编排（MySQL + backend + frontend） |
| `backend/Dockerfile` | python:3.11-slim + uvicorn |
| `frontend/Dockerfile` | 多阶段构建（node:20 → nginx:alpine） |
| `frontend/nginx.conf` | 静态托管 + `/api/` 反代到 backend:8000 |
| `.dockerignore` | 排除 .git/docs/quick_poc/node_modules |