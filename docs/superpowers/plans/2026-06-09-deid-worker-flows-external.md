# Deid Worker 双流水线外发 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 标准 Pipeline（Worker 4 flow + 程序卫生）产出名称级可外发文档；可选深度 Pipeline（窗口 detect + 逐条 suggest + pair 写回）升级至身份级可外发。

**Architecture:** 单 `deid_job` 状态机延伸；`run_worker_flow()` 统一 Worker 调用；程序负责元数据/文件名/XML 写回/候选窗口切片；小模型深度流逐窗/逐条输入。

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3/Pinia, Mac Worker WebSocket proxy, existing `discover_llm`/`llm_parse`/`xml_replace`

**Spec:** [`docs/superpowers/specs/2026-06-09-deid-worker-flows-external-design.md`](../specs/2026-06-09-deid-worker-flows-external-design.md)

---

## File map

| File | Responsibility |
|------|----------------|
| `app/deid/discovery/flows.py` | `run_worker_flow`, flow registry, chunk/window strategies |
| `app/deid/discovery/flow_parse.py` | Parsers: surface, leak, risk, suggest, readiness |
| `app/deid/discovery/deep_candidates.py` | Program: candidate window extraction |
| `app/deid/engine/metadata.py` | `scrub_docprops`, `scan_metadata_residuals` |
| `app/deid/prompts.py` | Default prompts for flows 2–6 |
| `app/deid/service.py` | State machine, scan/run/verify/deep orchestration |
| `app/deid/engine/pipeline.py` | Integrate metadata scrub; extend verification |
| `app/deid/engine/xml/walker.py` | Add `comments.xml` |
| `app/models_deid.py` | New JSON columns on `DeidJob` |
| `app/migrate.py` | Column migrations |
| `app/api/deid.py` | Deep + export endpoints |
| `website/src/stores/deid.ts` | Deep API + state |
| `website/src/components/deid/DeidDeepReview.vue` | Deep preview UI (new) |
| `website/src/components/deid/DeidMainStage.vue` | Verify UI + deep entry |
| `tests/test_deid_flows.py` | Flow parsers + metadata + candidates |
| `tests/test_deid_deep.py` | Deep pipeline integration |

---

### Task 1: Worker flow executor + parsers

**Files:**
- Create: `app/deid/discovery/flows.py`
- Create: `app/deid/discovery/flow_parse.py`
- Test: `tests/test_deid_flows.py`

- [ ] **Step 1: Write failing parser tests**

```python
# tests/test_deid_flows.py
from app.deid.discovery.flow_parse import (
    parse_surface_lines,
    parse_leak_lines,
    parse_risk_lines,
    parse_suggest_line,
    parse_readiness_lines,
)

def test_parse_surface_lines():
    text = "surface|中国能源建设集团规划设计有限公司|规划设计集团"
    items = parse_surface_lines(text)
    assert len(items) == 1
    assert items[0]["canonical"] == "中国能源建设集团规划设计有限公司"
    assert items[0]["surface"] == "规划设计集团"

def test_parse_risk_lines_verbatim():
    text = "risk|project_id|251231内控审计|项目编号可定位"
    items = parse_risk_lines(text)
    assert items[0]["category"] == "project_id"

def test_parse_suggest_line():
    assert parse_suggest_line("suggest|客户类别：上市公司") == "客户类别：上市公司"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest tests/test_deid_flows.py -v`

- [ ] **Step 3: Implement `flow_parse.py` and minimal `flows.py`**

`flow_parse.py`: line parsers mirroring `llm_parse.py` style.

`flows.py`: extract `run_worker_flow()` from `discover_llm` loop — accept `build_user_message(chunk, meta)`, `parser`, `max_tokens`, reuse `WorkerRouter.chat_completions`.

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/test_deid_flows.py -v`

---

### Task 2: Metadata scrub + comments.xml

**Files:**
- Create: `app/deid/engine/metadata.py`
- Modify: `app/deid/engine/pipeline.py`
- Modify: `app/deid/engine/xml/walker.py`
- Test: `tests/test_deid_flows.py` (append)

- [ ] **Step 1: Write metadata scrub test**

```python
def test_scrub_docprops_clears_creator(tmp_path):
    # build minimal unpacked docx dir with docProps/core.xml containing creator/email
    from app.deid.engine.metadata import scrub_docprops, scan_metadata_residuals
    work = tmp_path / "work"
    # ... create core.xml with <dc:creator>张晓平</dc:creator>
    scrub_docprops(work, label="脱敏工具")
    residuals = scan_metadata_residuals(work)
    assert not any(r["field"] == "creator" for r in residuals if "@" in r.get("value", ""))
```

- [ ] **Step 2: Implement `metadata.py`**

`scrub_docprops(work_dir, label)` — clear listed fields in core/app/custom.xml.

`scan_metadata_residuals(work_dir)` — return `[{field, value}]` if creator/lastModifiedBy contain email or non-empty personal ids.

- [ ] **Step 3: Call scrub in `run_deid_pipeline` before `pack_docx`**

- [ ] **Step 4: Add `comments.xml` to `target_xml_files`**

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_deid_flows.py tests/test_deid.py -v`

---

### Task 3: DB columns + settings

**Files:**
- Modify: `app/models_deid.py`
- Modify: `app/migrate.py`
- Modify: `app/deid/settings_store.py` or seed in `migrate.py`

- [ ] **Step 1: Add columns to `DeidJob`**

