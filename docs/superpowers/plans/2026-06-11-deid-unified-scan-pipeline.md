# 统一扫描管线实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把实体/语义/程序三段扫描合并为一条自动管线,状态机简化为 `draft → queued → scanning → review → confirmed → finishing → done`,删除 leak_verify,黑名单收敛到 filters.py。

**Architecture:** 新增 `run_full_scan_pipeline`(service.py)按序调用三个阶段函数,由 ScanQueue 统一调度;删除中间状态与对应 API;前端 Stepper 收为 5 步,新增三区块审阅页。

**Tech Stack:** FastAPI + SQLAlchemy / Vue 3 + Pinia。Spec: `docs/superpowers/specs/2026-06-11-deid-unified-scan-pipeline-design.md`

**回归底线:** 每个任务完成时 `python -m pytest tests/ -q` 全绿;最后 `npm run build` + eval 对比。

---

### Task 1: filters.py 黑名单收敛(纯重构,行为不变)

**Files:**
- Create: `app/deid/discovery/filters.py`
- Modify: `app/deid/discovery/merge.py`(`_GENERIC_MERGE`,18-37 行)
- Modify: `app/deid/discovery/enrich.py`(`_NOISE_TERMS`)
- Modify: `app/deid/discovery/deep_flows.py`(`_GENERIC_HEADERS` 57 行、`_BOILERPLATE_PATTERNS` 69 行)
- Modify: `app/deid/discovery/semantic_rules.py`(具体地名黑名单,~202 行)
- Test: `tests/test_deid_filters.py`

- [ ] **Step 1: 写失败测试** — `tests/test_deid_filters.py`:

```python
"""filters.py 收敛后各常量组可导入且内容非空。"""
from app.deid.discovery import filters


def test_filter_groups_exist():
    assert "有限公司" in filters.GENERIC_MERGE_TERMS
    assert filters.NOISE_TERMS
    assert filters.GENERIC_HEADERS
    assert filters.BOILERPLATE_PATTERNS
    assert filters.EVAL_SPECIFIC_TERMS  # 哈密/应城/乌兹别克等评测特判,单独成组


def test_old_modules_reference_filters():
    from app.deid.discovery import merge, enrich, deep_flows
    assert merge._GENERIC_MERGE is filters.GENERIC_MERGE_TERMS
    assert enrich._NOISE_TERMS is filters.NOISE_TERMS
    assert deep_flows._GENERIC_HEADERS is filters.GENERIC_HEADERS
```

- [ ] **Step 2: 跑测试确认失败**(`ModuleNotFoundError: filters`)
- [ ] **Step 3: 创建 filters.py** — 把四处常量原样搬入(值逐字复制,不增删),`semantic_rules.py` 里「哈密|应城|乌兹别克」等地名抽成 `EVAL_SPECIFIC_TERMS` 并加注释 `# EVAL_SPECIFIC: 针对 deid_50/55 评测文档族的补丁,可整组移除`;原模块改成 `from app.deid.discovery.filters import GENERIC_MERGE_TERMS as _GENERIC_MERGE` 形式,保持内部名不变以免改动调用点
- [ ] **Step 4: 全量测试通过后提交** — `refactor(deid): consolidate hardcoded filter lists into filters.py`

### Task 2: 删除 leak_verify 链与死代码

**Files:**
- Delete: `app/deid/discovery/entity_leak.py`、`app/deid/discovery/deep_candidates.py`、`tests/test_deid_entity_leak.py`
- Modify: `app/deid/service.py`(删 L12 import;删 `_scan_job_impl` 中 L857-901 的 leak_verify 块)
- Modify: `tests/test_deid_deep.py`(删 `extract_deep_candidates` 相关 3 个测试,L6/24/30/36)
- Modify: `app/deid/discovery/standard_verify.py`(若 `run_post_run_verify` 仅剩 entity_leak 调用方则保留——完成阶段 merge_verification 仍用,只删 entity_leak 侧入口)

- [ ] **Step 1: 删除文件与引用** — service.py 中 leak_verify 块删除后,`initial_discover` 的进度上限从 85 改为 92(直接衔接 merge)
- [ ] **Step 2: grep 确认无残余** — `grep -r "entity_leak\|deep_candidates" app/ tests/` 零命中
- [ ] **Step 3: 全量测试通过后提交** — `feat(deid): remove leak_verify LLM re-scan, residual check moves to program scan`

### Task 3: 管线整合 — run_full_scan_pipeline

**Files:**
- Modify: `app/deid/service.py`
- Test: `tests/test_deid_pipeline.py`(新建)

- [ ] **Step 1: 写失败测试**(TESTING 下 Worker 离线,验证一次 start 自动跑完三段、落 `review`、`semantic_skipped=True`、`program_scan_json` 非空):

