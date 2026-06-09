# 财务文档脱敏工具 MVP 设计

- **日期**: 2026-05-31
- **状态**: 已批准，待实施
- **背景**: 财务审校场景下，需在将 Word 底稿交给外部 LLM 前完成主体脱敏；主客户为国家电投（国家电力投资集团有限公司）体系文档
- **北极星**: **脱敏效果** — 可识别主体替干净、可验证、词库随审计师使用持续变好

---

## 1. 产品定位

| 项 | 决定 |
|----|------|
| 系统角色 | LLM **前置**工具；**scan** 经 Mac Worker 调本机 Ollama 做实体发现，**run** 仍不调 LLM |
| 输入 | 单次 **1 个** `.docx` |
| 脱密范围 | 仅 **可识别主体**（公司/机构/人名/证件号等）；金额、比率、会计科目 **保留** |
| 占位符策略 | 批内（单文档）**全局一致**伪匿名，如 `[公司_1]`、`[姓名_1]` |
| 存储 | 词库与任务数据 **全部走数据库**，运行时 **不读 YAML 配置** |
| 访问控制 | **无**（内网/VPN 隔离） |
| UI | `/deid` **独立专业风**（与 ClawSocial 暖色主站分离）；Tab：**文档脱敏 \| 词库管理** |
| 文件生命周期 | 任务完成后 **24h** APScheduler 自动清理 + **手动删除** |

**不做（MVP）**: Excel、多文件批处理、词库批量导入/导出、修订 accept（LibreOffice）、批注 `comments.xml`、Rehydrate 还原、run 阶段 LLM、硬导出门禁。

**v2 增量（2026-06）**: scan 阶段经 `/ws/worker` 透明代理调用 Mac 本机 Ollama（`qwen3.5:4b-mlx`）做智能发现；叠加文档规则（以下简称/机构后缀）。详见 [`2026-06-08-deid-mac-worker-llm-design.md`](2026-06-08-deid-mac-worker-llm-design.md)。

---

## 2. 用户与场景

- **用户**: 财务审校师
- **典型流程**: 上传审计底稿 Word → 扫描确认主体 → 补充漏网 → 执行脱敏 → 下载脱密 docx + mapping + 验证报告 → 将 docx 交给外部 LLM
- **主客户包**: 国家电投（`spic`），默认启用；通用财务规则包（`general_finance`）默认启用

### 2.1 词库飞轮（越用越好）

```
处理底稿 → 发现漏网 → 手动补充 → 默认「保存到词库」
    → 后续文档 preset 自动命中 → 残留扫描通过率 ↑ → 手动补充次数 ↓
```

MVP 必须打通：**手动补充 → 词库沉淀 → 统计命中 → 词库页「最近加入」可见**。

---

