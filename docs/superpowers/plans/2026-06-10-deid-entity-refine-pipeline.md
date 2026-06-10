# Deid 实体扫描优化环 + 语义扫描 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构脱敏主流程为 `上传→实体扫描→语义扫描→确认→完成`；实体扫描含标准→gap→反思与可选经验；语义扫描先预览后勾选；⑤ 一次性写 docx（实体+可选语义）；拆除 run 后 `verifying`。

**Architecture:** 实体优化批与语义扫描批分离；`run_worker_flow()` 复用；反思=带 gap/exp 的第 2 轮 discover+alias；语义 detect 对原文、写回仅在 `finishing`；`progress_json.wizard_step` 驱动 5 步 Stepper。

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3/Pinia, SSE scan-stream, Mac Worker relay, existing `discover_llm`/`flows.py`/`deep_candidates.py`/`deep_apply.py`

**Spec:** [`docs/superpowers/specs/2026-06-10-deid-entity-refine-pipeline-design.md`](../specs/2026-06-10-deid-entity-refine-pipeline-design.md)

**Note:** 仓库已部分实现旧 spec（`flows.py`、`alias_surface`、`standard_verify` in run、`deep/*` API、`DeidDeepReview`）。本计划以**一次性拆除**旧路径为前提，任务含删除与迁移。

---

## File map

| File | Responsibility |
|------|----------------|
| `app/deid/discovery/flow_parse.py` | 新增 `parse_gap_lines`, `parse_exp_lines` |
| `app/deid/discovery/scan_gap.py` | Worker flow `scan_gap` |
| `app/deid/discovery/scan_experience.py` | Worker flow `scan_experience` |
| `app/deid/discovery/entity_refine.py` | 批编排：standard→gap→reflect→merge；经验 prompt 注入 |
| `app/deid/discovery/experience_store.py` | job/pack 经验读写、≤5 行 FIFO |
| `app/deid/prompts.py` | `scan_gap`/`scan_experience` 默认 prompt + setting keys |
| `app/deid/service.py` | 状态机、scan 批、semantic、confirm→finishing；**删除** verifying/deep-on-done |
| `app/deid/schemas.py` | `SemanticSelectionIn`, `ExperienceRememberIn`, `ConfirmIn` 扩展 |
| `app/api/deid.py` | 新路由；废弃 `run`/`deep/scan` 旧语义 |
| `app/models_deid.py` | `experience_lines_json`, `semantic_risks_json`, `semantic_selection_json`, `reflect_round_count` |
| `app/migrate.py` | 新列 |
| `website/src/components/deid/DeidStepper.vue` | 5 步 |
| `website/src/components/deid/DeidSubStepper.vue` | 子进度（新建） |
| `website/src/components/deid/DeidEntityScanStage.vue` | 实体扫描+弹层（新建） |
| `website/src/components/deid/DeidReflectModal.vue` | 经验/再反思（新建） |
| `website/src/components/deid/DeidSemanticScanStage.vue` | 语义三态（新建） |
| `website/src/stores/deid.ts` | wizard_step、SSE snapshot、semantic API |
| `website/src/components/deid/DeidMainStage.vue` | 路由到各 stage |
| `tests/test_deid_entity_refine.py` | 实体批、gap/exp parser（新建） |
| `tests/test_deid_semantic.py` | 语义预览+finish apply（新建） |

---

### Task 1: gap/exp parsers + prompts

**Files:**
- Modify: `app/deid/discovery/flow_parse.py`
- Modify: `app/deid/prompts.py`
- Modify: `app/deid/settings_store.py`
- Test: `tests/test_deid_entity_refine.py` (create)

- [ ] **Step 1: Write failing parser tests**

```python
# tests/test_deid_entity_refine.py
from app.deid.discovery.flow_parse import parse_gap_lines, parse_exp_lines

def test_parse_gap_lines():
    text = "gap|alias_miss|规划设计集团|表头简称未纳入别名"
    items = parse_gap_lines(text)
    assert len(items) == 1
    assert items[0]["category"] == "alias_miss"
    assert items[0]["snippet"] == "规划设计集团"

def test_parse_exp_lines():
    text = "exp|表头简称需在别名阶段补全\n无"
    items = parse_exp_lines(text)
    assert items == ["表头简称需在别名阶段补全"]

def test_parse_exp_lines_skips_none():
    assert parse_exp_lines("无") == []
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest tests/test_deid_entity_refine.py -v`

