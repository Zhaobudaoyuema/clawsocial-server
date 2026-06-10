# 脱敏主流程重构：实体扫描优化环 + 语义扫描

- **日期**: 2026-06-10
- **状态**: 待审
- **前置**: [`2026-05-31-deid-mvp-design.md`](2026-05-31-deid-mvp-design.md)、[`2026-06-08-deid-mac-worker-llm-design.md`](2026-06-08-deid-mac-worker-llm-design.md)
- **替代**: [`2026-06-09-deid-worker-flows-external-design.md`](2026-06-09-deid-worker-flows-external-design.md) 中的状态机、run 后验漏、深度含反思等章节；该文档中元数据卫生、XML 替换、小模型预算、语义 detect/suggest 仍可参照，但**流程编排以本文为准**。
- **背景**: 用户反馈 run 后 `verifying` 不可见导致「卡住」；需将反思迁入实体扫描阶段优化识别；语义脱敏改名为语义扫描并前置到确认之前；⑤ 完成时一次性写 docx。

---

## 1. 产品目标

| 项 | 决定 |
|----|------|
| 成功标准 | 出口文档可外发；外部难以识别主体公司；金额保留 |
| 主 Stepper | `上传 → 实体扫描 → 语义扫描 → 确认 → 完成` |
| 实体扫描 | **固定流程**；标准识别 + 反思（再识别）；可选经验；列表分阶段展示 |
| 语义扫描 | **可选**；子进度先展示、用户点击才执行；预览勾选，可不选任何条 |
| 完成 | **唯一一次**写 docx：实体替换 + 元数据卫生 + 用户勾选的语义 pairs |
| Worker | Mac Worker 小模型；Worker 写经验 `exp|`，程序只解析/注入/写回 |
| Worker 离线 | 实体扫描仅词库；语义扫描禁用可跳过 |

### 1.1 术语

| 用户词 | 技术含义 |
|--------|----------|
| **标准** | 第 1 轮模型识实体：`entity_discover` + `alias_surface` |
| **反思** | 在标准结果基础上 **再标准一遍**（第 2 轮 discover + alias）；非独立第三种 Flow |
| **gap** | `片段 + 已识别实体` → Worker 产 `gap|` 行，注入反思轮 prompt |
| **经验** | 反思结束后可选；Worker 产 `exp|`（**为什么会漏**，抽象原因）；非程序拼接 |
| **语义扫描** | 原「深度脱敏」；指纹 detect + suggest 预览；写回在 ⑤ 完成 |

---

## 2. 主 Stepper 与页面阶段

```
① 上传 → ② 实体扫描 → ③ 语义扫描 → ④ 确认 → ⑤ 完成
```

| 步 | id | 固定/可选 | 说明 |
|----|-----|-----------|------|
| 上传 | `upload` | 固定 | 上传 docx |
| 实体扫描 | `entity_scan` | 固定·自动 | 见 §3 |
| 语义扫描 | `semantic` | 可选·点击执行 | 见 §5；可跳过 |
| 确认 | `confirm` | 固定 | 确认实体 + 语义勾选摘要 |
| 完成 | `finish` | 固定 | 一次 pack docx，见 §6 |

③ 在 Stepper 上始终可见。② 未完成时灰显「需先完成实体扫描」。③ 跳过后显示「可补做」，用户可随时回来执行。

---

## 3. 实体扫描（固定流程）

### 3.1 一批模型调用（Batch）

首扫默认执行 **1 批完整优化**（程序提交，一条 SSE 会话）：

```
标准（discover+alias）
  → gap（scan_gap：片段+实体 → gap|）
  → 反思（第 2 轮 discover+alias，prompt 含 gap + pack/job 历史 exp）
  → [反思结束，UI 弹层；经验由用户触发，不自动]
```

**手动「再反思」**（确认页或弹层）：新一批 **仅含** `gap → 反思 → [经验?]`，**不跑标准**。用户主动再反思最多 **5 次**（不含首扫默认那 1 次反思），超出提示「建议人工补实体」。