```python
"""统一管线:一次 start 自动串完三段扫描。"""


def _upload_job(client):
    import io
    md = "中国能建股份有限公司与葛洲坝集团签署协议。\n联系电话 13812345678。"
    r = client.post(
        "/api/deid/jobs",
        files={"file": ("t.md", io.BytesIO(md.encode("utf-8")), "text/markdown")},
    )
    assert r.status_code == 200
    return r.json()["id"]


def test_full_pipeline_offline_lands_in_review(client, db):
    job_id = _upload_job(client)
    r = client.post(f"/api/deid/jobs/{job_id}/start")
    assert r.status_code == 200
    # TESTING 下队列同步执行完毕
    job = client.get(f"/api/deid/jobs/{job_id}").json()
    assert job["status"] == "review"
    assert job["semantic_skipped"] is True  # Worker 离线自动降级
    ps = client.get(f"/api/deid/jobs/{job_id}/program-scan").json()
    assert ps["run_at"] is not None  # 程序扫描自动跑过


def test_confirm_without_separate_ack(client, db):
    job_id = _upload_job(client)
    client.post(f"/api/deid/jobs/{job_id}/start")
    ents = client.get(f"/api/deid/jobs/{job_id}/entities").json()
    r = client.post(
        f"/api/deid/jobs/{job_id}/confirm",
        json={"entity_ids": [e["id"] for e in ents]},
    )
    assert r.status_code == 200  # 不再要求先 program-scan/confirm
```

- [ ] **Step 2: 实现 `run_full_scan_pipeline(db, job_id, *, worker_router, queue)`** — service.py 新函数:
  1. 调 `_scan_job_impl` 的主体(改造:去掉末尾 `status="scanned"` / `done` 事件 / `bus.close`,改为返回中间结果,进度压缩到 0-50%)
  2. semantic 阶段:Worker 在线 → 内联 `semantic_start_job` 主体(去掉状态切换,进度 50-90%);离线 → `job.semantic_skipped=True` + `scan_summary["semantic_skipped_reason"]="worker_offline"` + log 事件「Worker 离线,语义扫描已跳过」
  3. program 阶段:调 `run_program_scan` 主体(去掉状态校验与 `program_review` 切换,进度 90-100%)
  4. 终态 `job.status = "review"`,emit `done` 事件后 `bus.close`
  - `scan_job_async`(L650)改为指向新管线;`semantic_start_job`/`run_program_scan` 的独立入口保留但内部复用同一批阶段函数
- [ ] **Step 3: 状态机与门禁调整**:
  - `confirm_job` L1924 状态校验改 `("review", "confirmed")`;L1926-1927 ack 门禁删除,改为 confirm 时写 `job.program_scan_ack_at = now_beijing()`(审计戳)
  - `run_program_scan` L1800 状态校验改 `("review",)`,L1843 不再切 `program_review`,保持 `review`
  - `revert_program_scan_change` 不变;`confirm_program_scan`(L1897-1908)删除
  - `re_run_scan_job` L1016/L1030/L1091:校验改 `("review",)`,执行期间不切状态(删 `re_scanning`),完成回 `review`
  - `semantic_skip_job`(L2355)删除;`semantic_suggest_all_job` L2545 校验改 `("review", "confirmed")`,L2561 不再切 `semantic_scanning`
- [ ] **Step 4: 全量测试 + 修复受影响断言**(`test_deid.py` L35、`test_deid_program_scan.py` L108 等处的 `program-scan/confirm` 调用删除,状态断言 `scanned/semantic_review/program_review` → `review`)
- [ ] **Step 5: 提交** — `feat(deid): unified three-stage scan pipeline with review status`

### Task 4: API 收敛与存量数据迁移

**Files:**
- Modify: `app/api/deid.py`(删 L312-313 `program_scan_confirm`、L382-393 `semantic_start`/`semantic_skip`)
- Modify: `app/migrate.py`(program_scan 迁移块之后追加)
- Test: `tests/test_deid_pipeline.py` 追加

- [ ] **Step 1: 写失败测试**:

```python
def test_removed_endpoints_404(client, db):
    job_id = _upload_job(client)
    client.post(f"/api/deid/jobs/{job_id}/start")
    assert client.post(f"/api/deid/jobs/{job_id}/semantic/start").status_code == 404
    assert client.post(f"/api/deid/jobs/{job_id}/semantic/skip").status_code == 404
    assert client.post(f"/api/deid/jobs/{job_id}/program-scan/confirm").status_code == 404


def test_status_migration():
    from app.migrate import LEGACY_DEID_STATUS_MAP
    assert LEGACY_DEID_STATUS_MAP["scanned"] == "review"
    assert LEGACY_DEID_STATUS_MAP["semantic_review"] == "review"
    assert LEGACY_DEID_STATUS_MAP["program_review"] == "review"
    assert LEGACY_DEID_STATUS_MAP["semantic_scanning"] == "scanning"
    assert LEGACY_DEID_STATUS_MAP["re_scanning"] == "review"
```

- [ ] **Step 2: 实现** — api/deid.py 删 3 个端点;migrate.py 加:

