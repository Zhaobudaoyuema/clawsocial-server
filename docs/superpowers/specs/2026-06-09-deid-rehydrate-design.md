# 结论回显（Rehydrate）设计

- **日期**: 2026-06-09
- **状态**: 已批准，实施中

## 1. 问题

脱敏 docx 交给外部大模型分析后，结论中仍含 `[公司_1]`、`[姓名_2]` 等占位符。用户需在本地将结论还原为真实实体名，便于内部审阅。

## 2. 术语

| 英文 | 中文 |
|------|------|
| Rehydration | 结论回显 / 占位符还原 |
| Mapping | `deid_entity_mappings` 表：placeholder ↔ original_text |

## 3. 决策

- **输入**：占位符形式 `[前缀_N]`（与 `_assign_placeholders` 一致）
- **数据源**：任务级 mapping，非实体库
- **文件保留**：完成 8h 后删除 docx 与磁盘目录
- **映射保留**：自 `completed_at` 起 90 天
- **UI**：左侧栏「我的实体」上方独立入口「结论回显」
- **MVP**：不做 fuzzy 占位符匹配

## 4. 生命周期

```
done → (8h) → archived（文件已删，mapping 保留）→ (90d) → 删除 job + mapping
```

手动删除任务：全量删除（含 mapping），与现逻辑一致。

## 5. API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/deid/jobs/{id}/mapping` | 返回 mapping 列表 |
| POST | `/api/deid/jobs/{id}/rehydrate` | `{ text }` → 还原结果 |
| GET | `/api/deid/jobs/rehydrate-eligible` | 可回显任务列表 |

`export` 对 `archived` 任务返回 400「文件已清理」。

## 6. 安全

- mapping 与原文同级敏感
- 还原在服务端完成，mapping 不下发给浏览器（仅 POST 返回还原后文本）
- 90 天自动清理；UI 提示勿外传

## 7. 不在范围（P2）

- Fuzzy 占位符
- mapping.xlsx 导出
- 完成页内嵌回显