- [ ] **Step 3: Implement parsers**

`parse_gap_lines`: `gap|类别|片段|说明`，类别枚举 `alias_miss|entity_miss|pattern_hint`。

`parse_exp_lines`: 每行 `exp|文本`，去重，跳过「无」。

- [ ] **Step 4: Add prompts + settings keys**

`FLOW_SCAN_GAP_KEY`, `FLOW_SCAN_EXPERIENCE_KEY`；`ensure_flow_prompts()` 种子。

- [ ] **Step 5: Run tests — expect PASS**

Run: `python -m pytest tests/test_deid_entity_refine.py -v`

---

### Task 2: scan_gap + experience_store

**Files:**
- Create: `app/deid/discovery/scan_gap.py`
- Create: `app/deid/discovery/experience_store.py`
- Test: `tests/test_deid_entity_refine.py` (append)

- [ ] **Step 1: Test experience_store roundtrip**

```python
def test_pack_experience_fifo(db, seeded_db):
    from app.deid.discovery.experience_store import append_pack_experience, load_pack_experience_lines
    pack_id = 1
    for i in range(6):
        append_pack_experience(db, pack_id, f"经验行{i}")
    lines = load_pack_experience_lines(db, pack_id)
    assert len(lines) == 5
    assert lines[0] == "经验行1"
```

- [ ] **Step 2: Implement `experience_store.py`**

`load_pack_experience_lines(db, pack_id) -> list[str]`（setting key `pack_{id}_experience`，JSON 数组，max 5）。

`append_pack_experience(db, pack_id, line)` FIFO。

`build_experience_prompt_block(job_lines, pack_lines) -> str`（≤3 job + pack 合并截断）。

- [ ] **Step 3: Implement `scan_gap.py`**

`async def run_scan_gap(sample, entities, router, db, *, job_id, on_event)` — 复用 `alias_surface` 的 chunk+实体子集策略，调用 `run_worker_flow("scan_gap", ...)`，`parse_gap_lines`。

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_deid_entity_refine.py -v`

---

### Task 3: entity_refine batch orchestrator

**Files:**
- Create: `app/deid/discovery/entity_refine.py`
- Create: `app/deid/discovery/scan_experience.py`
- Test: `tests/test_deid_entity_refine.py` (append)

- [ ] **Step 1: Test reflect prompt includes gap block**

```python
def test_build_reflect_system_prompt_includes_gap():
    from app.deid.discovery.entity_refine import build_reflect_system_prompt
    p = build_reflect_system_prompt("base", gap_lines=[{"snippet": "foo", "note": "bar"}], exp_lines=["经验1"])
    assert "foo" in p
    assert "经验1" in p
```

- [ ] **Step 2: Implement `entity_refine.py`**

```python
@dataclass
class EntityRefineResult:
    entities: list[MergedEntity]
    gaps: list[dict]
    standard_entity_count: int
    reflect_entity_count: int

async def run_standard_round(...) -> tuple[list[MergedEntity], LlmDiscoveryResult]
async def run_reflect_round(entities, gaps, exp_lines, ...) -> tuple[list[MergedEntity], LlmDiscoveryResult]
async def run_entity_refine_batch(..., *, include_standard: bool) -> EntityRefineResult
```

`include_standard=False` 时仅 `gap → reflect`（手动再反思）。

合并：`merge_entities(remembered + manual + round_entities)`，与现 scan 一致。

- [ ] **Step 3: Implement `scan_experience.py`**

单次 Worker 调用；输入 gap 摘要 JSON ≤500 字；`parse_exp_lines`；返回 `list[str]`。

- [ ] **Step 4: Unit test with mocked run_worker_flow**

Mock `run_worker_flow` 返回 gap/exp 行，断言 `run_entity_refine_batch(include_standard=True)` 调用顺序 standard→gap→reflect。

Run: `python -m pytest tests/test_deid_entity_refine.py -v`

---

### Task 4: DB columns + migrate

**Files:**
- Modify: `app/models_deid.py`
- Modify: `app/migrate.py`

- [ ] **Step 1: Add columns**

```python
experience_lines_json: Mapped[str | None] = mapped_column(Text, nullable=True)
semantic_risks_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # reuse or rename
semantic_selection_json: Mapped[str | None] = mapped_column(Text, nullable=True)
reflect_round_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
semantic_skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