**离线**：跳过标准/反思/经验 Worker，仅词库匹配（与现 `offline_only` 一致）。

### 3.2 UI 交互（核心）

```
[进度] 标准识别中…
  → 标准完成：立刻展示实体列表（快照 #1，只读）
  → [进度] 反思中…（默认自动 1 次）
  → 反思完成：实体列表更新（快照 #2）
  → 弹层：
      - 生成经验（可选，Worker exp|，逐条勾选记住 pack，默认全选）
      - 再反思
      - 继续（进入 ③ 或跳过至 ④）
  → scanned / 进入下一步
```

**子进度**（实体扫描区内，缩小 Stepper）：

```
标准识别 ── 反思
   ●        ○
```

经验不占自动子步骤；在弹层内可选。

SSE 事件扩展：

```json
{"type":"phase","phase":"standard","percent":40}
{"type":"entities_snapshot","entities":[...]}
{"type":"phase","phase":"reflect","percent":70}
{"type":"entities_snapshot","entities":[...]}
{"type":"reflect_done","gap_count":3,"new_entity_count":2}
```

### 3.3 Worker Flow

#### Flow: `entity_discover` + `alias_surface`（已有）

- 标准轮与反思轮各执行一次（反思轮 system 追加 gap 摘要 + 历史 exp，≤3 行）。

#### Flow: `scan_gap`（新增）

- **输入**: chunk + 块内已识别实体列表（与 alias_surface 预筛类似）
- **输出**: `gap|类型|片段|漏因说明`（每 chunk ≤3 条；无则 `无`）
- **职责**: 为反思轮提供「还缺什么」；**不是**第三种识实体 Flow

#### Flow: `scan_experience`（新增，可选）

- **触发**: 用户于弹层点击「生成经验」；无 gap 则不展示按钮
- **输入**: 本轮 gap 摘要 ≤500 字（不含公司名要求由 prompt 约束）
- **输出**: ≤3 行 `exp|抽象原因与改进要点`（Worker 生成，非模板拼接）
- **记住**: 用户逐条勾选「记住到客户包」，**默认全选**；pack 仅存抽象 `exp`，≤5 行，FIFO 淘汰
- **注入**: 仅后续批的 discover/alias system（`--- 历史经验 ---` 块）

### 3.4 经验存储

| 层级 | 字段 | 生命周期 |
|------|------|----------|
| Job | `experience_lines_json` | 本任务反思批累积；再反思追加 |
| Pack | `deid_settings.pack_{id}_experience` 或新表 | 用户勾选「记住」写入；跨任务注入 |

---

## 4. 状态机

```
draft → scanning → scanned → [semantic_pending | semantic_skipped]
     → semantic_scanning → semantic_review → confirmed → finishing → done
```

| 状态 | 含义 |
|------|------|
| `scanning` | 实体扫描批进行中（含 standard/reflect） |
| `scanned` | 实体扫描完成；`progress.wizard_step=semantic`；可进入 ③ 或跳过 |
| `semantic_pending` | ③ 待命（子进度已展示，未点击开始）；仍可用 `scanned` + `progress.subphase=semantic_idle` 表达 |
| `semantic_skipped` | 用户跳过 ③；或 `scanned` + flag |
| `semantic_scanning` | 指纹 detect 进行中 |
| `semantic_review` | risk 预览表，用户勾选 0～N 条 |
| `confirmed` | 用户确认实体 + 语义选择 |
| `finishing` | ⑤ 程序写 docx（合并原 `running`，无 Worker） |
| `done` | 可下载 |

实现可选用 `progress_json.wizard_step` + `subphase` 减少 `status` 枚举膨胀；上表为逻辑态。

**删除**（一次性拆旧代码）：`verifying`、`deep_reflecting`、`deep_verifying`、run 内 Flow3/4。

`scanning` 内 `progress.phase`：`standard` | `gap` | `reflect` | `experience`（仅用户触发时）。

