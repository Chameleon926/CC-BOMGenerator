# CC-BOMGenerator

> 语义 BOM 规则编译器与自动调优平台
> 独立于新旧主平台的 Python「规则实验室」
> PoC 已在新平台验证通过（准确率 52%→72%），当前进入正式开发阶段

---

## 这是什么

从合同标注测试集自动生成「语义 BOM」（业务定义 + 抽取规则 + 召回画像），基于 Badcase 做智能归因与优化，版本化管理，调优成效可视。

**谁用**：合同商务人员、业务实施人员

**解决什么问题**：
- 手工写/改抽取规则门槛高、耗时长
- Badcase 诊断靠人肉分析 Trace 逐条判断
- 改了规则不知是变好了还是变坏了（缺版本回归对比）

---

## PoC 验证结果

以「付款支持文档」条款在新平台验证：

| | 来源 | 准确率 | 投入 |
|---|---|---|---|
| 旧平台 | 业务手写 10 版迭代 | 65% | ≥16 小时 |
| 新平台 | 使用手工旧规则 | 52% | — |
| **本工具** | **PoC 自动生成 BOM** | **72%（+20pp）** | **一步生成** |

结论：LLM 生成的 BOM 优于业务手写，方法路径已验证，可复制推广。

> 当前阶段：方案评审已通过（领导采纳），进入正式开发。

---

## 架构

```
ingest(数据加载) → anonymize(脱敏) → generate(BOM生成) → diagnose(诊断) → optimize(优化) → evaluate(评估)
```

两阶段生成（与平台逻辑对齐）：

| 阶段 | 产出 | 说明 |
|---|---|---|
| Stage 1 | 语义定义 + 抽取规则（含拦截/匹配） | 从测试集归纳条款本质 |
| Stage 2 | 召回画像（正向关键词/易混淆词/章节/语义查询/正例） | 从定义派生 |
| Stage 3 | 规则自检 | 验证正例能抽、反例能拦，抓自相矛盾 |

optimize 场景做 5 类归因（召回/混合/BOM/Prompt模板/大模型推理），定向修复规则或画像。

---

## 技术栈

| 层 | 选型 |
|---|---|
| 语言 | Python 3.11+ / Vue 3 |
| 后端 | FastAPI + Pydantic v2 + SQLAlchemy + Alembic |
| 前端 | Vue 3 + Vite + axios |
| 数据库 | MySQL（utf8mb4）+ JSON 列 |
| 脱敏 | Presidio（本地 NER）+ 规则替换 |
| LLM | OpenAI 兼容（可配 base_url + api_key） |
| 测试 | pytest / vitest |

---

## 快速开始

### 方式一：本地开发

```bash
git clone git@github.com:Chameleon926/CC-BOMGenerator.git
cd CC-BOMGenerator

# 后端
cd backend
python -m venv .venv
pip install -r requirements.txt
cp ../config/llm.example.yaml ../config/llm.yaml   # 填 api_key/model/数据库连接
# 建 MySQL 库
mysql -u root -e "CREATE DATABASE cc_bom_generator CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
PYTHONPATH=. uvicorn src.main:app --reload --port 8000

# 前端（另一个终端）
cd frontend
npm install
npm run dev    # → http://localhost:5173
```

### 方式二：Docker 一键部署

```bash
git clone git@github.com:Chameleon926/CC-BOMGenerator.git
cd CC-BOMGenerator
docker-compose up -d
# → 前端 http://localhost  后端 API http://localhost:8000/docs
```

---

## 目录结构

```
CC-BOMGenerator/
├─ backend/                    # Python 后端（FastAPI）
│  ├─ src/cc_bom_generator/
│  │  ├─ contracts/            # Pydantic 契约
│  │  ├─ nodes/                # ingest/anonymize/generate/diagnose/evaluate
│  │  ├─ db/                   # SQLAlchemy + Alembic
│  │  └─ llm/                  # LLM 客户端
│  ├─ requirements.txt
│  └─ run.py                   # uvicorn 启动
├─ frontend/                   # Vue 前端
│  ├─ src/
│  │  ├─ views/                # 条款工作台/调优成效/设置
│  │  ├─ components/           # 复用组件
│  │  ├─ api/                  # 后端接口调用
│  │  └─ router/               # 路由
│  ├─ package.json
│  └─ vite.config.js           # 代理 /api → backend:8000
├─ config/
│  └─ llm.yaml                 # 模型配置（gitignore，各自填）
├─ prompts/                    # 提示词（纯文本 + {{var}}，与代码分离）
├─ quick_poc/                  # PoC 验证代码（已冻结）
├─ docs/
│  ├─ design/                  # 设计文档 HTML
│  └─ progress.md              # 开发进度
├─ CLAUDE.md
├─ .gitignore
└─ README.md
```

---

## 两人协作

本仓库由林大宇（feature_lindayu）和杨力（feature_yangli）各自用 Claude Code 协同开发。

三条铁律：

1. **开工前必须读 design 文档**（`docs/design/`），即使读过
2. **进度跟踪**：每次改完更新 `docs/progress.md`，提交标注模块编号
3. **改契约 = 停止 + 通知**：改 contracts/ 前必须先通知对方

详见 `CLAUDE.md` 与 `docs/功能模块拆分-按文件粒度.md`。

---

## License

MIT