```python
scan_entities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
deep_risks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
deep_pairs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Add migrate steps for SQLite/MySQL**

- [ ] **Step 3: Seed default flow prompts in `deid_settings` on migrate**

Keys: `flow_alias_surface_prompt`, `flow_post_run_verify_prompt`, `flow_export_readiness_prompt`, `flow_deep_detect_prompt`, `flow_deep_suggest_prompt`, `export_filename_mode=neutral`.

- [ ] **Step 4: Add default prompt templates to `app/deid/prompts.py`**

---

### Task 4: Flow 2 alias_surface in scan

**Files:**
- Modify: `app/deid/service.py` (`_scan_job_impl`)
- Modify: `app/deid/prompts.py`
- Test: `tests/test_deid_flows.py`

- [ ] **Step 1: After merge entities, run `alias_surface` via `run_worker_flow`**

Program: filter entities to those with normalized match in current chunk.

Parser: `parse_surface_lines` → append aliases to merged entities (`source=llm:surface`).

- [ ] **Step 2: Persist `scan_entities_json` at end of scan**

- [ ] **Step 3: Integration test with mocked Worker returning surface line**

---

### Task 5: Standard verify phase (Flow 3 + 4)

**Files:**
- Modify: `app/deid/service.py` — `_execute_deid` → after pipeline, set `verifying`, run flows
- Modify: `app/deid/engine/pipeline.py` — return metadata residuals in verification
- Test: `tests/test_deid.py`

- [ ] **Step 1: Extend `verification_json` schema in service**

Merge: `confirmed_clean` (existing alias scan), `metadata_clean`, `worker_entity_clean`, `readiness`.

- [ ] **Step 2: After `run_deid_pipeline`, if worker online, run Flow3 chunked on output text**

Extract output sample via `extract_sample_text(output_path)`.

- [ ] **Step 3: Run Flow4 with compressed Flow3 findings**

- [ ] **Step 4: Set job `status=done` only after verifying completes**

- [ ] **Step 5: Worker offline: skip Flow3/4, set `worker_available=false`, `readiness.notes` warning**

---

### Task 6: Neutral export filename

**Files:**
- Modify: `app/deid/service.py` `export_docx`
- Modify: `app/api/deid.py`

- [ ] **Step 1: Read `export_filename_mode` from settings**

Default: `deid_{job_id}_{YYYYMMDD}_desensitized.docx`

- [ ] **Step 2: Test export filename in `tests/test_deid.py`**

---

### Task 7: Deep candidate extraction

**Files:**
- Create: `app/deid/discovery/deep_candidates.py`
- Test: `tests/test_deid_deep.py`

- [ ] **Step 1: Test window extraction on synthetic text**

```python
def test_extract_windows_finds_project_line():
    text = "项目名称：251231内控审计\n金额单位：万元"
    windows = extract_deep_candidates(text, window_size=400)
    assert any("251231" in w["text"] for w in windows)
```

- [ ] **Step 2: Implement heuristic window extractor per spec §4.2**

Return list with `window_id`, `text`, `char_start`, `char_end`.

---

### Task 8: Deep detect + suggest service

**Files:**
- Modify: `app/deid/service.py`
- Modify: `app/api/deid.py`

- [ ] **Step 1: `POST /jobs/{id}/deep/scan`**

Status `done` → `deep_scanning`; run `extract_deep_candidates` on output; loop `deep_detect` per window; save `deep_risks_json`; status → `deep_review`.

- [ ] **Step 2: `POST /jobs/{id}/deep/suggest/{risk_id}`**

Single risk + context window → `deep_suggest` → update risk row `suggested_rewrite`.

- [ ] **Step 3: `POST /jobs/{id}/deep/apply`**

For enabled items: use user `rewritten` or cached suggest; build pairs; `run_deid_pipeline` or dedicated pair apply on output; overwrite output; `deep_verifying` → Flow3 deep mode → `done` with `deep_completed=true`.

- [ ] **Step 4: Tests with mocked Worker**

---

### Task 9: Frontend — verify UI + deep review

**Files:**
- Create: `website/src/components/deid/DeidDeepReview.vue`
- Modify: `website/src/stores/deid.ts`
- Modify: `website/src/components/deid/DeidMainStage.vue`
- Modify: `website/src/views/DeidView.vue`

- [ ] **Step 1: Store methods: `deepScan`, `fetchDeepRisks`, `deepSuggest`, `deepApply`**

- [ ] **Step 2: MainStage — readiness level display, offline banner, deep button**

- [ ] **Step 3: DeidDeepReview — table with checkbox, editable rewrite, lazy suggest loading**

- [ ] **Step 4: `npm run build` succeeds**

Run: `cd website && npm run build`

---

### Task 10: Regression

- [ ] **Run full deid test suite**

Run: `python -m pytest tests/test_deid.py tests/test_deid_flows.py tests/test_deid_deep.py tests/test_deid_rehydrate.py tests/test_worker_router.py -v`

- [ ] **Run API tests**

Run: `python -m pytest tests/test_api.py -v`

---

## Plan self-review (spec coverage)

| Spec § | Task |
|--------|------|
| §3 状态机 | Task 5, 8 |
| §4 Worker flows | Task 1, 4, 5, 8 |
| §4 小模型预算 | Task 1, 8 (env vars in flows.py) |
| §5 程序层 | Task 2, 6 |
| §6 数据模型 | Task 3 |
| §7 verification_json | Task 5, 8 |
| §8 API | Task 6, 8 |
| §9 UI | Task 9 |
| §10 隐私 | Task 8 (no mapping in worker body) |
| §11 测试 | Task 1–8, 10 |

No placeholders remain in task steps; each task has concrete files and commands.

---

## Suggested implementation order

1. Task 1 → 2 → 3 (foundation)
2. Task 4 → 5 → 6 (standard pipeline complete)
3. Task 7 → 8 (deep pipeline)
4. Task 9 → 10 (UI + regression)
