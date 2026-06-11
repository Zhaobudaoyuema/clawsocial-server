# 三段扫描一体化管线（全自动串联 + 集中审阅）

- **日期**: 2026-06-11
- **状态**: 已批准设计
- **前置**: [`2026-06-11-deid-program-scan-design.md`](2026-06-11-deid-program-scan-design.md)、[`2026-06-12-deid-semantic-v5-design.md`](2026-06-12-deid-semantic-v5-design.md)、[`2026-06-11-deid-entity-rescan-design.md`](2026-06-11-deid-entity-rescan-design.md)

## 1. 目标与动机

三个痛点，三个结构性解法：

| 痛点 | 现状 | 解法 |
|------|------|------|
| 扫描慢 | 全流程 ≈ 3N+M' 次串行 LLM 调用（N=chunk 数）；leak_verify 把全文复扫一遍 | **删除 leak_verify**（省 N 次），验漏由程序扫描规则引擎承接 → 2N+M' 次 |
| 交互繁琐 | 三段扫描之间全手动衔接，最短路径 6 次点击，每段完成后停摆等用户 | **一条自动管线**跑完三段，用户只在最后**集中审阅一次**（2-3 次点击） |
| 质量补丁散落 | 硬编码黑名单散落 5+ 个文件，针对单一评测文档族过拟合 | **收敛到 `filters.py`** 统一配置表，评测特判单独标记 |

附带收益：全管线进 ScanQueue，解决语义扫描绕过队列与排队任务抢单 Worker 撞 429 的问题。

## 2. 管线架构

新增统一入口 `run_full_scan_pipeline`（service.py），由 ScanQueue 调度：

| 阶段 | 内容 | LLM 调用 | 进度 |
|------|------|---------|------|
| entity | extract → remembered → initial_discover → merge | N | 0–50% |
| semantic | detect → suggest-all（规则兜底短路不变） | N + M' | 50–90% |
| program | 干跑替换 → residual 验漏 → C3 自动修复 | 0 | 90–100% |

- **删除 `entity_leak_verify` 整条链**：`discovery/entity_leak.py` 删除。字面残留验漏由 program 阶段规则引擎承接（别名残留 + PII 正则 + 机构后缀 span，能力已在 `markdown_pipeline.residual_scan_text` / `program_scan.py`）。
- **Worker 离线降级**：entity 退化为纯词库匹配，semantic 自动 `semantic_skipped=True`，program 照跑；管线不中断，`scan_summary` 记录降级原因，审阅页显示「LLM 未参与，仅词库+规则」横幅。
- 删除死代码 `discovery/deep_candidates.py`（400 字窗口，无调用方）。

## 3. 状态机

```
旧:draft → scanning → scanned ⇄ re_scanning → semantic_scanning → semantic_review
    → program_review →（回 semantic_review）→ confirmed → finishing → done

新:draft → queued → scanning → review → confirmed → finishing → done → archived
```

- 删除状态：`scanned`、`semantic_scanning`、`semantic_review`、`program_review`、`re_scanning`。
- `migrate.py` 数据迁移：`scanned`/`semantic_review`/`program_review` → `review`；`semantic_scanning` → `scanning`。
- 审阅页内的「再识别」「程序扫描重算」不切换 job.status（进度走 SSE，前端本地标志显示 spinner）。

## 4. API

| 端点 | 变化 |
|------|------|
| `POST /jobs/{id}/start` | 不变，入队完整管线 |
| `POST /semantic/start`、`/semantic/skip` | **删除** |
| `POST /semantic/suggest/{risk_id}`、`/suggest-all` | 保留（审阅页单条重生成） |
| `POST /program-scan/run` | 保留，语义改为「重算」：改实体表后手动触发，秒级同步 |
| `POST /program-scan/revert` | 保留 |
| `POST /program-scan/confirm` | **删除**，ack 并入 `/confirm` |
| `POST /jobs/{id}/confirm` | 移除 `program_scan_ack_at` 前置校验；实体勾选 + 语义勾选不变，未撤销的程序修复即采纳 |
| `POST /scan/re-run`、`/scan/experience` | 保留，审阅页可选操作 |

数据：`program_scan_ack_at` 列保留（不删列），`confirm_job` 时写入作为审计时间戳，不再做门禁。

## 5. 黑名单收敛（filters.py）

新建 `app/deid/discovery/filters.py`，命名常量组收敛，各模块改引用，**只收敛不改行为**：

| 来源 | 内容 |
|------|------|
| `merge.py` `_GENERIC_MERGE` | 16 个通用词防误合并 |
| `enrich.py` `_NOISE_TERMS` | 噪声词 |
| `deep_flows.py` `_GENERIC_HEADERS`、`_BOILERPLATE_PATTERNS` | detect 误报过滤 |
| `semantic_rules.py` 具体地名黑名单 | **标记 EVAL_SPECIFIC 组**（哈密/应城/乌兹别克等），后续可整组移除 |
| `entity_leak.py` 占位符/股票代码豁免 | 随文件删除，有价值部分并入 filters |

## 6. 前端

- Stepper 7 步 → 5 步：`upload → convert → scan（自动三段，实时面板）→ review（三区块）→ finish`。
- 新组件 `DeidReviewStage.vue` 三区块单页：
  1. 实体表（复用 EntityTable/EntityList，改后出现「重算程序修复」按钮）
  2. 语义风险列表（从 SemanticScanStage 抽审阅部分，勾选采纳、单条重生成）
  3. 程序修复 diff（复用 ProgramScanStage diff 列表，逐条撤销）
  - 底部「确认并执行脱敏」主按钮。
- `DeidSemanticScanStage`、`DeidProgramScanStage` 作为步骤页删除（可复用子组件保留）。
- `stores/deid.ts`：wizardPhase 13 相位 → 约 7 个；SSE 单会话覆盖三阶段。

## 7. 测试与验证

- 适配新状态机：`test_deid.py`、`test_deid_flows.py`、`test_deid_program_scan.py`；删除 entity_leak 测试。
- 新增：管线自动串联端到端、Worker 离线降级、状态迁移映射。
- 回归标准：全量 pytest + `npm run build` + `scripts/eval_deid_export.py` 评测文档导出残留对比（**关键**：确认删 leak_verify 后残留指标不回退）。

## 8. 风险与回退

- **最大风险**：删 leak_verify 后「词库外未知实体」少一轮 LLM 发现。缓解：eval 验证 + 审阅页人工兜底更直观。若 eval 明显回退，备选方案是把「查字面残留」并入 semantic detect prompt（本期不实现）。
- 存量任务：迁移映射后落在 `review`，实体/风险/程序 diff 数据兼容，无需重跑。