- [ ] **Step 2: Add `_ensure_deid_jobs_refine_columns()` in migrate.py**

- [ ] **Step 3: Verify migrate on test DB**

Run: `python -m pytest tests/test_deid.py::test_seed_idempotent -v`

---

### Task 5: Refactor `_scan_job_impl` — entity refine batch + SSE

**Files:**
- Modify: `app/deid/service.py`
- Modify: `app/deid/scan_events.py` (if needed for new event types)
- Test: `tests/test_deid_entity_refine.py` (integration with mock)

- [ ] **Step 1: Write integration test**

Mock `run_entity_refine_batch`；调用 `scan_job`；断言 `scan_summary` 含 `reflect_round=1`；bus 收到 `entities_snapshot` 两次（通过 mock on_event 捕获）。

- [ ] **Step 2: Replace scan body after sample extract**

在线路径：

1. `phase=standard` → `run_standard_round` → emit `entities_snapshot` #1 → persist 临时实体
2. `phase=gap` → `run_scan_gap`
3. `phase=reflect` → `run_reflect_round` → merge → emit `entities_snapshot` #2 → `_persist_merged_entities`
4. emit `reflect_done` with gap_count, new_entity_count
5. `job.reflect_round_count = 1`；`progress.wizard_step = semantic`

离线：保持词库-only，跳过 gap/reflect，`wizard_step=semantic`。

- [ ] **Step 3: Remove alias_surface-only pass as separate final step**

Alias 纳入 standard/reflect 每轮末尾（或每轮内 discover 后 alias），避免三轮重复。

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_deid_entity_refine.py tests/test_deid.py::test_ceec_fixture_scan -v`

---

### Task 6: re-reflect + experience API

**Files:**
- Modify: `app/deid/service.py`
- Modify: `app/api/deid.py`
- Modify: `app/deid/schemas.py`
- Test: `tests/test_deid_entity_refine.py`

- [ ] **Step 1: Test re-reflect limit**

```python
def test_re_reflect_rejects_after_five(client, db, seeded_db, monkeypatch):
    # job.reflect_round_count=5 → POST /scan/re-reflect → 400
```

- [ ] **Step 2: Implement `re_reflect_job`**

`POST /jobs/{id}/scan/re-reflect`：`status=scanned`，`reflect_round_count < 5`，`include_standard=False` 批，SSE 可选同步返回实体列表，递增 count，再 emit `reflect_done`。

- [ ] **Step 3: Implement `generate_experience` + `remember_experience`**

`POST /jobs/{id}/scan/experience`：读 `gaps_json` 或最近 gap 缓存；Worker `scan_experience`；追加 `experience_lines_json`。

`POST /jobs/{id}/scan/experience/remember` body `{indices:[0,1]}` → `append_pack_experience`。

- [ ] **Step 4: Register routes in `api/deid.py`**

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_deid_entity_refine.py -v`

---

### Task 7: Remove run verifying + merge confirm→finishing

**Files:**
- Modify: `app/deid/service.py`
- Modify: `app/deid/discovery/standard_verify.py` (delete or gut unused exports)
- Modify: `app/api/deid.py`
- Test: `tests/test_deid.py`

- [ ] **Step 1: Simplify `_execute_deid` → `finish_job`**

删除 `run_standard_verify` 调用与 `verifying` 状态。

`finishing` 流程：

```python
result = run_deid_pipeline(path, out, entities, patterns, whitelist)
pairs = json.loads(job.semantic_selection_json or "[]")
if pairs:
    apply_semantic_pairs_to_workdir(work, pairs)  # before pack, or unpack→apply→pack
verification = result["verification"]  # program only
verification["program_only"] = True
verification["semantic"] = {...}
```

