# 实体扫描重构：初次识别 + 再识别 + 全局经验



- **日期**: 2026-06-11

- **状态**: 已批准

- **替代**: `2026-06-10-deid-entity-refine-pipeline-design.md` 中的 gap/自动反思/弹层编排



---



## 1. 产品目标



| 项 | 决定 |

|----|------|

| 首扫 | 自动 1 轮：词库 + discover_llm（注入全局最近 10 条经验） |

| 再识别 | 用户触发，在已有实体基础上带 chunk 上下文补漏 |

| 经验 | 仅 LLM 再识别产生新 canonical 时可用；chunk diff → 1 条 ≤100 字；确认后全局生效 |

| 废弃 | gap、自动反思、ReflectModal、pack 经验、alias_surface — **直接删除** |



---



## 2. 流程



```

初次识别（自动）→ scanned → [用户再识别]* → [经验提取?] → 语义扫描

```



### 2.1 初次识别



词库匹配 → discover_llm（system + 全局最近 10 条经验）→ 冻结 initial_snapshot

**自动再识别（2026-06-12 增补）**：首扫成功后、进入 `scanned` 前，若 Worker 在线则自动执行 1 轮 `run_re_scan()`（`phase=re_discover_auto`）。不计入用户手动再识别 5 次上限；字段 `auto_rescan_done` 标记已执行。离线时跳过。

**实体验漏（2026-06-12 增补）**：自动再识别后，对实体替换 preview 跑 `post_run_verify`（`entity_leak.py`）。解析 `leak|entity_leak|片段|说明`，将机构字面转为 `DiscoveredEntity` 候选合并，`source=leak_verify`，UI 显示「验漏」徽章。不在此阶段自动 exclude。



### 2.2 再识别



discover_llm（re_discover prompt + 已知实体列表）→ merge



- 不限次数；无新增时软提示

- delta 相对 initial_snapshot 计算



### 2.3 经验提取



- 前置：`experience_eligible`（最近一次再识别有新 canonical）

- Worker 输入：按 chunk 的 initial vs current 实体 diff

- 输出：1 条 ≤100 字，禁止具体公司名/片段

- 确认后写入 `deid_global_experience`；确认后 `experience_eligible=false`



### 2.4 全局经验库



- 上限 20 条 FIFO

- 初次识别注入最近 10 条

- 设置页 CRUD



---



## 3. 状态机



```

draft → scanning → scanned → (re_scanning)* → scanned

```



`progress.phase`: extract | remembered | initial_discover | re_discover | merge | experience



---



## 4. API



| 方法 | 路径 |

|------|------|

| POST | `/jobs/{id}/start` |

| GET | SSE `/jobs/{id}/scan-stream` |

| POST | `/jobs/{id}/scan/re-run` |

| POST | `/jobs/{id}/scan/experience` |

| POST | `/jobs/{id}/scan/experience/confirm` |

| GET/POST/PATCH/DELETE | `/settings/global-experience` |



删除：`/scan/re-reflect`、`/scan/experience/remember`



---



## 5. UI



单页工作台：主 Stepper（上传 → 实体扫描 → 语义扫描 → 确认 → 完成）+ 实体扫描子 Stepper（两步：初次识别 → 核对和再识别）。



### 5.1 核对阶段（entity-scanned）



- **状态区**：标题「初次识别完成，请核对实体列表」；副文案说明可删除误报、手动添加或再识别；摘要为来源统计（共 N · AI x · 已记住 y · 手动 z · +Δ）

- **实体列表**：可删除；搜索 + 来源 filter +「仅新增」toggle；隐藏占位符列；长名称 ellipsis + title 全文

- **手动添加**：列表下方「+ 手动添加实体」

- **底栏**：再识别 | 经验提取（eligible 时）| 进入语义扫描

- **扫描/再识别进行中**：列表只读，显示 LivePanel



### 5.2 Worker Toast



- 显示阶段：`upload | scan-draft | scanning | entity-scanned`

- 核对阶段文案：「Worker 已恢复，可继续再识别」

- 其他阶段：「智能扫描已恢复，可使用 AI 发现实体」

- 语义扫描及之后不显示



删除：`DeidReflectModal`、标准/反思子 Stepper、alias_surface 相关进度阶段。



---



## 6. 测试



- 首扫仅 1 轮 LLM

- re-run delta / experience_eligible

- 全局经验 FIFO 20 / 注入 10

- 离线 re-run 503

