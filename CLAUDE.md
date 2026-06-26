# CC-BOMGenerator

> 语义 BOM 规则编译器与自动调优平台 —— 独立于新旧主平台的 Python「规则实验室」。
> 从标注评测集生成语义 BOM（定义/规则/召回画像/正反例），对 Badcase 智能归因并优化，版本化回归评估。

---

## 👥 协作约定（两人 Claude Code 并行开发）

本仓库由两位开发者各自用 Claude Code 协同开发。请严格遵守：

1. **单一事实源 = 本仓库**
   Claude 会话记忆是易失的；仓库才是持久的。所有重要决策（架构、契约、约定）必须落到仓库文件：本 `CLAUDE.md`、`docs/design/` 设计文档、`src/.../contracts/`。**不要把关键信息只留在会话里。**

2. **契约先行（Contract-First）—— 这是并行开发的核心范式**
   - 动手实现任何节点前，**先在 `src/cc_bom_generator/contracts/` 定义并提交该节点的输入/输出 Pydantic schema**。
   - 契约是协作边界：A 实现 `generate`、B 实现 `diagnose`，彼此只看对方的契约，不读对方实现内部。
   - **改契约 = 开 PR 让对方 review**。契约变更属于「高影响变更」，必须显式同步，不能默默改。

3. **分支 + PR 工作流**
   - `main` = 集成分支（已评审通过的稳定内容），**不直接推**。
   - 个人分支：`feature_lindayu`、`feature_yangli` —— 各自在自己分支开发。
   - 流程：个人分支 → 开 PR → 对方 review → 合入 `main`。
   - 复杂功能可在个人分支下再开短命分支（`feat/<node>-<topic>`），完成后合回个人分支。
   - 合并前用 `/code-review` 自审，复杂改动用 `superpowers:requesting-code-review` 互审。
   - 小步提交，逻辑单元完成即 commit + push。

4. **开工先 `git pull`，按节点分工**
   - 避免两人同时改同一文件；按 7 个节点 + 模块划分 ownership。
   - 拉取后若有冲突，优先保护契约文件与设计文档的权威性。

5. **脱敏与数据合规**
   - 真实合同数据、含敏感信息的评测集**不入库**（见 `.gitignore` 的 `data/raw` 等）。
   - 共享样例放 `data/samples/`，且必须已脱敏。

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
详见 `docs/design/business-design.html` 与（待产出）`technical-design.html`。

---

## 📁 目录结构

```
CC-BOMGenerator/
├─ CLAUDE.md                      # 本文件，协作契约
├─ README.md                      # 项目说明（待补）
├─ .gitignore
├─ docs/
│  ├─ design/                     # HTML 设计文档（业务/技术，给业务与评审看）
│  │  ├─ business-design.html
│  │  └─ technical-design.html    # 待产出
│  └─ superpowers/specs/          # markdown 设计规范（开发参考）
├─ src/cc_bom_generator/
│  ├─ contracts/                  # 【最先建】Pydantic 契约，协作边界
│  ├─ nodes/                      # 各节点实现（按契约）
│  └─ ...
└─ data/
   └─ samples/                    # 脱敏后的共享样例
```

---

## 🧰 技术栈

- **语言**：Python 3.11+
- **前端**：Streamlit
- **脱敏**：Presidio（本地 NER，假名化）
- **外部 LLM**：google-generativeai（Gemini），API 直连为主 + 手动兜底
- **本地 BOM 库**：SQLite + JSON（版本化）
- **契约**：Pydantic v2
- **测试**：pytest
- **IDE**：PyCharm（`.idea/` 已 gitignore）

---

## 📝 代码约定

- 契约一律用 **Pydantic v2**；节点输入输出必须是已定义的契约类型。
- 标识符用英文；注释与业务文档用中文、贴近合同业务语言。
- 每个节点必须可独立单元测试（给定输入契约，断言输出契约）。
- commit message 简明（中文/英文均可）。
- 不引入未经设计文档确认的重型依赖（向量库等 Phase 2 再评估）。

---

## ✅ 当前进度

- [x] 业务设计文档 v0.1（`docs/design/business-design.html`）
- [ ] 技术设计文档（`docs/design/technical-design.html`）
- [ ] markdown 设计规范（`docs/superpowers/specs/`）
- [ ] 演示 Deck（frontend-slides）
- [ ] contracts 定义（实现第一步）
- [ ] 各节点实现

## ▶️ 运行

（待实现后补充：`streamlit run src/cc_bom_generator/app.py` 等）