---

## 5. 语义扫描（可选）

### 5.1 位置与原则

- 在 **④ 确认之前**；对**原文样本**做指纹检测与改写**预览**。
- **不写 docx**；勾选结果存 `semantic_selection_json`，⑤ 再 apply。
- 用户可不选：跳过 ③，或 0 条勾选，⑤ 仅实体替换。

### 5.2 UI 三态

**待命**（② 结束后默认展示，不调 Worker）：

子进度先显示（空心 + 说明）：

```
指纹检测 ── 改写预览 ── 应用预览
   ○          ○            ○
```

- 按钮：「开始语义扫描」「跳过，直接确认」
- Worker 离线：禁用开始 + 说明

**执行中**：子进度高亮 + SSE（`semantic_detect` 逐窗；`semantic_suggest` 懒加载）

**结束**：risk 表（勾选、可编辑改写）；「下一步：确认」在 **0 条选中** 时仍可用

### 5.3 Worker Flow（沿用 deep 命名空间，无反思）

| Flow | 说明 |
|------|------|
| `deep_candidate_extract` | 程序抽窗 |
| `deep_detect` | 逐窗 `risk|` |
| `deep_suggest` | 逐条懒加载 `suggest|` |

**不含** post_run_verify、export_readiness、再标准脱敏。

### 5.4 语义子进度 phase

`semantic_detect` → `semantic_review` → （⑤ 内 `semantic_apply`）

---

## 6. 完成（⑤ 一次性写 docx）

用户于 ④ 点击「开始脱敏」→ `finishing`：

1. `build_plan_from_job_entities` + XML 替换
2. `scrub_docprops` + `comments.xml`
3. 若 `semantic_selection_json` 非空：对**同一份** unpacked workdir 应用 semantic pairs（`deep_apply` 逻辑）
4. `pack_docx` → `output_path`
5. **程序验**（别名残留、元数据、PII 正则）→ 写入 `verification_json`，**仅警告，不硬挡下载**

无 Worker 调用。

`run_summary`：

```json
{
  "replacement_count": 120,
  "semantic_applied_count": 0,
  "semantic_skipped": true
}
```

---

## 7. verification_json（简化）

```json
{
  "passed": true,
  "program_only": true,
  "standard": {
    "confirmed_clean": true,
    "metadata_clean": true,
    "pattern_pii_clean": true
  },
  "semantic": {
    "scanned": false,
    "selected_count": 0,
    "applied_count": 0
  },
  "summary": "名称脱敏完成；未应用语义改写",
  "residuals": []
}
```

下载：程序验失败时仍可 `override_ack`（保持 MVP 软门禁）。

---

## 8. API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/jobs/{id}/start` | 上传后扫描；内含默认 1 批实体优化 |
| GET | SSE `/jobs/{id}/scan-stream` | phase、entities_snapshot、reflect_done |
| POST | `/jobs/{id}/scan/re-reflect` | 手动再反思批（无标准）；5 次上限 |
| POST | `/jobs/{id}/scan/experience` | 弹层内生成经验（Worker） |
| POST | `/jobs/{id}/scan/experience/remember` | 勾选行晋升 pack |
| POST | `/jobs/{id}/semantic/start` | 开始语义扫描（detect） |
| GET | `/jobs/{id}/semantic/risks` | 预览列表 |
| POST | `/jobs/{id}/semantic/suggest/{risk_id}` | 懒加载 suggest |
| POST | `/jobs/{id}/semantic/skip` | 跳过语义 |
| POST | `/jobs/{id}/confirm` | 确认实体 + 语义选择 → 触发 finishing |
| GET | `/jobs/{id}/export` | 中性文件名；程序验警告 |

**删除/废弃**：`POST /jobs/{id}/run` 独立阻塞验漏；`deep/scan` 在语义预览前写 output；run 内 `verifying`。

确认接口合并原 confirm + run：一次请求进入 `finishing`。