```python
LEGACY_DEID_STATUS_MAP = {
    "scanned": "review",
    "semantic_review": "review",
    "program_review": "review",
    "re_scanning": "review",
    "semantic_scanning": "scanning",
}

# run_migrations 内追加:
for old, new in LEGACY_DEID_STATUS_MAP.items():
    conn.execute(
        text("UPDATE deid_jobs SET status = :new WHERE status = :old"),
        {"old": old, "new": new},
    )
```

- [ ] **Step 3: 全量测试通过后提交** — `feat(deid): remove per-stage endpoints, migrate legacy job statuses`

### Task 5: 前端 — 5 步 Stepper 与三区块审阅页

**Files:**
- Modify: `website/src/stores/deid.ts`(WizardPhase L347-360、wizardPhase() L383-410、wizardStep() L443-461)
- Create: `website/src/components/deid/DeidReviewStage.vue`
- Modify: `website/src/components/deid/DeidMainStage.vue`、`DeidStepper.vue`、`DeidLeftRail.vue`
- Delete(作为步骤页): `DeidSemanticScanStage.vue`、`DeidProgramScanStage.vue` 中的步骤壳(可复用子块抽入 ReviewStage)

- [ ] **Step 1: stores/deid.ts 收敛**:

```ts
type WizardPhase =
  | 'upload' | 'markdown-preview' | 'scan-draft'
  | 'scanning' | 'review' | 'finishing' | 'done'

function wizardPhase(): WizardPhase {
  if (showEntitiesPanel.value || showRehydratePanel.value) return 'upload'
  const job = currentJob.value as { status?: string } | null
  if (!job) return 'upload'
  const st = job.status || ''
  if (st === 'done' || st === 'archived') return 'done'
  if (st === 'finishing' || st === 'running' || st === 'confirmed') return 'finishing'
  if (st === 'review') return 'review'
  if (st === 'scanning' || st === 'queued') return 'scanning'
  if (st === 'draft') return markdownStageEntered.value ? 'scan-draft' : 'markdown-preview'
  return 'upload'
}

function wizardStep(): 'upload' | 'convert' | 'scan' | 'review' | 'finish' {
  const phase = wizardPhase()
  if (phase === 'upload') return 'upload'
  if (phase === 'markdown-preview' || phase === 'scan-draft') return 'convert'
  if (phase === 'scanning') return 'scan'
  if (phase === 'review') return 'review'
  return 'finish'
}
```

  删除 `semanticStageEntered`/`programStageEntered`/`programScanRunning`(改为 ReviewStage 内局部 `recalculating` ref)、`enterSemanticStage`;`handleScanEvent` 的 `scanSession` 三分支保留 `initial`/`rescan`(`semantic` 并入 initial 单会话)
- [ ] **Step 2: DeidReviewStage.vue** — 三区块布局(遵循 DESIGN.md):
  1. 实体表:复用 `DeidEntityTable`;增删改后顶部出现「重算程序修复」按钮 → `POST /program-scan/run`(秒级)刷新区块 3
  2. 语义风险:从 `DeidSemanticScanStage.vue` 抽风险列表+勾选+单条重生成(调 `/semantic/suggest/{id}`);`semantic_skipped` 时显示「LLM 未参与,仅词库+规则」横幅
  3. 程序修复 diff:从 `DeidProgramScanStage.vue` 抽 diff 列表+逐条撤销(调 `/program-scan/revert`)
  - 底部主按钮「确认并执行脱敏」→ 现有 confirm 流
- [ ] **Step 3: 接线** — MainStage 的 phase 路由表更新;Stepper 标签数组改 5 项;`npm run build` 通过
- [ ] **Step 4: 提交** — `feat(deid): 5-step wizard with unified review stage`

### Task 6: 端到端验证

- [ ] **Step 1:** `python -m pytest tests/ -q` 全绿
- [ ] **Step 2:** `cd website && npm run build` 通过
- [ ] **Step 3:** `python scripts/eval_deid_export.py` 跑评测文档,对比删 leak_verify 前后导出残留指标;**若回退,在结果中如实记录并停下来讨论**(备选:验漏指令并入 detect prompt,本期不实现)
- [ ] **Step 4:** 手动冒烟:上传→观察三段自动串联 SSE→审阅页改实体→重算→确认→导出
- [ ] **Step 5:** 最终提交

---

## Self-Review 已核对

- Spec §2 管线→Task 3,§3 状态机→Task 3/4,§4 API→Task 4,§5 filters→Task 1,§6 前端→Task 5,§7 验证→Task 6,leak_verify 删除→Task 2。无遗漏。
- 类型一致:`review` 状态字符串、`LEGACY_DEID_STATUS_MAP`、`run_full_scan_pipeline` 签名各任务间一致。
- 注意:Task 3 是核心,改动最大;Task 1/2 先行是为了让 Task 3 的 diff 更干净。