将 semantic pairs apply 并入 pipeline 或 `finish_job` 内联调用 `apply_deep_pairs` 于 workdir（**勿**先写 output 再改）。

- [ ] **Step 2: Merge `confirm_job` + `run_job`**

`confirm_job` 接受 `entity_ids`, `remember_ids`, `semantic_selection`；设置 `semantic_selection_json`；`status=finishing`；调用 `finish_job`；`status=done`。

废弃 `POST /jobs/{id}/run`（返回 410 或转发到 confirm）。

- [ ] **Step 3: Update `test_job_scan_run_flow`**

确认路径：`scan → semantic/skip → confirm → done`；无长时间 blocking verifying。

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_deid.py -v`

---

### Task 8: Semantic scan service (原文预览，不写 docx)

**Files:**
- Modify: `app/deid/service.py`
- Modify: `app/deid/discovery/deep_flows.py` (detect on sample text, not output)
- Modify: `app/api/deid.py`
- Test: `tests/test_deid_semantic.py` (create)

- [ ] **Step 1: Write semantic skip test**

```python
def test_semantic_skip_sets_flag(client, db, seeded_db):
    # scanned job → POST /semantic/skip → semantic_skipped true, wizard confirm
```

- [ ] **Step 2: Refactor `semantic_start_job`**

- 输入：`extract_sample_text(stored_path)` 非 output_path
- `status`: `scanned` → `semantic_scanning` → `semantic_review`
- 保存 `semantic_risks_json`；**不**改 `output_path`

- [ ] **Step 3: Routes**

| 路径 | 行为 |
|------|------|
| `POST /semantic/start` | detect |
| `GET /semantic/risks` | 预览 |
| `POST /semantic/suggest/{id}` | 懒加载 |
| `POST /semantic/skip` | flag + wizard_step=confirm |

删除或废弃：`POST /deep/apply` 写 output、`deep_verifying`。

- [ ] **Step 4: `semantic_review` 保存选择**

`POST /semantic/selection` body `{items:[{risk_id, enabled, rewritten}]}` → `semantic_selection_json`（可在 confirm 时一并提交）。

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_deid_semantic.py -v`

---

### Task 9: Frontend — 5-step Stepper + wizard_step

**Files:**
- Modify: `website/src/components/deid/DeidStepper.vue`
- Modify: `website/src/stores/deid.ts`

- [ ] **Step 1: Update DeidStepper**

```typescript
const steps = [
  { id: 'upload', label: '上传', short: '传' },
  { id: 'entity_scan', label: '实体扫描', short: '实' },
  { id: 'semantic', label: '语义扫描', short: '义' },
  { id: 'confirm', label: '确认', short: '认' },
  { id: 'finish', label: '完成', short: '完' },
]
```

- [ ] **Step 2: Store `wizardStep()` from `job.progress.wizard_step`**

映射：`scanning→entity_scan`，`scanned+semantic*→semantic`，`semantic_review→semantic`，`confirmed→confirm`，`finishing|done→finish`。

- [ ] **Step 3: Handle SSE `entities_snapshot` + `reflect_done`**

更新 `entities` ref；`reflect_done` 打开 modal 状态。

- [ ] **Step 4: Build**

Run: `cd website && npm run build`

---

### Task 10: Frontend — Entity scan stage + Reflect modal

**Files:**
- Create: `website/src/components/deid/DeidSubStepper.vue`
- Create: `website/src/components/deid/DeidEntityScanStage.vue`
- Create: `website/src/components/deid/DeidReflectModal.vue`
- Modify: `website/src/components/deid/DeidMainStage.vue`

- [ ] **Step 1: DeidSubStepper**

Props: `steps: {id,label}[]`, `current`, `descriptions?`。

- [ ] **Step 2: DeidEntityScanStage**

子进度 `标准识别 | 反思`；嵌入 `DeidScanLivePanel`；标准完成后显示 `DeidEntityList`（readonly）。

- [ ] **Step 3: DeidReflectModal**