---

## 9. 前端组件

| 组件 | 职责 |
|------|------|
| `DeidStepper` | 5 步：上传/实体扫描/语义扫描/确认/完成 |
| `DeidSubStepper` | 配置驱动子进度（实体 2 步、语义 3 步） |
| `DeidEntityScanStage` | 标准→反思进度、列表双快照、反思结束弹层 |
| `DeidReflectModal` | 经验生成、再反思、继续 |
| `DeidSemanticScanStage` | 待命/执行/预览三态；先示子进度再执行 |
| `DeidConfirmStage` | 实体表 + 语义条数摘要 |
| `DeidFinishStage` | finishing 进度 + 完成下载 |

文案：

- 「扫描」→「实体扫描」
- 「深度脱敏」→「语义扫描」

---

## 10. 小模型预算

沿用 [`2026-06-09`](2026-06-09-deid-worker-flows-external-design.md) §4.4，新增：

| Flow | 单次输入 | max_tokens |
|------|----------|------------|
| `scan_gap` | chunk + 实体子集 | 256 |
| `scan_experience` | gap 摘要 ≤500 字 | 128 |
| 反思轮 discover | 同 scan + gap/exp 块 ≤3 行 | 1024 |
| `deep_detect` | ≤400 字/窗 | 256 |
| `deep_suggest` | ≤800 字 | 128 |

**禁止**：单调用大块「扫描+反思+经验」；经验非每批必产。

---

## 11. 隐私

| 阶段 | Worker 可见 |
|------|-------------|
| 实体扫描 | 原文片段 |
| 语义扫描 | 原文片段（非脱敏后文） |
| 完成 | 无 Worker |

pack 经验不得含具体公司名/片段（prompt 约束 + 程序校验长度）。

---

## 12. 迁移策略

**一次性拆除**（不双轨）：

- 移除 `run_standard_verify` 在 `run`/`_execute_deid` 的调用
- 移除 `verifying` 状态及前端等待
- 深度 API 改为语义扫描阶段 API；删除完成后才出现的「深度脱敏」入口
- 合并 `confirm` + `run` 为 `confirm → finishing`

回归：`tests/test_deid*.py` 按新状态机重写相关用例。

---

## 13. 测试策略

| 场景 | 断言 |
|------|------|
| 首扫 | SSE 含 `entities_snapshot` ×2；默认 1 次反思 |
| 再反思 | 不调用第 1 轮 discover；第 6 次提示 |
| 经验 | mock Worker 返回 `exp|`；记住 pack 后下任务 prompt 含该行 |
| 跳过语义 | `semantic_skipped`；finish 无 pairs |
| 语义 0 勾选 | `semantic_applied_count=0` |
| 语义 N 勾选 | finish 后原文片段被替换 |
| 离线 | 仅词库；语义开始 503 |
| finish | 无 Worker；程序验写入 verification |

---

## 14. 验收

- [ ] 实体扫描：标准完成后立刻见列表；反思后列表更新；弹层可选经验/再反思
- [ ] 主 Stepper 顺序：上传→实体扫描→语义扫描→确认→完成
- [ ] 语义：子进度先展示；点击才开始；可跳过或 0 条勾选
- [ ] 完成：仅一次写 docx；实体 + 可选语义
- [ ] 无 run 后 verifying 卡顿
- [ ] Worker 离线：词库 + 语义禁用
- [ ] 小模型：无超长合并调用；经验可选

---

## 15. 与 2026-06-09 spec 对照

| 2026-06-09 | 本文 |
|------------|------|
| run 后 Flow3+4 | **删除**；反思在实体扫描 |
| 深度含验漏/再标准 | **删除** |
| 深度在完成后 | **语义扫描在确认前** |
| export_readiness Worker | **删除**；程序验仅警告 |
| Flow1/2、metadata、deep detect/suggest | **保留** |
| readiness level deep/standard | 简化为 `verification.semantic.*` + 文案提示 |
