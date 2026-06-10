# 语义扫描 v5：8 类指纹体系 + 聚焦窗口检测

- **日期**: 2026-06-12
- **状态**: 已实施
- **验收基准**: deid_55 类文档

## 1. 类别定义（9 类）

| category | 含义 | 改写目标 |
|----------|------|---------|
| `project_id` | 数字编号+内控/审计 | `内控审计项目` |
| `project_name` | 具名基建/能源项目 | `新能源示范项目` / `海外风电项目` |
| `listing_code` | 证券代码 | `证券代码` |
| `listing_structure` | A+H、流通A股+H股等 | `多市场上市` |
| `data_source` | 同花顺/Wind 等平台名 | `外部数据源` |
| `deal_event` | 可唯一定位的并购/欠款/诉讼一句 | `关联交易事项` |
| `person_trait` | `[姓名_x]`+出生年/学历等 | 保留占位符，删属性 |
| `client_hint` | 客户分类线索 | 泛化分类 |
| `table_row` | 表行内可替换短语（非金额） | 地域/描述泛化 |

废弃旧类：`org_fingerprint`、`person_fingerprint`、`listing_fingerprint`（见 `semantic_categories.py` 迁移表）。

## 2. 职责边界

| 残留类型 | 负责 Worker | 不负责 |
|---------|------------|--------|
| 公司/集团/设计院简称 | `entity_discover` / `re_discover` / `entity_leak_verify` | 语义 detect |
| 项目编号、具名项目、证券代码、并购事件句 | `deep_detect` / `deep_suggest` | 程序规则主检测 |
| 金额、百分比 | 无（保留） | 任何 Worker |

## 3. 检测架构

- 输入：`build_preview_text`（实体替换后）
- 窗口：`extract_deep_candidates()` 约 400 字；无候选时 fallback 4000 字 chunk
- 配额：每窗 ≤3 条风险（`_MAX_RISKS_PER_UNIT=3`）
- Token：`DEID_DEEP_MAX_TOKENS_DETECT=256`、`DEID_DEEP_MAX_TOKENS_SUGGEST=128`
- 程序规则：默认关闭（`DEID_SEMANTIC_PROGRAM_RULES=0`），仅作 suggest 兜底

## 4. 写回

- `partition_semantic_pairs` 除 `<w:p>` 外遍历 `<w:tc>` 单元格
- 长子串（>80 字）优先最短可唯一定位子串
- `semantic_missed_samples` 按类聚合写入 `verification_json`

## 5. 完成阶段 readiness

- `_execute_deid` 仅 `merge_verification`（程序验漏 + 语义落地统计），**不**调用 Worker `post_run_verify`
- Worker 验漏仅在实体扫描阶段 `entity_leak_verify` 使用
- `entity_leak`（扫描阶段）→ 合并为待确认实体，不阻塞确认替换
- 残留 `project_name` / `listing_code` / `deal_event` → `level=standard`, `ready=false`
- 全部通过 + 语义已应用 → `level=deep`, `ready=true`

## 6. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `DEID_DEEP_WINDOW_SIZE` | 400 | 聚焦窗口字数 |
| `DEID_DEEP_MAX_TOKENS_DETECT` | 256 | detect Worker max tokens |
| `DEID_DEEP_MAX_TOKENS_SUGGEST` | 128 | suggest Worker max tokens |
| `DEID_SEMANTIC_PROGRAM_RULES` | 0 | 1=启用程序规则检测（legacy） |

## 7. 验收标准（deid_55）

- 成品无「规划设计集团」等字面机构名
- `251231…内控审计` → `内控审计项目`
- 证券代码 → `证券代码`
- 具名基建项目 → 泛化项目名
- `verification_json.readiness` 给出明确 level 与 blocker 列表

回归脚本：`python scripts/eval_deid_export.py <desensitized.docx>`
