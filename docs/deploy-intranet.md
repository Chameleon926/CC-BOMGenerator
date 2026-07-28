# 内网部署教程（极简版）

> 场景：内网权限管控，外网 push 不进去。代码靠**打包手动传**。验证「上传测试集 → 生成 BOM」。

---

## 第一步：内网机拉代码（三选一）

**方式 A（推荐）：git clone** —— 内网能访问 GitHub 时
```bash
git clone -b feature_lindayu https://github.com/Chameleon926/CC-BOMGenerator.git
cd CC-BOMGenerator
```

**方式 B：GitHub 下载 ZIP** —— 内网能访问 GitHub 但没装 git
GitHub 仓库 → Code → Download ZIP（**选 `feature_lindayu` 分支**，main 是旧的）→ 传内网解压。

**方式 C（fallback）：外网打包手动传** —— 内网连不上 GitHub
外网机项目根目录跑：
```bash
tar --exclude='node_modules' --exclude='__pycache__' --exclude='.venv' \
    --exclude='backend/data' --exclude='config/llm.yaml' --exclude='.git' \
    -czf bom-code.tar.gz .
```
把 `bom-code.tar.gz` 传内网解压。

> ⚠️ **必须用 `feature_lindayu` 分支**——最新代码（含典型正例、架构夯实）都在这个分支，`main` 是旧的。

---

## 第二步（可选）：离线 Python 包

内网若**无 PyPI 镜像**，外网机先下载好 wheels：

```bash
mkdir -p wheels && pip download -r backend/requirements.txt -d wheels/
tar -czf bom-wheels.tar.gz wheels/
```

`bom-wheels.tar.gz` 一并传内网。

---

## 第三步（可选）：离线前端包

内网若**无 npm 镜像**，外网机装好依赖后直接打包 `node_modules`，或 build 后只传产物：

```bash
cd frontend && npm install
# 方式 A：传 node_modules（内网能 npm run dev）
tar -czf bom-frontend-deps.tar.gz node_modules
# 方式 B：build 后只传 dist（内网 nginx 托管，不用 node）
npm run build   # 产出 frontend/dist/
```

---

## 第四步：内网机解压 + 装后端依赖

```bash
mkdir bom && cd bom
tar -xzf bom-code.tar.gz

cd backend
# 有内网 PyPI 镜像：
pip install -r requirements.txt
# 无镜像（用了第二步的离线包）：
tar -xzf ../bom-wheels.tar.gz -C . && pip install --no-index --find-links=wheels/ -r requirements.txt
```

---

## 第五步：配置 `config/llm.yaml`（关键）

```bash
cd ../  # 回项目根
cp config/llm.example.yaml config/llm.yaml
```

编辑 `config/llm.yaml`，填成（**LLM + DB 都在这一个文件**）：

```yaml
# === LLM（必改：指向内网可达的大模型）===
api_key: "你的key"
base_url: "https://内网大模型端点"   # ← 改成内网的
model: "模型名"                       # ← 内网模型名
api_format: "anthropic"              # 或 openai，看端点
temperature_stage1: 0.2
temperature_stage2: 0.5
temperature_stage3: 0.0

# === 数据库（必改：内网 MySQL）===
mysql_host: "127.0.0.1"
mysql_port: 3306
mysql_user: "root"
mysql_password: "你的密码"
mysql_database: "cc_bom_generator"
```

> ⚠️ **base_url 是唯一的外网依赖**——生成调 4 次大模型。必须填**内网能访问**的大模型端点。

---

## 第六步：起 MySQL + 建库 + 跑迁移

内网起 MySQL（5.7+ / utf8mb4），建库：

```sql
CREATE DATABASE cc_bom_generator CHARACTER SET utf8mb4;
```

建表（在项目根）：

```bash
cd backend && PYTHONPATH=. python -m alembic upgrade head
```

---

## 第七步：起后端

```bash
cd backend && PYTHONPATH=. uvicorn src.main:app --host 0.0.0.0 --port 8000
```

验证：`curl http://127.0.0.1:8000/api/health` → `{"status":"ok"}` 即通。

---

## 第八步：起前端（可选，curl 也能验证）

```bash
cd frontend
# 有内网 npm 镜像：
npm install && npm run dev
# 无镜像（用了第三步的离线包）：
tar -xzf ../bom-frontend-deps.tar.gz   # 解出 node_modules
npm run dev
```

浏览器开 `http://内网机IP:5173`。

---

## 第九步：验证生成场景

1. 条款库 → 「导入测试集」→ 传你的 Excel（列含 `doc_id / block_code / expected_value`）
2. 点「生成」→ 等约 2 分钟（7-8 个节点）
3. 详情页看：BOM（定义/拦截/匹配/毒药词/画像/典型正例+理由）+ 完整提示词（可复制）

**跑通 = 生成场景验证成功。**

---

## 常见坑

| 现象 | 原因 | 解决 |
|---|---|---|
| Skill3「定义+规则生成」失败 | LLM 端点不通/key 错 | 检查 `config/llm.yaml` 的 base_url/api_key，curl 测连通 |
| 起后端报 DB 连不上 | MySQL 没起/密码错/库没建 | 确认 MySQL 起、库建了、config 密码对 |
| 前端 5173 打不开 | vite 没起 / 代理 | 确认 `npm run dev` 在跑；后端要在 :8000 |
| alembic 报版本冲突 | 迁移没跑全 | `PYTHONPATH=. python -m alembic upgrade head` 跑到 head |