按钮：生成经验、再反思（调 API）、继续（进语义扫描页）。

经验列表 checkbox 默认全选 + 记住 pack。

- [ ] **Step 4: Wire MainStage**

`wizard_step=entity_scan` 时渲染 `DeidEntityScanStage`。

- [ ] **Step 5: Build**

Run: `cd website && npm run build`

---

### Task 11: Frontend — Semantic scan stage

**Files:**
- Create: `website/src/components/deid/DeidSemanticScanStage.vue`
- Modify: `website/src/stores/deid.ts`
- Modify: `website/src/components/deid/DeidMainStage.vue`
- Delete or repurpose: `website/src/components/deid/DeidDeepReview.vue` → 迁入 SemanticScanStage

- [ ] **Step 1: Idle state**

子进度三格空心 + 说明文案；「开始语义扫描」「跳过，直接确认」。

- [ ] **Step 2: Running state**

调 `semantic/start`；子进度高亮 + logs。

- [ ] **Step 3: Review state**

Risk 表；0 条可选；「下一步：确认」。

- [ ] **Step 4: Remove done-page deep button**

删除 `DeidMainStage` 完成页「深度脱敏」入口。

- [ ] **Step 5: Build**

Run: `cd website && npm run build`

---

### Task 12: Frontend — Confirm merges run

**Files:**
- Modify: `website/src/components/deid/DeidConclusionView.vue` or confirm stage
- Modify: `website/src/stores/deid.ts`

- [ ] **Step 1: Confirm API 一次提交**

`POST /confirm` with `entity_ids`, `remember_ids`, `semantic_selection`；显示 `finishing` spinner；完成后 `wizard_step=finish`。

- [ ] **Step 2: 语义摘要**

`已选 N 条语义改写` / `未应用语义改写`。

- [ ] **Step 3: Remove separate `run` store method** or make alias.

- [ ] **Step 4: Build + manual smoke**

Run: `cd website && npm run build`

---

### Task 13: Tear down legacy code paths

**Files:**
- Modify: `app/deid/service.py` — remove `deep_scan_job` output-path logic, `deep_apply_job` pre-finish apply
- Modify: `app/api/deid.py` — remove `/deep/scan`, `/deep/apply` or 410
- Modify: `tests/test_deid_deep.py` — rewrite as `test_deid_semantic.py`
- Delete: unused imports `standard_verify` from run path

- [ ] **Step 1: Grep legacy**

Run: `rg "verifying|deep_scan_job|deep_apply|run_standard_verify|post_run_verify" app/ website/ tests/`

- [ ] **Step 2: Remove dead code**

- [ ] **Step 3: Full regression**

Run: `python -m pytest tests/test_deid.py tests/test_deid_entity_refine.py tests/test_deid_semantic.py tests/test_deid_flows.py tests/test_deid_rehydrate.py -v`

Run: `python -m pytest tests/test_api.py -v`

---

## Plan self-review (spec §14 对照)

| 验收项 | Task |
|--------|------|
| 实体扫描列表双快照+弹层 | 5, 9, 10 |
| 5 步 Stepper 顺序 | 9 |
| 语义先示后点、可跳过/0 选 | 8, 11 |
| 完成一次写 docx | 7 |
| 无 verifying 卡顿 | 7, 13 |
| Worker 离线词库+语义禁用 | 5, 8 |
| 小模型分批调用 | 2, 3 |
| 经验 Worker 可选 | 6, 10 |
| 再反思 5 次上限 | 6 |
| 一次性拆旧代码 | 7, 8, 13 |

无 TBD 占位。

---

## Suggested implementation order

1. Task 1 → 2 → 3 → 4 (foundation)
2. Task 5 → 6 (entity scan backend)
3. Task 7 → 8 (finish + semantic backend)
4. Task 9 → 10 → 11 → 12 (frontend)
5. Task 13 (cleanup + regression)

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-10-deid-entity-refine-pipeline.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — 每 Task 派生子 agent，任务间人工/自动 review

**2. Inline Execution** — 本会话按 Task 顺序执行，`executing-plans` 检查点

**Which approach?**
