# 验证日志（generate / 调优闭环）

> 验证阶段的报错记录，按 `#N + 日期` 索引。你说「第 N 次」「刚才那次」或大致时间，我就能查到。
> 服务端详细栈在 uvicorn 后台日志（本 session task `bjv6jux43` 的 output 文件）。
> 每条记录：输入 / 错误 / 服务端栈 / 原因 / 修复 / 状态。

---

## 验证 #1 | 2026-07-02

- **输入**：Swagger UI `/api/generate`，`clause=付款支持文档`，其余默认
- **错误**：`422 Unprocessable Entity` — `Value error, Expected UploadFile, received: <class 'str'>`，`input: "string"`
- **服务端栈**：无（请求在 FastAPI 入参校验层被拒，未进业务逻辑）
- **原因**：Swagger UI 的 `file` 字段传了占位字符串 `"string"`，没真正选 xlsx 文件 —— **操作问题，非代码 bug**
- **修复**：`file` 字段点「选择文件」按钮选 `procurement_payment_support_documents.xlsx`；或用 curl `-F "file=@/e/Python_Project/CC-BOMGenerator/test/docs/procurement_payment_support_documents.xlsx"`
- **状态**：✅ 已解决（操作指引）

---

## 验证 #2 | 2026-07-02 02:11

- **输入**：`procurement_payment_support_documents.xlsx`（curl 上传成功），`clause=付款支持文档`
- **错误**：`500 Internal Server Error` — `'gbk' codec can't encode character '✅' in position 19: illegal multibyte sequence`
- **服务端栈**：`UnicodeEncodeError` @ `pipeline.generate_bom` → `print(f"\n  ✅ 生成完成...")` → uvicorn stdout（Windows cp936）编码 ✅ 失败
- **原因**：**真 bug**。`pipeline.py:54` 用 `print` 输出含 emoji 的字符串到 uvicorn stdout，Windows 控制台默认 GBK 编码无法编码 ✅，整个请求 500（DB 已写、BOM 已生成，但响应阶段 print 崩了）
- **修复**：① `logging_config.py` 把 `sys.stdout/stderr.reconfigure(encoding="utf-8")`（根治所有 emoji/特殊字符编码）② `pipeline.py` 的 3 行 `print` 改 `log.info` + 去掉 ✅ emoji（log 规范不用 emoji）
- **状态**：✅ 已修复（logging_config utf-8 + pipeline print→log.info 去 emoji）— 验证 #3 确认编码问题不再出现

---

## 验证 #3 | 2026-07-02 02:18

- **输入**：同 #2（编码修复后重跑），curl 上传 `procurement_payment_support_documents.xlsx`，`clause=付款支持文档`
- **错误**：`500` — `大模型输出无法解析为 JSON（重试 1 次后仍失败）`，@ `ProfileBuildSkill`（seq=4，耗时 19.6s）
- **服务端栈**：`llm/client.py:106` `call_json` → `_parse_json` 失败 → `ValueError` → orchestrator 500；pipeline_run status=fail
- **原因**：ProfileBuildSkill 调 LLM 产 `recall_profile`，LLM 输出 JSON 解析失败。错误信息 `text[:500]` 只附前 500 字符（截断在 `semantic_queries` 中间），无法判断是 **LLM 真截断**（讯飞 max_tokens cap）还是**格式问题**（多余文字/JSON 不合法）。需看完整 LLM 输出才能定论。
- **修复**：⏳ 诊断中 —— 先改 client 记完整 LLM 输出到日志，重启重跑确认根因，再定修复（增大 max_tokens / 精简 prompt / 加固 _parse_json）
- **状态**：✅ 已修复 — `_parse_json` 加 trailing comma 容错（LLM 常见 `{"a":1,}` 错）+ 完整 LLM 输出日志；重跑 generate 成功（见 #4）

---

## 验证 #4 | 2026-07-02 02:25

- **输入**：同 #3（修复后），curl `-F "clause=付款支持文档"` + `procurement_payment_support_documents.xlsx`
- **结果**：✅ **generate 链路通了！** 200 返回完整 BOM（`semantic_definition` + 5 条 `core_match_rules` + 3 条拦截规则 + 召回画像，中文正常）
- **小问题**：`bom.clause` 字段乱码 `¸¶¿îÖ§³ÖÎÄµµ`（应为"付款支持文档"），其他字段中文正常
- **原因**：curl 命令行的中文参数在 Windows git bash 经 GBK 编码发送，服务端按 UTF-8 解码 → 乱码。**输入编码问题，非代码 bug**（其他中文字段来自 LLM 的 UTF-8 输出，所以正常）
- **修复建议**：① 用 Swagger UI（浏览器 UTF-8）调，clause 不乱码；或 ② Excel 带 `block_name` 列，clause 从 Excel 取（不依赖命令行参数）
- **状态**：✅ generate 链路已通（编码 #2 + JSON 解析 #3 两大 bug 已修），clause 乱码用 Swagger UI 规避

