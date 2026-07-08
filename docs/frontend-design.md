# CC-BOMGenerator 前端设计文档（单一事实源）

> **状态：Living Document。** 任何前端的新增 / 修改 / 优化，必须同步更新本文档对应章节，并在 §12 变更日志追加一行（见 §11 变更协议）。
> **最近更新：** 2026-07-08 ｜ **维护人：** 林大宇（feature_lindayu）
> **设计依据：** [ui-ux-pro-max](https://github.com) 99 条 UX 准则 + Data-Dense Dashboard 风格基线

---

## 0. 文档定位与阅读指南

本文档是 **前端开发的唯一事实源（Single Source of Truth）**。它同时承担三件事：

1. **设计契约** —— 每个页面的布局、组件、数据源、交互、状态都固定写死在此，开发照此实现。
2. **进度镜像** —— §10 记录「已建 / 在建 / 待建」，与 `docs/progress.md` 互为印证。
3. **协作边界** —— 前端只看本文档 + 后端契约（§6），不读后端实现内部。

**与其他文档的关系：**

| 文档 | 角色 | 本文如何引用 |
|---|---|---|
| `docs/技术设计-生成场景后端专项.md` | 后端契约 + 算法源 | §6 API 契约的权威来源 |
| `docs/progress.md` | 两人开发进度 | §10 进度的镜像 |
| `CLAUDE.md` | 协作铁律 + 目录树 | 前端目录约定（§4） |
| `docs/design/prototype-redesign.html` | 原始交互原型（归档参考） | 视觉参考，以本文为准 |

> ⚠️ 当本文档与代码冲突时：**未 commit 的代码不算数**，以本文档为准；commit 后以代码为准并回写本文档。

---

## 1. 产品定位与用户

| 维度 | 说明 |
|---|---|
| 产品 | 语义 BOM 规则编译器工作台（内部工具，非对外 SaaS） |
| 用户 | 规则工程师 / 业务分析师（单人或小团队，桌面办公场景） |
| 核心任务链 | 导入测试集 → 选条款生成 BOM → 复制提示词 → 粘新平台跑分 |
| 技术栈 | Vue 3 + Element Plus + Tailwind CSS + Vite + axios + vue-router |
| 部署 | 本地开发（vite :5173 代理 /api → backend :8000）；Docker 一键（nginx 反代） |

**关键约束（影响设计决策）：**

- LLM 调用慢（单次生成 5–60s）→ 异步 + 进度反馈是核心体验，不是可选。
- 数据量小（条款通常 < 50 个）→ 不需要虚拟列表 / 复杂分页，但需要好的空状态与错误恢复。
- 内部工具 → 不需要登录态 / 多租户 / 移动端优先；**桌面 ≥ 1280px 为主目标**，1024 可用即可。

---

## 2. 信息架构（目标态：3 层）

```
条款库（第一级 / Library）            ← 入口，列出所有条款
   │
   ├─ [导入测试集]  POST /testset/scan   → 扫描 + upsert clauses
   ├─ [新增条款]    POST /clauses        → 手动建
   ├─ [删除条款]    DELETE /clauses/{id} → popconfirm 确认
   │
   └─ 点条款「生成」POST /generate → 创建 run → 跳「生成任务列表」↓

生成任务列表（第二级 / Runs）          ← 某条款的所有生成任务
   │  字段：条款名 | 进度% | 状态 | 测试集 | 操作[详情][停止]
   │
   └─ 点「详情」→ 「任务详情」↓

任务详情（第三级 / Detail）            ← 单个 run 的全过程 + 结果
   ├─ 头部：条款名 | run_id | 创建时间 | 状态 | 耗时
   ├─ 执行进度（7 节点中文化 + ✓/✗/○ + 耗时）
   ├─ 选取数据列表（聚类选的代表正例：doc_id + 期望值片段）
   └─ BOM 结果（定义/拦截/毒药词/匹配/思维链/画像/提示词，折叠）
```

**路由表（vue-router，待实现）：**

| 路径 | 页面 | 组件 | 说明 |
|---|---|---|---|
| `/library` | 条款库 | `views/LibraryView.vue` | 默认首页 |
| `/runs` | 生成任务列表 | `views/RunsView.vue` | `?block_code=X` 可筛选 |
| `/runs/:id` | 任务详情 | `views/RunDetailView.vue` | 深链可分享 |
| `/config` | 模型配置 | `views/ConfigView.vue` | sidebar 第 3 项 |

> **现状 gap：** `vue-router` 已装（package.json）但 **未接线**（无 `router/`、无 `views/`、main.js 未 use(router)）。当前 `App.vue` 用 `activeMenu` ref 假切页，无 URL、无深链、无后退。→ §10 P0。

---

## 3. 设计系统（Design Tokens）

### 3.1 风格定位

**Data-Dense Dashboard**（BI / 企业报表 / ops 工作台）—— 信息密度高、留白克制、状态优先、WCAG AA。

- 蓝白企业级底色 + 状态色（绿成功 / 橙进行中 / 红失败危险 / 灰排队禁用）
- 反模式（Avoid）：装饰过度（ornate）、无筛选（no filtering）
- 单屏一个主 CTA（`primary-action`，P4）

### 3.2 色板（对齐 Element Plus 主题，不另起炉灶）

| 角色 | Token | 值 | 用途 |
|---|---|---|---|
| 主色 | `--el-color-primary` | `#409EFF` | 主 CTA / 选中态 / 链接 |
| 主色深 | `primary-deep` | `#1E40AF` | 数据强调 / 标题强调（可选） |
| 成功 | `--el-color-success` | `#67C23A` | success 状态 / ✓ |
| 警告 | `--el-color-warning` | `#E6A23C` | running 状态 / 进行中 |
| 危险 | `--el-color-danger` | `#F56C6C` | fail/cancelled / 删除 / ✗ |
| 信息 | `--el-color-info` | `#909399` | queued / 待生成 / 辅助 |
| 背景 | `bg` | `#F8FAFC`（slate-50） | 页面底色 |
| 表面 | `surface` | `#FFFFFF` | 卡片 / 表格 |
| 边框 | `border` | `#E2E8F0`（slate-200） | 分割线 |
| 正文 | `text` | `#1E293B`（slate-800） | 主要文字（≥4.5:1） |
| 次要 | `text-muted` | `#64748B`（slate-500） | 辅助文字（≥4.5:1） |

> **任务状态 → 颜色映射（全局统一，不可散落）：**
>
> ⚠️ **API 字段名是 `status`**（`GET /runs` 与 `GET /runs/{id}/status` 都返 `status`）。`run_status` 是**数据库列名**，前端代码一律用 `run.status`，别用 run_status。下表"取值"列即 `run.status` 的可能值。

| 状态 | `run.status` 取值 | el-tag type | 含义 |
|---|---|---|---|
| 排队中 | `queued` | `info` | 未开始 |
| 执行中 | `running` | `warning` | 后台线程跑节点 |
| 成功 | `success` | `success` | finish 正常 |
| 失败 | `fail` | `danger` | 异常 |
| 已取消 | `cancelled` | `danger`（effect=plain） | 用户停止 |

### 3.3 字体

| 用途 | 字体栈 | 说明 |
|---|---|---|
| 正文 / UI | `"PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif` | CJK 友好，**不外加载英文字体**（内部工具，首屏优先） |
| 数据 / 提示词 / 代码 | `ui-monospace, "Fira Code", Consolas, monospace` | 仅用于 prompt 代码块、耗时数字、doc_id |

> skill 建议 Fira Sans/Fira Code 全量；本项目为中文内部工具，**正文走系统 CJK 字体**，等宽仅用于代码/数据块（已有 `font-mono` 习惯）。`number-tabular`（P6）：耗时 / 版本号列用 `tabular-nums` 防抖动。

### 3.4 间距 / 圆角 / 阴影

| Token | 值 | 用途 |
|---|---|---|
| 间距节奏 | 8dp（Tailwind 默认即 4/8 体系） | `gap-2/3/4` → 8/12/16px |
| 卡片圆角 | `rounded-lg`（8px） | el-card / 面板 |
| 控件圆角 | `rounded-md`（6px） | 按钮 / 输入 |
| 阴影 | el-card `shadow="never"`（常态）+ `hover`（悬停） | 数据型工作台克制用阴影 |
| z-index | `0 / 10 / 20 / 40 / 100 / 1000` | dropdown / sticky / modal / toast 层级（`z-index-management`，P5） |

### 3.5 组件规范（基于 Element Plus）

| 场景 | 组件 | 规范 |
|---|---|---|
| 主操作 | `el-button type="primary"` | **每屏仅一个主 CTA**（`primary-action`，P4）；次操作用 default/plain |
| 危险操作 | `el-button type="danger"` + `el-popconfirm` | 删除前必确认（`confirmation-dialogs`，P8） |
| 列表 | `el-table` + 状态列用 `el-tag` | 行高亮 `highlight-current-row`；空状态用 `el-empty`（`empty-states`，P8） |
| 表单 | `el-form` + 可见 label | label 不藏在 placeholder（`input-labels`，P8）；错误就近（`error-placement`） |
| 反馈 | `ElMessage`（成功 3s 自动消失） | 成功操作必反馈（`success-feedback`/`submit-feedback`，P8） |
| 进度 | `el-progress :percentage` + 节点列表 | 任务列表用进度条，详情用节点清单 |
| 上传 | `el-upload drag` | 选文件即触发（不另存按钮） |
| 加载 | `v-loading` / skeleton | >300ms 操作给骨架（`progressive-loading`，P3） |

---

## 4. 全局布局骨架（App Shell）

```
┌─ Sidebar(240) ─┬─────────────────────────────────────────────┐
│  Logo 60h      │  TopBar 60h：面包屑 ............ [模型已连接] │
│ ├─────────────┼─────────────────────────────────────────────┤
│ │ 📋 条款库    │                                             │
│ │ 📋 生成任务  │            <router-view />                   │
│ │ ⚙ 模型配置   │            （当前页内容）                     │
│ │              │                                             │
│ │ (flex-1)     │                                             │
│ └─────────────┴─────────────────────────────────────────────┘
```

| 区域 | 宽/高 | 规范 |
|---|---|---|
| Sidebar | 固定 240px（`w-60`） | logo 60h + nav（图标+文字，`nav-label-icon`，P9）+ 当前项高亮（`nav-state-active`） |
| TopBar | 固定 60h | 面包屑（`breadcrumb-web`，P9）+ 右侧模型连接状态 tag |
| Main | flex-1 | `router-view` 出口；各页自管滚动 |
| 整体 | `h-screen overflow-hidden` | 桌面工具，不做移动端；最小 1024px |

**目录约定（待落地，对齐 CLAUDE.md）：**

```
frontend/src/
├─ App.vue              # 仅 App Shell（sidebar + topbar + router-view）
├─ main.js              # createApp + ElementPlus + router + icons
├─ router/index.js      # 【新增】4 条路由
├─ views/               # 【新增】页面级组件（每页一文件）
│  ├─ LibraryView.vue
│  ├─ RunsView.vue
│  ├─ RunDetailView.vue
│  └─ ConfigView.vue
├─ components/          # 复用组件（重构后保留，删旧版死代码）
│  ├─ ClauseTable.vue
│  ├─ RunProgress.vue   # 节点进度（列表/详情复用）
│  └─ BomPreview.vue    # BOM 结构化预览
├─ api/                 # axios 封装（接线复用，见 §10 死代码清理）
└─ style.css            # 全局 + Tailwind 指令
```

---

## 5. 页面规格（逐页）

> 每页统一字段：**目的 / 布局 / 组件清单 / 数据源 / 交互 / 状态（空·加载·错误）/ UX 准则**。

### 5.1 页面 A — 条款库（`/library`，第一级）

**目的：** 管理所有条款（导入 / 新增 / 删除），点「生成」进入任务列表。

**布局：**

```
┌────────────────────────────────────────────────────────────┐
│ [📁 导入测试集 drag]   [➕ 新增]   🔍 搜索...（debounce）   │
├────────────────────────────────────────────────────────────┤
│ el-table                                                   │
│ 条款名称        | 编码       | 用例 | 版本 | 来源    | 操作│
│ 交付模式        | FSB0000011 |  23  | v1   | a.xlsx  |[生成][🗑]│
│ 收入分成        | FSB0000007 |  17  | v0   | a.xlsx  |[生成][🗑]│
│                                                            │
│ （无数据时：el-empty「上传测试集后显示条款」）             │
└────────────────────────────────────────────────────────────┘
```

| 元素 | 组件 | 数据源 | 触发 |
|---|---|---|---|
| 条款列表 | `el-table` | `GET /clauses` | onMounted + 导入后刷新 |
| 导入 | `el-upload drag` | `POST /testset/scan` | 选文件即上传 |
| 新增 | `el-dialog + el-form` | `POST /clauses` | 点新增→弹窗→提交 |
| 删除 | `el-popconfirm` | `DELETE /clauses/{block_code}` | 确认后删 + ElMessage.success |
| 搜索 | `el-input` | 前端 filter | debounce 300ms（`debounce-throttle`，P3） |
| 生成 | `el-button primary` | `POST /generate` | 点击→创建 run→跳 `/runs?block_code=X` |

**状态：**

| 状态 | 表现 |
|---|---|
| 空（无条款） | `el-empty` + 引导上传 |
| 加载 | `v-loading` 表格 |
| 错误（扫描失败） | `ElMessage.error` + 表单内联错误提示 |
| 成功（导入） | `ElMessage.success("已导入 N 条")` |

**UX 准则：** `confirmation-dialogs`(P8) `empty-states`(P8) `submit-feedback`(P8) `debounce-throttle`(P3) `no-emoji-icons`(P4)

> ⚠️ 当前 App.vue 的导入成功 **无 toast 反馈**（§9 审视 #5）；删除功能未接线（在死代码 `api/clauses.js` 有 `remove`）。

### 5.2 页面 B — 生成任务列表（`/runs`，第二级）

**目的：** 查看某条款（或全部）的生成任务、进度、状态，可停止 / 进详情。

**布局：**

```
┌──────────────────────────────────────────────────────────────┐
│ TopBar: 生成任务 / 交付模式        [筛选: 全部 ▾]             │
├──────────────────────────────────────────────────────────────┤
│ el-table                                                     │
│ 条款名 | 进度          | 状态   | 测试集  | 创建时间 | 操作  │
│ 交付   | ████░░ 5/7    | 执行中 | a.xlsx  | 17:10    |[详情][停止]│
│ 交付   | ██████ 7/7    | ✓成功  | a.xlsx  | 17:05    |[详情]     │
│ 收入   | ░░░░░░ 0/7    | 排队中 | a.xlsx  | 17:12    |[详情][停止]│
│ 交付   | ████░░ 5/7    | ✗失败  | a.xlsx  | 17:00    |[详情]     │
└──────────────────────────────────────────────────────────────┘
```

| 元素 | 组件 | 数据源 | 说明 |
|---|---|---|---|
| 进度 | `el-progress :percentage :text-inside` | `run.progress`（后端已算好 %） | 后端 `GET /runs` 直接返 progress/done_nodes/total_steps，**前端别重算** |
| 状态 | `el-tag` | `run.status` | 见 §3.2 状态映射（字段名 `status`，不是 run_status） |
| 停止 | `el-button danger` + `el-popconfirm` | `POST /runs/{id}/stop` | 仅 `run.status==='running'` 时显示 |
| 详情 | `el-button` | 路由 `/runs/:id` | — |
| 自动刷新 | 轮询 `GET /runs` | 2s | `route.query.block_code` 透传；**任一 run.status==='running' 时轮询，全终态停**；onUnmounted 必清（§6.3） |

**路由参数：** `block_code` 从 `route.query.block_code` 读（条款库点「生成」后 `router.push({path:'/runs', query:{block_code:bc}})`），透传给 `GET /runs?block_code=X`；无 query 则列全部。

**失败 run 无「重试」按钮**（后端无 retry 端点）；重跑 = 回条款库点「生成」新建 run。

**UX 准则：** `loading-buttons`(P2) `confirmation-dialogs`(P8) `nav-state-active`(P9) `number-tabular`(P6)

> ✅ 后端 `GET /runs` + `POST /runs/{id}/stop` 已就绪（B 方案 commit `aabcb02`，含 finish-cancelled 守护，见 §6）。

### 5.3 页面 C — 任务详情（`/runs/:id`，第三级）

**目的：** 看单次 run 的全过程（节点进度 + 选取数据 + BOM 结果 + 提示词）。

**布局：**

```
‹ 返回任务列表    交付模式（财经视角）

┌─ 任务信息 ────────────────────────────────────────────┐
│ run_id: 13   创建: 2026-07-06 17:10   状态: 失败      │
│ 耗时: 4.3s   测试集: testdataset.xlsx                 │
└──────────────────────────────────────────────────────┘

┌─ 执行进度（7 节点中文化）─────────────────────────────┐
│ ✓ [1] 关键词抽取        598ms                         │
│ ✓ [2] 正例挑选          131ms                         │
│ ✗ [3] 定义+规则生成     1365ms  ❌ 403 认证失败        │
│ ○ [4] 召回画像组装      —                             │
│ ○ [5] 规则校验          —                             │
│ ○ [6] 自检              —                             │
│ ○ [7] 提示词组装        —                             │
└──────────────────────────────────────────────────────┘

┌─ 选取数据（聚类选的代表正例）─────────────────────────┐
│ el-table  文档ID                 | 期望结果（片段）   │
│ M3T1A384N121756732...           | 2.补充约定…预付款30%│
│ M3T1A782N122331094...           | 认证物料价格及货期… │
└──────────────────────────────────────────────────────┘

┌─ BOM 结果（折叠）─────────────────────────────────────┐
│ ▸ 定义   ▸ 拦截规则   ▸ 毒药词   ▸ 匹配规则           │
│ ▸ 排雷思维链   ▸ 召回画像   ▸ 完整提示词 [复制]       │
└──────────────────────────────────────────────────────┘
```

| 区块 | 数据源 | 说明 |
|---|---|---|
| 任务信息 | `GET /runs/{id}/status` | run_id / 状态 / 耗时 / nodes |
| 执行进度 | `status.nodes[]` | 中文化 skill 名（§7 映射表）+ ✓/✗/○ + 耗时 |
| 选取数据 | `result.selected_examples[]` | ✅ 已就绪（B 方案）：返 `[{doc_id, expected_value, item_code, item_name, doc_name}]`；展示 doc_id（mono+截断 P6）+ expected_value 片段，其余字段做 tooltip/展开行。失败/取消 run 也能取到 |
| BOM 结果 | `GET /runs/{id}/result` → `bom` + `full_prompt` | 折叠面板 `el-collapse`；提示词代码块 + 复制 |

**UX 准则：** `breadcrumb-web`(P9) `progressive-disclosure`(P8 折叠) `truncation-strategy`(P6 doc_id) `motion-meaning`(P7 折叠动画)

---

## 6. 后端 API 契约（前端视角）

> 权威源：`docs/技术设计-生成场景后端专项.md` + `backend/src/cc_bom_generator/api/routers/generate.py`。

### 6.1 端点表（含状态诚实标注）

| Method | Path | 用途 | 状态 | 前端页 |
|---|---|---|---|---|
| GET | `/health` | 健康检查 | ✅ | — |
| POST | `/testset/scan` | 上传测试集 + 扫条款 + upsert | ✅ | A |
| GET | `/clauses` | 条款列表（持久化） | ✅ | A |
| POST | `/clauses` | 手动新增 | ✅ | A |
| PUT | `/clauses/{block_code}` | 改条款 | ✅ | A |
| DELETE | `/clauses/{block_code}` | 删条款 + 级联清理 | ✅ | A |
| POST | `/generate` | 异步生成，返 run_id | ✅ | A→B |
| GET | `/runs` | **任务列表（含进度%）** | ✅ B 方案（待 commit） | B |
| GET | `/runs/{id}/status` | 节点进度 | ✅ | B/C |
| GET | `/runs/{id}/result` | BOM + 提示词 + 选取正例 | ✅ B 方案（含 selected_examples，失败/取消也返） | C |
| POST | `/runs/{id}/stop` | **停止任务** | ✅ B 方案（待 commit，finish 守护已修） | B |
| GET/POST | `/config` | 模型配置读写 | ✅ | 配置页 |

**图例：** ✅ 已就绪可联调 ｜ 🟡 工作区已写待 commit ｜ ⏳ 缺口待补

### 6.2 后端缺口（原型揭示）—— B 方案处理状态（2026-07-08）

| # | 缺口 | 影响 | 状态 | 处理 |
|---|---|---|---|---|
| 1 | `GET /runs` + `POST /runs/{id}/stop` | 页面 B | ✅ 已补 | B 方案写好（generate.py），含 progress%（done/7×100，is_retry=False 计数）+ stop 的 running 前置守护。待 commit |
| 2 | **finish 覆盖 cancelled bug** | 页面 B 停止无效 | ✅ 已修 | `repository.finish_pipeline_run` 加守护：用列查询读 DB 最新 run_status（绕后台线程独立 session 的 identity map 缓存），cancelled 则 return 不覆盖。资深测试并发推演 a/b/c/d 实证通过；TOCTOU 窄窗口 benign，不加 orchestrator 双保险 |
| 3 | `result` 缺 `selected_examples[]` | 页面 C 选取数据 | ✅ 已补（超预期） | 新增 `PositiveExample` 行契约（schemas/cleaned_test_set.py）+ Skill2 在**全行**上聚类选代表正例带 doc_id + orchestrator 落节点 output_json + `run_result` 返回。形状 `[{doc_id, expected_value, item_code, item_name, doc_name}]`（比原型多 3 追溯字段）。`run_result` 已放宽：失败/取消也返已产出部分（对齐原型「失败详情也看选取」）。真实数据验证 PASS |
| 4 | stop 不真中断后台 Thread | 页面 B 体验 | ⚠️ 已知限制（保留） | daemon Thread 无法中断 LLM 调用；stop 只标 cancelled 靠 #2 守护。**诚实限制**：① 点停止后当前节点仍会跑完；② 极窄并发窗口（bg 收尾 finish 的毫秒级，且 stop 要求 status==running 才触发）下，已停任务最终态可能显示为 success/fail 而非 cancelled（benign，非脏数据落库；资深测试 test_d 实证）。UX 文案待定（页面 B 停止按钮提示语） |

> **契约变更通知（CLAUDE.md 铁律 9）**：#3 改了 `schemas/cleaned_test_set.py`（A→B 交接契约，新增 `PositiveExample` + `positive_examples` 行字段）和 `services/ingest_service.py`（杨力文件，简版）解析全列。**杨力的正式 A 模块 ingest 接管时，必须产出含 `positive_examples` 行的 `CleanedTestSet`**（doc_id 等从源测试集带入）。需开 PR / 通知杨力 review。

### 6.3 轮询契约（前端 ↔ 后端）

| 参数 | 值 | 说明 |
|---|---|---|
| 间隔 | 2000ms | `setInterval` |
| 超时 | 5 分钟 | 超时标 error |
| 容错 | 连续 5 次失败 | 标 error「连接中断」 |
| 终态 | `success` / `fail` / `cancelled` | 命中即停轮询 + 拉结果 |
| 清理 | **onUnmounted 必清 pollTimer** | ⚠️ 当前 App.vue 漏了（§9 审视 #3） |

---

## 7. 关键状态机与映射

### 7.1 任务状态机（后端 run_status）

```
        POST /generate              节点逐个 commit
queued ─────────────→ running ──────────────→ success
                         │
                         ├── 异常 ──────────→ fail
                         │
                         └── POST /stop ────→ cancelled
                                  （finish 守护不覆盖）
```

### 7.2 前端 run phase（本地态）

```
idle ──startGenerate──→ running ──success──→ done
                          │                    
                          ├── fail/cancelled ──→ error
                          └── 超时/断连 ───────→ error
```

### 7.3 Skill 名中文化映射（全局常量，列表/详情复用）

```js
const SKILL_NAMES = {
  FeatureExtractSkill:  '关键词抽取',
  ExampleRetrieveSkill: '正例挑选',
  DefinitionRuleSkill:  '定义+规则生成',
  ProfileBuildSkill:    '召回画像组装',
  RuleCheckSkill:       '规则校验',
  SelfCheckSkill:       '自检',
  PromptAssembleSkill:  '提示词组装',
}
```

> 当前 App.vue（行 93-98）与死代码 GeneratePanel.vue（行 6-14）**各有一份映射**，重构后只保留一份，放 `constants/skill.js`。

---

## 8. 交互流（端到端时序）

```
用户               前端                         后端
 │                  │                            │
 ├─上传 xlsx──────→│ POST /testset/scan ────────→│ scan + upsert clauses
 │                  │← clauses[] ────────────────│
 │                  │ ElMessage.success("已导入")│
 │                  │                            │
 ├─点「生成」─────→│ POST /generate ────────────→│ 创建 run
 │                  │← run_id ───────────────────│
 │                  │ 跳 /runs?block_code=X       │
 │                  │ 轮询 GET /runs/{id}/status  │
 │                  │← nodes[]（实时）────────────│
 │                  │ el-progress 更新            │
 │                  │                            │
 ├─点「详情」─────→│ 跳 /runs/:id                │
 │                  │ GET /status + /result      │
 │                  │← 进度 + BOM ───────────────│
 │                  │                            │
 ├─点「停止」─────→│ POST /runs/{id}/stop ──────→│ 标 cancelled
 │                  │ ElMessage("已停止")         │ （finish 守护不覆盖）
 │                  │                            │
 └─复制提示词────→│ clipboard.writeText ───────→│ （纯前端）
```

---

## 9. 现状评估（99 UX 准则审视当前 App.vue）

> 审视对象：当前在线的 `frontend/src/App.vue`（单页分屏，07-06 重写版）。准则编号见 ui-ux-pro-max 优先级表。

### 9.1 必须修（CRITICAL / HIGH）

| # | 问题 | 准则 | 现状 | 改法 |
|---|---|---|---|---|
| 1 | **路由缺失** | P9 `deep-linking`/`back-behavior`/`nav-state-active` | `activeMenu` ref 假切页，无 URL / 无后退 / 无深链 | 接 vue-router，4 路由（§2） |
| 2 | **轮询不清理** | P3 `debounce-throttle` + 资源泄漏 | `App.vue` 无 `onUnmounted` 清 `pollTimer`，组件卸载后仍轮询 | `onUnmounted(() => stopPoll(currentRun))`（死代码 GeneratePanel 反而做对了，行 81） |
| 3 | **emoji 当图标** | P4 `no-emoji-icons` | 按钮「🚀 生成」、上传「📁」、状态「✓」混用 emoji | 全换 Element Plus icon（`Promotion`/`Upload`/`CircleCheckFilled`），按钮文字不带 emoji |
| 4 | **配置页空壳** | P9 `nav-hierarchy` | sidebar 有「模型配置」项，点无反应（无 UI） | 接 `ConfigView`（死代码 ConfigPanel.vue 可改造复用） |
| 5 | **导入无成功反馈** | P8 `submit-feedback`/`success-feedback` | `onUploadChange` 成功只更新 clauses，无 toast | `ElMessage.success("已导入 N 条")` |

### 9.2 应优化（MEDIUM）

| # | 问题 | 准则 | 改法 |
|---|---|---|---|
| 6 | 空状态对比度低 | P1 `color-contrast` | 「选择左侧条款」用 `text-slate-300`（#cbd5e1），对比度 < 4.5:1 → 改 `slate-400` 起；或用 `el-empty` |
| 7 | 搜索无 debounce | P3 `debounce-throttle` | 条款 < 50 时影响小；> 50 加 300ms debounce（标注触发条件） |
| 8 | 无骨架屏 | P3 `progressive-loading` | LLM 慢，首次拉 result 时给 skeleton 而非空白 |
| 9 | 进度无 `el-progress` | P10 | 任务列表用进度条（当前仅详情有节点列表） |

### 9.3 死代码（必须删，零引用）

| 文件 | 行数 | 状态 | 处理 |
|---|---|---|---|
| `components/GeneratePanel.vue` | 285 | Element Plus 重写前的旧版（原生 input/button + CSS 变量），未被引用 | **删除** |
| `components/ConfigPanel.vue` | 118 | 同上旧版表单，未被引用 | **删除**（配置页用新 `ConfigView` 重写） |
| `api/index.js` | 23 | axios 封装，App.vue 改用裸 axios 后零引用 | **保留并接线**（§10 重构后统一用它） |
| `api/generate.js` / `config.js` / `clauses.js` | 各 ~25 | 为组件化写的 API 模块，零引用；`clauses.js` 含未接线的 CRUD | **保留并接线**（routes 化后复用） |

> **结论：** 2 个旧版组件删；4 个 api 模块**不是死代码而是「未接线」**——路由化重构时统一接回（`api/index.js` 的响应拦截器正好解决 §9.1 #5 的统一错误提示）。Skill 名映射两份去重（§7.3）。

---

## 10. 开发进度与路线图

### 10.1 已完成（截至 2026-07-06）

- ✅ 技术栈就位：Vue3 + Element Plus + Tailwind + Vite（代理 /api → :8000）
- ✅ App Shell：sidebar(240) + topbar(60) + 左右分屏（单页）
- ✅ 左屏：el-upload 导入 + el-table 条款列表 + 搜索 filter
- ✅ 右屏：生成按钮 + 节点进度列表 + BOM 结构化预览（el-descriptions）+ 提示词代码块 + 复制
- ✅ 异步联调：POST /generate → 轮询 /status → /result（2s/5min/5 次容错）
- ✅ 持久化：onMounted 拉 /clauses（刷新不丢）
- ✅ 图标全局注册（main.js）

### 10.2 当前 Gap（→ 目标 3 层 IA）

| 优先级 | 工作项 | 依赖 | 产出 |
|---|---|---|---|
| **P0** | 接 vue-router（4 路由）+ 建 `views/` | 无 | URL 化、深链、后退 |
| **P0** | 删死代码（2 旧组件）+ 接线 4 个 api 模块 + Skill 映射去重 | P0 路由 | 统一 axios 封装 + 错误提示 |
| **P0** | 后端 commit `GET /runs` + `POST /stop` | 后端 | ✅ B 方案已写待 commit（页面 B 可联调） |
| **P1** | 页面 B 生成任务列表（el-progress + 状态 tag + 停止/详情） | P0 | 第二级落地 |
| **P1** | 后端修 finish 覆盖 cancelled bug（§6 #2） | 后端 | ✅ B 方案已修（repository 列查询守护） |
| **P1** | 后端 result 加 selected_examples（§6 #3） | 后端 | ✅ B 方案已补（带 doc_id，真实数据 PASS） |
| **P1** | 页面 C 任务详情（折叠 BOM + 选取数据 + 中文化节点） | P1 后端 | 第三级落地 |
| **P1** | 页面 A 增强：新增/删除（popconfirm）+ el-empty + 导入 toast + debounce | 无 | 第一级完整 |
| **P2** | 配置页 ConfigView（接线 configApi） | 无 | sidebar 第 3 项落地 |
| **P2** | a11y 修复（去 emoji、对比度、reduced-motion） | 无 | WCAG AA |

### 10.3 决策记录

- **不引入状态管理库**（Pinia）：单工作台、状态局部化够用，符合「务实反对过度工程」（用户偏好）。
- **不外加载英文字体**：内部中文工具，系统 CJK 字体首屏优先。
- **不做移动端**：桌面 ≥ 1024px 工具，最小可用即可。

---

## 11. 变更协议（铁律）

> 对应 CLAUDE.md「进度跟踪纪律」在前端的延伸。

**任何前端改动（新增 / 修改 / 优化 / 修 bug），落地前必须：**

1. **更新本文档对应章节** —— 改了布局改 §5，改了契约改 §6，改了进度改 §10。
2. **§12 变更日志追加一行** —— 格式：`| 日期 | 类型 | 章节 | 说明 | commit |`。
3. **同步 `docs/progress.md`** —— 林大宇段落加一行（日期/模块/文件/说明）。
4. **同步 `CLAUDE.md` 目录树** —— 仅当新增 / 删除 / 移动文件时。
5. **改后端契约（§6 端点表）= 停止 + 通知** —— 触发 CLAUDE.md 铁律 9（契约是协作边界）。

**未同步文档 = 违规，不允许 commit。**

---

## 12. 变更日志

| 日期 | 类型 | 章节 | 说明 | commit |
|---|---|---|---|---|
| 2026-07-08 | 初版 | 全文 | ui-ux-pro-max 审视 + 沉淀：定 3 层 IA / Data-Dense Dashboard 设计系统 / 后端契约（含 4 缺口）/ 死代码清单 / 路线图 / 变更协议 | `43e28b6` |
| 2026-07-08 | 后端-B 方案 | §6.1/§6.2/§5.3/§10.2 | 补原型 4 缺口：`GET /runs`(progress%) + `POST /stop` + finish-cancelled 守护(repository 列查询) + selected_examples 全链路带 doc_id(新增 PositiveExample 行契约，真实数据 PASS)；run_result 放宽（失败/取消也返）；资深测试 24 项 pytest 全绿、并发推演通过。**契约变更需通知杨力（铁律9）** | `43e28b6` |
| 2026-07-08 | 前端施工补遗 | §3.2/§5.2/§13 | 资深前端 agent 评审后修施工缺口：§3.2 status 字段名(run_status→`status`)、§5.2 删无端点的重试按钮+block_code 来源(route.query)+轮询条件；新增 §13 施工补遗（跨页状态约定/字段映射/组件 props 边界/迁移顺序/router mode/错误边界等） | （待 commit） |

---

## 13. 施工补遗（按资深前端评审，2026-07-08）

> 评审结论：设计层 OK，施工层缺字段级/组件级细节。本节补齐至 build-ready。

### 13.1 跨页状态传递约定（不引入 Pinia 的替代方案，**阻塞项**）

| 状态类型 | 方案 | 说明 |
|---|---|---|
| 路由参数（block_code / run_id） | `route.query` / `route.params` | 条款库→`/runs?block_code=X`；列表→`/runs/:id`。URL 即状态，可分享/刷新 |
| 会话级刚创建未落库的 run | `composables/useRunPoll.js` **模块级单例 ref** | 条款库点生成→POST /generate 拿 run_id→立即写进单例→跳 `/runs`；RunsView onMounted 读单例 + 拉 `GET /runs` 合并，避免竞态（列表还没该 run） |
| 列表/详情各自的轮询 | 组件内 ref + `onUnmounted` 清理 | **轮询发生点**：RunsView（列表轮询）+ RunDetailView（详情轮询），**两处都要 onUnmounted 清 pollTimer** |
| 条款选中态 | 不跨页（各页自管） | LibraryView 本地 selectedClause；RunsView 用 route.query.block_code 定位 |

### 13.2 字段映射表（前端列 ↔ 后端字段）

| 页 | 前端列/展示 | 后端字段 | 端点 |
|---|---|---|---|
| A 条款库 | 条款名称/编码/用例/版本/来源 | `block_name`/`block_code`/`positive_count`/`current_version`/`source_file` | `GET /clauses` |
| B 任务列表 | 进度/状态/测试集/创建/耗时 | `progress`/`status`/`source_file`(从clause)/`started_at`/`duration_ms` | `GET /runs` |
| C 任务详情 | run_id/状态/耗时/nodes/选取/BOM | `run_id`/`status`/`duration_ms`/`nodes[]`/`selected_examples[]`/`bom`+`full_prompt` | `/status` + `/result` |

> `GET /runs` 不直接返测试集名；若要展示，RunsView 用 `run.block_code` 反查 clause 列表拿 `source_file`，或后端补字段（P2）。

### 13.3 复用组件 props/emits 边界（§4 组件为**新建**，非保留）

| 组件 | props | emits | 形态 |
|---|---|---|---|
| `ClauseTable.vue`【新建】 | `clauses`, `loading`, `selected`(bc) | `select`, `generate`(bc), `delete`(bc) | 纯展示+事件，**不自带 fetch**（父组件拉数据传入） |
| `RunProgress.vue`【新建】 | `nodes[]`, `mode: 'bar'\|'list'` | — | `bar`：`el-progress :percentage`（列表用）；`list`：节点清单 ✓/✗/○（详情用）。**双形态靠 mode prop 切** |
| `BomPreview.vue`【新建】 | `bom` | — | `el-collapse` 7 块；定义/拦截默认展开，其余收起 |

### 13.4 App.vue（337 行）逻辑搬迁归属

| 现有逻辑 | 迁到 |
|---|---|
| `activeMenu`/menuItems | 删（router-link-active 接管 sidebar 高亮） |
| 上传/扫描/clauses/搜索 | `LibraryView.vue` + `clausesApi` |
| `runs`/startGenerate/startPoll/stopPoll | `composables/useRunPoll.js`（**跨页单例**，含 onUnmounted；参考 GeneratePanel.vue:81 的正确清理） |
| currentRun/Bom/Prompt computed | `RunDetailView.vue` 本地 |
| `SKILL_NAMES` | `constants/skill.js`（全局唯一） |
| `copyPrompt` | `composables/useClipboard.js` 或详情页本地 |

### 13.5 迁移顺序依赖图（**严格按序**，避免断网/丢逻辑）

```
1. 建 router/index.js + views/ 4 空壳 + App.vue 改纯 Shell(router-view)  ← 空壳能跑
2. 抽 composables/useRunPoll.js（含 onUnmounted，参考 GeneratePanel:81）+ constants/skill.js
3. views 内接线 api/ 4 模块（已可 import，见 §13.6）实现 3 页 + ConfigView
4. 全绿验证（联调后端）
5. 删死代码 GeneratePanel.vue / ConfigPanel.vue（此时其有用逻辑已抽进 composable）
```
> ⚠️ **不要先删死代码再接线**——GeneratePanel 的 onUnmounted 清理是正确逻辑，必须先抽进 useRunPoll 再删，否则回归 bug（§9.1#2）。

### 13.6 api/ 模块状态更正（§9.3 过保守）

`src/api/`（index/generate/config/clauses 4 模块）**代码完整、可直接 import**（`clausesApi` 含全 CRUD、`generateApi` 含 start/status/result、`configApi` 完整、`index.js` 响应拦截器已统一处理错误+404 静默）。§9.3"未接线"应理解为"App.vue 单文件没引用"，**路由化重构时直接 import 使用即可**，无需重写。

### 13.7 其他施工决策

- **router mode**：`createWebHistory`（生产 nginx 需 `try_files $uri $uri/ /index.html` 兜底，否则刷新 `/runs/1` 404）；若 nginx 暂未配，开发期可用 `createWebHash` 过渡。
- **错误边界**：详情页 `/runs/:id` 不存在→后端 404→前端 `el-empty`「任务不存在」+返回按钮；500→`ElMessage.error`+重试。`api/index.js` 已对 404 静默，各页自行渲染空态。
- **模型连接 tag**（TopBar）：当前硬编码 success，**装饰性**；未来接 `/health`+config 校验。文档标注诚实。
- **`PUT /clauses/{block_code}`**：后端有，前端**暂不接编辑交互**（预留，P2 再做行内编辑）。
- **`POST /generate` 的 file**：条款库点「生成」时**不传 file**（复用 scan 存的 `latest.xlsx`），只传 `clause`+`block_code`。
- **空状态文案统一**：A 页 `el-empty`「上传测试集后显示条款」；C 页无 run「选择条款生成后查看详情」。三处文案对齐。
- **a11y 落地点**：① 状态用 icon+文字不只靠色（§3.2 tag 配 icon）；② 折叠/图标按钮加 `aria-label`；③ `@media (prefers-reduced-motion)` 关 hover 阴影/进度条动画。
- **原型路径修正**：§0 引用的 `docs/design/prototype-redesign.html` 实际在 **`docs/archive/`**。

