# 程序扫描步骤（语义后 · 确认前）

- **日期**: 2026-06-11
- **状态**: 已实现
- **前置**: [`2026-06-10-deid-entity-refine-pipeline-design.md`](2026-06-10-deid-entity-refine-pipeline-design.md)、[`2026-06-12-deid-semantic-v5-design.md`](2026-06-12-deid-semantic-v5-design.md)

## 1. 目标

将原「完成阶段程序验漏」前移到 **语义扫描之后、确认之前**，对用户可见、可撤销，并在确认前自动补全别名/实体（C3 规则）。

| 项 | 决定 |
|----|------|
| Stepper | `上传 → 文档转换 → 实体扫描 → 语义扫描 → **程序扫描** → 确认 → 完成` |
| 行为 | 全自动写入 + diff 列表可撤销 |
| 实体策略 | 包含关系扩别名，否则新建 `source=program_scan` |
| 算法 | 干跑替换 → residual 验漏 → 反查 source.md → C3 修复 |
| Worker | 不使用 |

## 2. 状态机

```
semantic_review / scanned(+semantic_skipped)
  → POST /program-scan/run → program_review
  → POST /program-scan/confirm → program_scan_ack_at 写入 → 进入确认页
  → POST /confirm → finishing → done
```

`confirm_job` 要求 `program_scan_ack_at` 非空。

## 3. 算法

1. **干跑**：`build_preview_text(source.md, entities)`，最长优先 `ReplacementPlan`
2. **验漏**：`residual_scan_md(preview_text, entities)`，跳过占位符 span 内子串
3. **修复**：对每个 alias_residual，在 source 定位 span；C3 归属后写库
4. **再干跑**：统计 `residual_before` / `residual_after`

## 4. API

| 方法 | 路径 |
|------|------|
| POST | `/api/deid/jobs/{id}/program-scan/run` |
| GET | `/api/deid/jobs/{id}/program-scan` |
| POST | `/api/deid/jobs/{id}/program-scan/revert` |
| POST | `/api/deid/jobs/{id}/program-scan/confirm` |

## 5. 数据

`DeidJob.program_scan_json`、`DeidJob.program_scan_ack_at`