---

## 验证 #5 | 2026-07-02 ~02:30

- **输入**：同前，curl 中文 clause（乱码）+ Excel，**第 2 次 generate**（block_code 空）
- **错误**：`500` — `IntegrityError (1062, "Duplicate entry '1' for key 'bom_versions.uq_bom_version'")`
- **服务端栈**：`save_bom_version` 插入 `(block_code='', version=1)` → 唯一约束 `(block_code, version)` 冲突（#4 那次已插入同 `block_code='' version=1`）
- **根因链**：① clause 参数 curl 中文乱码 ② Excel 无 block_code 列 → block_code='' ③ generate 固定 version=1 → 同 block_code='' 第二次 generate → `(block_code='', version=1)` 重复
- **修复方向**（含用户诉求）：① clause 不必填（默认从测试集 block_name 列取）② block_code 从测试集取或由文件名生成（非空）③ version 自增（同 block_code 再 generate → 版本 +1，避免冲突）
- **状态**：✅ 已修复 — ① `clause` 改 `Form("")` 可选 ② `find_col` 加去下划线（`Block Code`/`Block Name` 匹配上）③ `save_bom_version` version 自增。重跑 generate 成功：`clause=付款支持文档`（中文正常，from Excel）/ `block_code=FSB0000004` / `version=1`，BOM 完整返回

---

## 验证 #6 | 2026-07-02 ~02:40（业务专家 agent 审查输出质量）

- **输入**：generate 完整输出（22722 字节，付款支持文档条款）
- **审查**（业务专家 agent 对比 schemas 契约 + 业务质量）：
  - **契约齐全 ✅**：BOM 全字段（clause/block_code/version/source/status/semantic_definition/extraction_rules[2拦截+4匹配]/recall_profile[10关键词+6混淆+6章节+3语义查询+5正例]/created_at）、full_prompt、verification 都在
  - **完整性 ✅**：无截断/乱码，prompt_text 1882 字结构完整（定义+规则+画像+JSON Schema）
  - **业务质量 7.5/10**：方向正确无误塞，有过拟合
- **Critical 问题**：
  - C1：`positive_keywords` 含"华为"（公司名过拟合，跨合同泛化失效，直接拖累跑分）
  - C2：prompt 命中规则标题"下面3点命中其一条"实际列了 4 条（数量矛盾，模型可能只认前3条）
- **Important**：正例含公司名/金额/地址（污染向量召回）；confusion_words 选错（把"专用发票/开具/转账"等本条款强相关词当混淆，应改付款金额/时间/比例/方式）；缺"纯验收标准/流程"拦截规则；否定规则"仅流程无实质"与命中规则③"提交方式"边界冲突；fixes 标称覆盖23正例但 verification 只验5条
- **状态**：⏳ 待修复（generate 输出质量问题，非阻塞链路）—— 阶段 2 处理（C1「华为」按跑分是否跨主体定，不一刀切）

---

## 验证 #7 | 2026-07-02 ~03:xx（进度反馈 + 前端 demo 搭建 + 多 agent 验证）

### 进度反馈（阶段 1）
- generate 改异步：`POST /generate` 立即返回 run_id（后台线程跑节点）+ `GET /runs/{id}/status`（查节点进度）+ `GET /runs/{id}/result`（取 BOM）
- orchestrator.run 加 `run_id` 参数（异步复用预创建 run）
- 验证 run_id=9：11 节点（7 首次 + 4 回修，48s）实时可见 ✅
- 修 result 500（GenerateResponse.cleaned_test_set 默认 {}）

### 前端 demo（Vue3 + Vite）
- `frontend/`：index.html + src/main.js + src/App.vue（三环节：① 设计上传/参数 ② 进度实时节点+进度条 ③ 输出 BOM+提示词复制）
- Vite 代理 `/api` → backend:8000，5173 前端 + 8000 后端联调通

### 多 agent 验证
- **契约对齐 agent**：前端字段访问 vs 后端返回，逐字段核对 ✅ 全对齐
- **前端审查 agent**：发现轮询健壮性问题 → 已修：C1 超时熔断(5min)、C2 连续失败(5次)、I3 结果拉取 try/catch、I4 clipboard 降级、I7 重置清文件；模板 I6 文件清除按钮、M4 key 防复用错乱
- **状态**：✅ demo 链路通，用户浏览器 `localhost:5173` 可用

---