## 3. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│  Vue  /deid                                              │
│  Tab: 文档脱敏 | 词库管理                                 │
└───────────────────────────┬─────────────────────────────┘
                            │ REST /api/deid/*
┌───────────────────────────▼─────────────────────────────┐
│  app/deid/service.py          任务状态机、编排             │
│  app/deid/engine/pipeline.py  双引擎调度                   │
└───────────────┬─────────────────────┬───────────────────┘
                │                     │
    ┌───────────▼──────────┐  ┌───────▼──────────────┐
    │ Engine A (主路径)     │  │ Engine B (兜底)       │
    │ unpack→merge→XML替换  │  │ python-docx         │
    │ →pack→validate        │  │ 同 ReplacementPlan  │
    │ →残留扫描             │  │ →残留扫描           │
    └───────────┬──────────┘  └─────────────────────┘
                │
    app/deid/vendor/office/   ← Anthropic skills docx 脚本（unpack/merge_runs/pack/validate）
                │
┌───────────────▼─────────────────────────────────────────┐
│  SQLite/MySQL — 词库表 + deid_jobs 等                    │
│  uploads/deid/{job_id}/ — 原文件、输出、ZIP               │
│  APScheduler — deid_cleanup（24h）                       │
└─────────────────────────────────────────────────────────┘
```

### 3.1 优先级

```
P0  脱敏干净（识别 + 替换 + 残留扫描 + 报告）
P1  可验证（verification_report + mapping + 摘要）
P2  好用（预览、词库、手动补充、任务列表、飞轮统计）
P3  版式（validate；兜底模式警告；命中段统一正文格式）
```

---

## 4. 脱敏引擎

### 4.1 Engine A — 主路径（XML）

**流程**:

1. `unpack(input.docx, work_dir)`
2. `merge_runs(work_dir)` — 合并相邻同 `w:rPr` 的 run，降低碎片化漏匹配
3. 对下列 XML **统一** 提取段落 → 匹配 → 写回:
   - `word/document.xml`
   - `word/header*.xml`
   - `word/footer*.xml`
   - `word/footnotes.xml` / `word/endnotes.xml`（尽量覆盖）
   - `word/document.xml` 内 `w:txbxContent` 下的 `w:p` **（MVP 要）**
4. `pack(work_dir, output.docx, original=input.docx, validate=True)`
5. **残留扫描**（见 §4.4）

**不做**: `comments.xml`、修订 accept、图片 OCR。

### 4.2 匹配归一化（MVP 要）

扫描与执行 **共用** `normalize_for_match(text)`:

- Unicode NFKC（全角→半角等）
- 折叠连续空白（「电 投」≈「电投」）

匹配在归一化串上找位置，写回针对 **原文 span**；词库 seed 为高频简称增加空格变体 alias。

### 4.3 ReplacementPlan（双引擎共用）

1. 加载白名单 → 标记保护区间
2. 加载已确认实体的全部 alias，**长度降序**匹配
3. 加载 `deid_pattern_rules`（信用代码、手机、邮箱、区域公司等）
4. 冲突：最长优先；从 **后往前** 应用替换
5. 分配占位符：按 `entity_type` 分组，组内字典序 → `[公司_1]`、`[姓名_1]` …

### 4.4 写回策略 — 占位符统一普通正文（方案 B）

- **仅当**段落 `full_text` 上存在至少一处替换命中时，才重建该段落
- 保留 `w:pPr`（含 `w:numPr` 列表编号）
- 删除段内全部旧 `w:r`，新建 **单个** `w:r` + 从 `styles.xml` Normal/`docDefaults` 读取的 **PLAIN_RPR**（中文 eastAsia 从 Normal 读，不写死）
- 未命中段落 **不重建**，保留原格式

### 4.5 Engine B — python-docx 兜底

**触发**: unpack 失败、pack/validate 失败、XML 超时/异常、或 `DEID_FORCE_DOCX=1`。

行为: 遍历 body + tables + header/footer；同 Plan；命中段 plain 重建；标记 `engine=python-docx-fallback`，摘要 **兼容模式** 警告。

### 4.6 残留扫描（MVP 要）

对输出 docx 再 unpack（不 merge），在所有目标 XML 的 `w:t` 中搜索:

1. 本任务 **已确认** 的全部 alias（归一化匹配）
2. 全局规则：18 位信用代码、18 位身份证、11 位手机号

结果写入 `deid_jobs.verification_json`:

```json
{
  "passed": false,
  "alias_residuals": [{"text": "国家电投", "location": "document.xml#p42", "snippet": "…"}],
  "pattern_residuals": [{"type": "credit_code", "snippet": "911…"}]
}
```

### 4.7 修订

**MVP 不考虑** accept_changes / LibreOffice。`w:ins` 内可见 `w:t` 仍参与匹配与替换。使用须知一句说明未接受修订风险即可。

---

## 5. 下载与验证（软门禁）

| 验证结果 | 行为 |
|----------|------|
| `passed=true` | 绿色「验证通过」，直接下载 ZIP |
| `passed=false` | 红色警告 + 残留列表；勾选 **「本人已知晓风险，仍要下载」** + 可选备注 → 写 `override_reason` → 允许下载 |

**不硬阻断下载**（用户明确不要导出门禁）。

ZIP 固定包含:

| 文件 | 说明 |
|------|------|
| `{原名}_desensitized.docx` | 脱敏结果 |
| `mapping.xlsx` | 原文 \| 占位符 \| 类型 \| 来源 \| 命中次数 |
| `verification_report.xlsx` | 检查项 \| 结果 \| 位置 \| 片段 |

---

## 6. 数据库设计

### 6.1 词库（长期）

**`deid_client_packs`**

| 字段 | 说明 |
|------|------|
| id, code, name, description | `spic`, `general_finance` |
| is_default, is_active | 新建任务默认勾选 |

**`deid_entities`**

| 字段 | 说明 |
|------|------|
| pack_id, entity_type | company / person / org / custom |
| canonical_name | 规范名 |
| placeholder_prefix | 公司 / 姓名 / 机构 |
| source | seed / admin |
| times_hit_total, last_hit_at | 飞轮统计 |
| first_seen_job_id | 可选，首次沉淀来源 |
| is_active, notes | |

**`deid_entity_aliases`**

| 字段 | 说明 |
|------|------|
| entity_id, alias_text | 唯一 (entity_id, alias_text) |
| match_mode | MVP: exact |
| priority, times_hit | |
| added_from | seed / library / job_manual |

**`deid_pattern_rules`** — regex、entity_type、placeholder_prefix、priority、pack_id（nullable=全局）

**`deid_whitelist_terms`** — term、term_type（exact/regex）、category、pack_id（nullable）

### 6.2 任务（单文档）

**`deid_jobs`**

| 字段 | 说明 |
|------|------|
| status | draft → scanning → scanned → confirmed → running → done / failed |
| pack_ids | JSON 或关联 |
| original_filename, file_type, stored_path, output_path | |
| engine | standard / python-docx-fallback |
| verification_json | 残留扫描结果 |
| override_reason | 软门禁勾选备注 |
| preview_ack_at | 替换预览确认时间 |
| completed_at, expires_at | 24h 起算 |
| created_at | |

**`deid_job_entities`** — batch 内确认实体: placeholder, source（preset/手动补充）, is_excluded, alias 组

**`deid_job_entity_aliases`**

**`deid_entity_mappings`** — 导出 mapping 数据源

**`deid_hit_logs`**（可选 MVP）— file_part, paragraph_index, snippet

### 6.3 UI 来源文案

| 内部值 | 界面 |
|--------|------|
| preset | **词库** |
| manual | **手动补充** |

---

## 7. 国家电投 Seed

脚本: `scripts/seed_deid_spic.py`（幂等，按 pack.code + alias_text 去重）

**spic_group → [公司_1]** 别名含: 国家电力投资集团有限公司、国家电投、国家电投集团、中国电投、中国电力投资集团公司、中电投、SPIC 等。

**独立实体**: 国家核电、电投产融（及曾用名）、上海电力、电投能源、吉电股份、远达环保、五凌电力、黄河水电、资本控股、财务公司等（见头脑风暴清单）。

**规则**: 信用代码、手机、邮箱、银行卡、`国家电投集团{2,8}电力有限公司` 等区域 regex。

**白名单**: 会计科目、报表名、准则术语、比率 pattern（约 200 条）。

**误并防护**: 「国投」「国家开发投资」等与 SPIC **分开**实体。

Seed 只跑初始灌库；之后增长靠 **词库 UI + 任务沉淀**。

---

## 8. API

### 8.1 任务

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/deid/jobs` | 任务列表（含剩余清理时间） |
| POST | `/api/deid/jobs` | 上传 docx，创建任务 |
| POST | `/api/deid/jobs/{id}/scan` | 扫描 |
| GET | `/api/deid/jobs/{id}/entities` | 实体列表 |
| POST | `/api/deid/jobs/{id}/entities` | 手动补充 |
| PATCH | `/api/deid/jobs/{id}/entities/{eid}` | 勾选/误报/合并 |
| POST | `/api/deid/jobs/{id}/preview` | 抽样替换预览 |
| POST | `/api/deid/jobs/{id}/confirm` | 锁定占位符 |
| POST | `/api/deid/jobs/{id}/run` | 执行脱敏 |
| GET | `/api/deid/jobs/{id}/export` | ZIP（含 override 参数） |
| POST | `/api/deid/jobs/{id}/rescan` | 重新扫描（保留手动补充） |
| DELETE | `/api/deid/jobs/{id}` | 删除任务及文件 |

### 8.2 词库

| 方法 | 路径 |
|------|------|
| GET | `/api/deid/packs` |
| GET/POST/PATCH/DELETE | `/api/deid/entities` + `/{id}/aliases` |
| POST | `/api/deid/entities/merge` |
| GET/POST/PATCH/DELETE | `/api/deid/pattern-rules` + `/test` |
| GET/POST/PATCH/DELETE | `/api/deid/whitelist` |

---

## 9. 前端 — 文档脱敏 Tab

### 9.1 三步向导

1. **上传** — 单 `.docx`；默认勾选 spic + general_finance  
2. **扫描与确认** — 实体表；手动补充（橙色 **手动补充**）；默认 **保存到词库**；重新扫描  
3. **执行与导出** — 替换预览；执行；验证摘要；下载 / 删除  

### 9.2 实体表

列: 勾选 | 实体 | 类型 | 来源（词库/手动补充）| 命中次数 | 占位符 | 操作（合并/误报/跳转词库）

排序: **手动补充置顶** → 命中多 → 未命中警告

### 9.3 执行后摘要（中文）

- 验证通过 / 未通过（N 处残留）
- 替换处数、实体数、引擎（标准/兼容）
- 覆盖: 正文/页眉/页脚/脚注/文本框 各几处
- **手动补充未命中** 列表（红色）
- 白名单跳过 N 处

### 9.4 使用须知（Step 3 固定）

- 验证报告与 mapping 仅本地保存，勿上传云端  
- 文本框/批注 MVP 未全覆盖，请抽查  
- 兼容模式可能改变版式  
- 未接受修订的文档可能有漏脱风险  
- **每次手动补充并保存到词库，后续文档将自动识别**

---

## 10. 前端 — 词库管理 Tab

| 子页 | 能力 |
|------|------|
| 实体 | 按 pack 筛选；增删改；别名 textarea（一行一个）；合并；启停；搜索 |
| 最近加入 | 30 天内 admin/job_manual 沉淀；命中次数 |
| 识别规则 | CRUD + regex 测试 |
| 白名单 | 精确词/正则；分类 |

新增 alias 时: 归一化去重，冲突则拒绝并提示已属实体。

词库变更 **不影响** 已完成 job；进行中 job 可 **重新扫描** 吃新词库。

**MVP 不做**: 批量 Excel 导入/导出。

---

## 11. 模块目录

```
app/deid/
├── vendor/office/          # unpack, merge_runs, pack, validate
├── engine/
│   ├── plan.py             # ReplacementPlan + normalize
│   ├── pipeline.py         # A/B 调度 + 残留扫描
│   ├── xml/
│   │   ├── walker.py
│   │   ├── text_extract.py
│   │   ├── replace.py
│   │   └── styles.py
│   └── docx_fallback.py
├── service.py
└── schemas.py

app/api/deid.py
app/jobs/deid_cleanup.py

website/src/views/DeidView.vue
website/src/components/deid/
website/src/stores/deid.ts

scripts/seed_deid_spic.py
tests/test_deid.py
```

---

## 12. 后台任务

**`deid_cleanup`** — 每小时:

```sql
SELECT id FROM deid_jobs
WHERE status = 'done' AND completed_at < now() - interval 24 hour
```

删除磁盘 `uploads/deid/{id}/` 及任务相关表行（词库不动）。

---

## 13. 依赖

| 依赖 | 用途 |
|------|------|
| defusedxml | XML 解析 |
| python-docx | 兜底引擎 |
| openpyxl | mapping / verification xlsx |

---

## 14. 验收标准

1. 含「国家电投」「电投产融」docx，词库命中，占位符为普通正文（命中段无加粗）  
2. 归一化:「国家 电投」可命中  
3. 文本框内公司名被替换  
4. 页眉公司名被替换  
5. 金额、「应收账款」不替换  
6. 手动补充 + 保存词库 → 新 job 自动命中；词库「最近加入」可见  
7. 残留未通过: 红警 + 勾选后可下载，`override_reason` 入库，报告标未通过  
8. 验证通过 job 可直接下载  
9. pack validate 失败时走兜底或 failed，有中文提示  
10. 手动删除 + 24h 清理有效  
11. `python -m pytest tests/test_deid.py` 通过  

---

## 15. V1.1+ Backlog

- Excel `.xlsx`（同 unpack 思路）
- 词库 Excel 导入/导出、团队共享 pack
- 扫描 Pass 3：未命中「XX有限公司」建议
- `comments.xml` 批注
- 按 pack 残留率趋势图
- span 级细粒度替换（不全段重建）

---

## 16. 头脑风暴决策记录

| 议题 | 结论 |
|------|------|
| 批 vs 单文档 | 单文档 |
| 格式 | 仅 Word |
| 占位符 | 方案 A 一致伪匿名；格式方案 B 统一正文 |
| 配置 vs DB | 全 DB + seed 脚本 |
| 词库 UI | MVP 必做 |
| 批量导入 | MVP 不做 |
| 访问控制 | 无 |
| 引擎 | Anthropic unpack/XML/pack 主 + python-docx 兜底 |
| 归一化 / txbx / 残留扫描 / 验证报告 | 要 |
| 修订 accept | 不考虑 |
| 导出门禁 | 不要（软门禁+报告） |
| 段落重建 | 用户接受：仅命中段重建 |
