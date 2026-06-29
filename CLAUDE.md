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

4. **开工先 `git pull`，按模块分工**
   - 避免两人同时改同一文件；按 `docs/功能模块拆分-按文件粒度.md` 划分 ownership。
   - 拉取后若有冲突，优先保护契约文件与设计文档的权威性。
   - 开发进度同步：**每次开工先看 `docs/` 里的进度清单**。

5. **脱敏与数据合规**
   - 真实合同数据、含敏感信息的评测集**不入库**（见 `.gitignore` 的 `data/raw` 等）。
   - 共享样例放 `data/samples/`，且必须已脱敏。
   - **外网路径**自动执行脱敏后方可出网；**内网路径**不脱敏。

6. **开发文档位置**
   - `docs/开发文档-协作指南.md` —— 分支策略、IDE、数据库、代码约定
   - `docs/功能模块拆分-按文件粒度.md` —— 每个模块拆到文件/类/函数/输入/输出/谁写
   - 两位 Claude 开工前必须读这两个文件。

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
├─ CLAUDE.md
├─ .gitignore / .env.example / requirements.txt
├─ config/
│  └─ llm.yaml              # 模型配置（gitignore，各自填）
├─ prompts/                 # 提示词（纯文本 + {{var}}，与代码分离）
├─ quick_poc/               # PoC 验证代码（已冻结）
├─ src/cc_bom_generator/    # 正式产品代码
│  ├─ contracts/            # Pydantic 契约（已定义 6 个文件）
│  ├─ nodes/                # 各节点实现（待开发）
│  ├─ db/                   # SQLAlchemy + Alembic（待开发）
│  ├─ llm/                  # LLM 客户端（待开发）
│  └─ ui/                   # Streamlit 前端（待开发）
├─ docs/
│  ├─ design/               # 设计文档 HTML（业务/技术/Agent/原型）
│  ├─ 开发文档-协作指南.md
│  └─ 功能模块拆分-按文件粒度.md
├─ tests/                   # 单元测试
└─ data/samples/            # 脱敏样例
```

---

## 🧰 技术栈

- **语言**：Python 3.11+
- **前端**：Streamlit（纯 Python 写界面）
- **脱敏**：Presidio（本地 NER）+ 规则替换
- **LLM 客户端**：OpenAI 兼容（可配 api_key + base_url + 模型）
- **数据库**：MySQL（utf8mb4）+ JSON 列；**SQLAlchemy ORM + Alembic 迁移**
- **DB 驱动**：PyMySQL
- **契约**：Pydantic v2
- **测试**：pytest
- **IDE**：PyCharm（`.idea/` 已 gitignore）

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
- [ ] Streamlit UI（工作台/调优成效/设置）
- [ ] 集成联调 + 回归测试

---

## ▶️ 运行

```bash
# 开发阶段
PYTHONPATH=. streamlit run src/cc_bom_generator/ui/app.py

# PoC 验证（已冻结）
python quick_poc/rule_pipeline.py quick_poc/data/sample_slice.yaml --mode optimize --print-prompt
```

---

## 📚 关键文档索引

| 文档 | 路径 | 说明 |
|---|---|---|
| 协作指南 | `docs/开发文档-协作指南.md` | 分支、IDE、DB、代码约定 |
| 模块拆分 | `docs/功能模块拆分-按文件粒度.md` | M1-M9，每模块拆到文件/类/输入/输出 |
| 领导汇报 | `docs/design/leadership-brief.html` | 8 页 HTML PPT |
| 交互原型 | `docs/design/prototype-redesign.html` | Streamlit 界面设计参考 |
| 技术设计 | `docs/design/technical-design.html` | 架构/数据模型/分期 |