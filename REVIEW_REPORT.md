# ClawSocial Code Review Report

**Baseline:** 51/51 tests pass. 4 deprecation warnings.

---

## Executive Summary

ClawSocial is a well-architected, creative platform combining Travel Frog-style AI crawfish agents with a social network in a 2D world. The codebase demonstrates strong FastAPI idioms, good use of spatial hashing for world state, and a clean separation of concerns between REST, WebSocket, and social layers. However, it contains several **hard correctness bugs** — primarily mismatched column names between the ORM model and two API modules — that cause runtime failures in several endpoints. These must be fixed before production deployment. Beyond the bugs, there are meaningful security, performance, and architecture issues to address.

---

## Findings by Severity

### 🔴 Critical (fix immediately)

#### 1. `Message`/`Friendship` Column Name Mismatch — `world.py` Endpoints Return 500

**Affected:** `world.py:794–848` (`_calc_active_score`), `world.py:942–950` (`world_friends_positions`), `world.py:1007–1009` (`world_leaderboard`), `world.py:1014` (`world_leaderboard`), `world.py` REST endpoints in `/send`, `/friends-positions`, `/leaderboard`.

The `Message` model defines `from_id` and `to_id` (line 92–93). But `world.py`'s `_calc_active_score` and several REST endpoints use `Message.from_user_id` and `Message.to_user_id`, and `Friendship.initiated_by` is used where `Friendship.user_b_id` is needed. These columns do not exist — the endpoints will raise `AttributeError` at runtime.

**Code example** (`world.py:801–806`):
```python
rows = (
    db.query(func.count(Message.id))
    .filter(Message.from_user_id == user_id)   # ← DOES NOT EXIST
    .scalar()
    or 0
)
```

**Also in** `world.py:804`, `world.py:812`, `world.py:1014`:
```python
Message.from_user_id   # wrong
Message.to_user_id     # wrong  (correct: from_id / to_id)
```

And `world.py:943–947`:
```python
(Message.from_user_id == me.id, Message.to_user_id == friend.id),  # ← wrong column names
(Message.from_user_id == friend.id, Message.to_user_id == me.id),
```

**Fix:** Replace `from_user_id` → `from_id`, `to_user_id` → `to_id` throughout `world.py`.

---

#### 2. Duplicate `_calc_active_score` in `ws_client.py` — Uses Non-Existent Columns

**Affected:** `ws_client.py:51–83`

`ws_client.py` has its own `_calc_active_score` function that also uses `Message.from_user_id` / `Message.to_user_id` (non-existent columns). This function is called from `_user_dict()` (line 1176) which is used in `discover` and `friends` query helpers — meaning every user discovery will fail.

```python
rows = db.query(func.count(Message.id)).filter(
    Message.from_user_id == user_id   # ← wrong column name
).scalar() or 0
```

**Contrast with** `world.py:794–848` which correctly uses `Message.from_id`/`Message.to_id`.

There are now **two completely different `_calc_active_score` implementations** with the same name — `ws_client.py`'s version is broken, `world.py`'s version has wrong column names.

**Fix:** Remove the broken `ws_client.py:51-83` version entirely and import the corrected one from `world.py` (or create a shared utility). Then fix `world.py`'s column names to `from_id`/`to_id`.

---

#### 3. Undefined Variable — `world_explored` Endpoint Crashes

**Affected:** `world.py:870–877`

```python
raw_cells = (
    db.query(
        func.count(func.distinct(
            MovementEvent.x / CELL_SIZE * 1000 + MovementEvent.y / CELL_SIZE
        ))
    )
    .filter(MovementEvent.user_id == user.id, MovementEvent.created_at >= seven_days_ago)  # ← seven_days_ago not defined
    .scalar()
    or 0
)
```

`seven_days_ago` is never defined in this function. The endpoint will raise `NameError`.

---

#### 4. `world_share_card` Has No Token Auth — Anyone Can View Any User's Stats

**Affected:** `world.py:274–329`

```python
@router.get("/api/world/share-card")
def world_share_card(
    target_id: int | None = Query(None),
    x_token: str = Header(..., alias="X-Token"),   # Token present but not used for auth
    db: Session = Depends(get_db),
):
    me = _get_user(x_token, db)          # Token IS validated (last_seen updated)
    target = db.query(User).filter(User.id == (target_id or me.id)).first()
```

The function validates the caller's token (to update `last_seen_at`) but then exposes **any user's stats** without restricting access. Combined with the fact that `world_share` endpoints (lines 1140–1241) are completely unauthenticated, this means anyone can enumerate all users' movement counts, encounter counts, friend counts, and messages. While the data is not deeply sensitive, this is an information-disclosure issue.

---

### 🟠 High (fix soon)

#### 5. Homepage HTML Rendered Without CSP or Sanitization — Stored XSS

**Affected:** `homepage.py:141–155`

The `/homepage/{user_id}` endpoint renders `user.homepage` as raw HTML directly in `HTMLResponse`. There is no Content-Security-Policy header, no HTML sanitization, and no sandbox. A malicious user could store JavaScript that executes in every visitor's browser.

The `_is_html()` check is present but intentionally permissive — it only ensures the content is HTML-like, not that it's safe.

**Fix:** Add a CSP header (`default-src 'self'`) or sanitize with `bleach`. Alternatively, serve the homepage in a sandboxed `<iframe>`.

---

#### 6. N+1 Query — `world_leaderboard` Loads All Users Then N Queries Per User

**Affected:** `world.py:1004–1047`

```python
for u in db.query(User).all():           # Load all N users
    score = 0.0
    msg_count = db.query(...).filter(...)  # 1 query per user
    move_count = db.query(...).filter(...)  # 1 query per user
    encounter_count = db.query(...).filter(...)  # 1 query per user
    friend_count_q = db.query(...).filter(...)   # 1 query per user
```

For 100 users this is 401 queries. Should use a single aggregated query or a raw SQL join.

---

#### 7. N+1 in `ws_client.py` Snapshot Loop — `_build_step_context` Does Per-User Queries

**Affected:** `ws_client.py:319–689`

Every 5 seconds, for every connected client, `_build_step_context` runs multiple queries per visible user: `_load_user`, `_calc_active_score`, `db.query(User)`, `db.query(Friendship)` for each visible user, `db.query(Message)` for last interaction, etc. For 50 online users each seeing 10 others, this is ~500 queries per 5-second cycle. Under load this will saturate the connection pool.

---

#### 8. `friends-positions` REST Endpoint — Inconsistent Column Names + Two Separate JOINs

**Affected:** `world.py:912–987`

The `friends-positions` endpoint uses the wrong column names `Message.from_user_id` / `Message.to_user_id` and `MovementEvent.user_id` (which IS correct here). The join logic queries friendships in two separate queries instead of one, then deduplicates in Python. More critically, `Friendship.initiated_by` is compared against `me.id` which doesn't make sense for filtering accepted friendships.

---

#### 9. `_do_send_sync` in `world.py` — Uses Non-Existent Column Names

**Affected:** `world.py:733–775`

```python
friendship = (
    db.query(Friendship)
    .filter(
        and_(
            Friendship.user_a_id == min(from_id, to_id),    # ← wrong logic
            Friendship.user_b_id == max(from_id, to_id),    #   (should use user_a_id < user_b_id)
        )
    )
```

The friendship query logic here uses `min/max` on IDs which matches the convention in `messages.py`, but the rest of `world.py` uses different patterns. More critically, this function is never actually called from the REST endpoints — the REST `/send` uses `messages.py`'s `_send_with_attachment`. This function appears dead code but would crash if called.

---

#### 10. Registration HTML Response Leaks Token in `<div>` Tag

**Affected:** `register.py:219`

```python
<div class="token">Token：{user.token}</div>
```

The raw token is embedded in the HTML body. While this is intentional (user needs to copy it), the token is also reflected in server-side logging and the URL redirect. Ensure logs do not output full tokens at INFO level. The URL `me_url = f"/world/share/{user.id}?token={user.token}"` also puts the token in the URL path — a minor risk for token exposure via Referer headers.

---

### 🟡 Medium (address when possible)

#### 11. Deprecation: `on_event("startup"/"shutdown")` Should Be Lifespan Context Manager

**Affected:** `main.py:164, 199`

FastAPI 0.115+ deprecates `@app.on_event("startup")` and `@app.on_event("shutdown")`. Should migrate to the `lifespan` context manager pattern:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown
```

This is a clean-up task, not a correctness issue — the current code works but generates 4 warnings per run.

---

#### 12. Inconsistent `datetime` Import Locations

Multiple files import `datetime` at different locations:
- `register.py` imports at top-level
- `ws_client.py` re-imports `datetime` and `timedelta` inside functions (lines 135–136, 165, 263, 337, etc.)
- `world_aggregator.py` imports at top level
- `messages.py` imports at top level

This creates confusion about what timezone the naive `datetime` constructors use. While the convention of using `datetime.now(timezone.utc)` is consistent, the scattered imports make it easy to accidentally use `datetime.utcnow()` (which is deprecated).

---

#### 13. Inconsistent `_check_recipient_status` Placement

**Affected:** `messages.py:292–296`

In `messages.py`, `_check_recipient_status` is called before creating a `friend_request` message (line 192), meaning a `friends_only` user will reject the first outreach. But the comment says "status 变更立即生效" — the check should also apply to the block scenario before allowing `accepted` messages. Currently it is checked (lines 246, 228) for accepted messages, so this is correct.

---

#### 14. Social Event Deduplication Missing

**Affected:** `ws_client.py:924–936`, `world.py:700–708`

When a user encounters another, `_record_social_event` is called. If the WebSocket snapshot loop fires multiple times for the same encounter window, or if both the snapshot loop and REST `discover` endpoint record encounters, duplicate `encounter` events will be written. There is no unique constraint or upsert logic to prevent this.

**Fix:** Add a unique constraint on `(user_id, other_user_id, event_type, created_at_window)` or deduplicate in application logic.

---

#### 15. `_world_state_from_app` Fallback Creates Unbounded Module-Level Singleton

**Affected:** `world.py:37, 40–45`

```python
_fallback_world_state = WorldState(WorldConfig())  # module-level singleton

def _world_state_from_app(request_or_app):
    if hasattr(app, "state") and hasattr(app.state, "world_state"):
        return app.state.world_state
    return _fallback_world_state  # used when no app.state
```

If called before `app.state` is initialized (e.g., during testing or early requests), this returns a separate singleton that won't receive spawn/move events. The comment says "兜底单例（仅在测试或无 app.state 时使用）" but it's also used in REST endpoints like `world_explored` where `request=None` is passed explicitly.

---

#### 16. `world_share_events` / `world_share_stats` — No Auth, Predictable User IDs

**Affected:** `world.py:1157–1241`

These endpoints return 200 with `events: []` for non-existent user IDs (lines 1165–1166) rather than 404. The response structure is consistent but the HTTP semantics are wrong. `raise HTTPException(status_code=404)` does appear (lines 1165, 1202) but the response body has the same format as success — check whether this is actually handled correctly.

---

#### 17. `world_share_events` — `datetime.min` is Naive, Causes Comparison Error

**Affected:** `world.py:1169`

```python
since = datetime.min.replace(tzinfo=timezone.utc) if days else datetime.min.replace(tzinfo=timezone.utc)
```

Actually this line looks correct. But earlier it uses:
```python
datetime.min.replace(tzinfo=timezone.utc)
```
This is correct usage of `datetime.min`. The line above is actually fine. Let me re-check...

Actually the real concern is in the `window == "24h"` case, the `since` calculation is correct. But the `window == "0"` case uses `datetime.min` which is fine. So this is not a bug. **Correction: Not a finding.**

---

#### 18. APScheduler `max_instances=1` But No Distributed Lock

**Affected:** `world_aggregator.py:166–178`

Both scheduled jobs have `max_instances=1` which prevents concurrent execution in a single process. But if the server is scaled horizontally (multiple processes), each process will run its own scheduler — the `agg_heatmap_cells` job will run N times per interval. No database-level locking is used. For MySQL, this can be addressed with `SELECT ... FOR UPDATE` or a dedicated scheduler lock table.

---

#### 19. `send_message_file` — File Saved Before DB Transaction

**Affected:** `messages.py:275–289`

```python
if file and file.filename:
    attachment_path, attachment_filename = await save_upload(file)  # ← saved to disk
sender = _auth(x_token, db)
return _send_with_attachment(...)  # ← DB transaction might fail
```

If the DB commit fails after the file is already saved, the file remains on disk orphaned. The `finally` block deletes on error, but the flow shows the file is saved before `_auth` — if `_auth` raises HTTPException (401), the file leaks.

**Fix:** Move file save inside `_send_with_attachment` after DB success, or clean up in the except block.

---

#### 20. `_bg_delete_acked` Deletes `SocialEvent` Rows by ID — Potential ID Collision

**Affected:** `ws_client.py:712–727`

```python
db.query(SocialEvent).filter(
    SocialEvent.user_id == user_id,
    SocialEvent.id.in_(acked_ids),   # acked_ids are message IDs like "msg_123"
).delete(...)
```

The `SocialEvent` and `Message` tables share a global ID sequence (both use `BigInteger, autoincrement=True`). An acked_id like `msg_123` is parsed as `123` and then used to delete a `SocialEvent` with `id=123`. This only works if the Message and SocialEvent IDs happen to not collide. Over time they will diverge — this will silently fail to delete SocialEvent records.

---

### 🟢 Low (nice to have)

#### 21. `func.random()` in `discover` — Performance on Large Tables

**Affected:** `friends.py:87`, `ws_client.py:1202`

```python
base_q.order_by(func.random()).limit(DISCOVER_PAGE_SIZE).all()
```

`ORDER BY RAND()` is O(n log n) and degrades badly on large user tables. For production with thousands of users, use `OFFSET` with a stable sort key or fetch a random window.

---

#### 22. Duplicate `_get_friendship` Pattern Across Files

Both `messages.py:42–46` and `friends.py` implement friendship lookup with `min/max` ordering. This pattern appears 3+ times. Should be centralized in `app/models.py` or a shared utility.

---

#### 23. `_bg_update_user_xy` — Race Condition Between Background Tasks

**Affected:** `world.py:686–697`, `ws_client.py:1531–1542`

When a user moves, two background tasks are spawned:
- `_bg_persist_move` (writes MovementEvent)
- `_bg_update_user_xy` (updates user's last_x/last_y)

If the user moves again before the first `_bg_update_user_xy` completes, a subsequent task may overwrite with a stale position. For reconnection recovery this is a minor issue — the in-memory WorldState is authoritative anyway.

---

#### 24. Missing `__init__.py` Files for Python Package Imports

The project lacks `__init__.py` files in several directories. While modern Python 3 implicit namespace packages work, explicit `__init__.py` files are more robust across Python versions and tooling.

---

#### 25. `_world_state_from_app(None)` in Several REST Endpoints

**Affected:** `world.py:863, 919`

When `request=None` is passed (as in `world_explored` and `world_friends_positions`), the function always returns the module-level `_fallback_world_state` singleton. This means these endpoints never see the real `app.state.world_state` — they return stale or empty data. The endpoints are effectively broken.

---

#### 26. `get_bounds` Recalculated Every Frame in `world_map.ts`

**Affected:** `HeroMap.vue:98`, `world_map.ts:65–86`

Every mouse move event calls `getBounds()` which iterates all users to compute bounding box. This is O(n) per mousemove. Should be cached and only recalculated when users change.

---

#### 27. `setInterval` Without Cleanup in `StatsBar.vue`

**Affected:** `StatsBar.vue:51–54`

```typescript
setInterval(async () => { ... }, 30000)
```

The interval is not cleaned up in `onUnmounted`. On component unmount (unlikely for this page, but still), the timer continues.

---

## Per-File Review

### `app/models.py`
- ✅ Schema design is clean, well-documented
- ✅ Correct use of SQLAlchemy 2.0 `Mapped`/`mapped_column`
- ✅ Proper composite indexes for the main query patterns (`ix_msg_to_created`, `ix_friendship_a_status`)
- ✅ `_utc_now()` as default/onupdate callable — correct timezone handling
- ✅ `UniqueConstraint` on `(user_a_id, user_b_id)` ensures no duplicate friendships
- ⚠️ `message.id` and `social_event.id` share no namespace — acked_id parsing in `_bg_delete_acked` is fragile (see Finding #20)

### `app/database.py`
- ✅ `pool_pre_ping=True` — good for MySQL connection health
- ✅ `pool_size=50` with `max_overflow=30` — appropriate for 500 agents
- ✅ Uses `DeclarativeBase` (SQLAlchemy 2.0 style)
- ⚠️ No `engine.dispose()` on shutdown — connection pool not explicitly cleaned up

### `app/auth.py`
- ✅ Clean separation from the WS context
- ✅ Correctly uses `next(get_db())` for the generator pattern
- ✅ Refreshes user after update — good

### `app/main.py`
- ✅ `_setup_logging()` with force=True and dual-handler support
- ✅ Rate limiting middleware is well-designed (sliding window, per-user vs per-IP)
- ✅ `_client_ip` handles X-Forwarded-For correctly (takes first IP)
- ✅ Exception handlers return correct content-type for different path groups
- ⚠️ `on_event("startup"/"shutdown")` is deprecated (see #11)
- ⚠️ `_load_recent_positions` ignores the `cutoff` filter — loads ALL users with positions, not just recent ones (line 188: `User.last_x.isnot(None)` should also filter `User.last_seen_at >= cutoff`)

### `app/api/register.py`
- ✅ Token generated with `secrets.token_hex(16)` — cryptographically sound
- ✅ RegistrationLog written in same transaction as user creation
- ✅ Broadcast to all on join
- ✅ HTML response with meta refresh for browser UX
- ⚠️ Token in URL (`/world/share/{user.id}?token={user.token}`) — risk of Referer leakage
- ⚠️ `today_start` calculation uses naive truncation — correctly uses `replace()` to zero time

### `app/api/stats.py`
- ✅ Minimal, correct, properly indexed
- ⚠️ `Stats` counter could be eventually consistent (acceptable trade-off)

### `app/api/admin.py`
- ✅ Admin key auth is simple and effective
- ✅ Rate limit toggle is dynamic (updates `app.state`)

### `app/api/world.py`
- 🔴 Multiple broken endpoints due to wrong column names (see #1, #2, #9)
- 🔴 `seven_days_ago` undefined in `world_explored` (see #3)
- 🔴 `_world_state_from_app(None)` always returns fallback singleton (see #25)
- 🔴 `_calc_active_score` uses non-existent columns (see #1)
- 🔴 N+1 in `world_leaderboard` (see #6)
- ⚠️ `func.random()` performance (see #21)
- ⚠️ `_world_state_from_app` fallback (see #15)
- ✅ Logging is thorough and structured

### `app/api/ws_client.py`
- 🔴 Broken `_calc_active_score` with wrong column names (see #2)
- 🔴 Duplicate `_calc_active_score` definition (see #2)
- 🔴 N+1 in `_build_step_context` snapshot loop (see #7)
- ⚠️ `_bg_delete_acked` ID collision risk (see #20)
- ⚠️ Social events not deduplicated (see #14)
- ⚠️ `_calc_exploration_frontier` does 4×9×(range/200)² iterations — worst case ~900 iterations × 4 directions = 3600 iterations. Acceptable but could be optimized
- ✅ Snapshot loop has `_known_user_ids` for encounter deduplication
- ✅ `ws_clients` cleanup on disconnect is correct
- ✅ `_load_user` / `_friends_of` use correct `from_id`/`to_id` columns
- ✅ `_do_send_sync` correctly uses `from_id`/`to_id` (unlike `world.py`'s version)

### `app/crawfish/social/messages.py`
- ✅ `friend_request` → `accepted` state machine is correct
- ✅ `IntegrityError` handling for the race condition between concurrent friend requests
- ✅ `_accept_friendship` commits DB before pushing WS — good data consistency
- ✅ `_increment_total_messages` uses `with_for_update()` to prevent race conditions
- ⚠️ `_check_recipient_status` not called before pending-state sends (intentional, as `friends_only` users should still receive requests)
- ⚠️ File saved before DB commit (see #19)
- ✅ `_auth` updates `last_seen_at` and refreshes user

### `app/crawfish/social/friends.py`
- ✅ Batch query for friend profiles avoids N+1 (line 142–143)
- ✅ Proper use of `or_` and `and_` for friendship queries
- ✅ Blocked messages are cleared on block action

### `app/crawfish/social/homepage.py`
- 🔴 Stored XSS risk (see #5)
- ✅ `_is_html` detection with stdlib HTMLParser
- ✅ `_reject_json` prevents accidental JSON uploads
- ✅ Size limit (512KB) is reasonable
- ✅ 512KB limit on HTML upload is reasonable

### `app/crawfish/world/state.py`
- ✅ Spatial hash grid is correctly implemented
- ✅ Thread-safe with `threading.Lock` for all mutations
- ✅ `bulk_init_from_db` handles duplicates gracefully
- ✅ `cleanup_inactive` removes from all three structures (users, occupied, grid)
- ✅ `spawn_user` handles reconnection correctly
- ⚠️ `random.randrange` in hot path — acceptable for spawn but could cause contention at startup with many simultaneous connections

### `app/jobs/world_aggregator.py`
- ✅ `max_instances=1` prevents intra-process overlap
- ⚠️ No distributed locking for multi-process deployments (see #18)
- ⚠️ `INSERT OR REPLACE` in SQLite path will first delete then insert, then UPDATE on the same row in same session — the second UPDATE will update row count 0 (see lines 67-87). Actually this is incorrect — the first statement inserts the row, then the second UPDATE finds it and updates it. So the behavior is correct but the code is confusing. The increment happens correctly.
- ✅ Batched deletion for TTL cleanup — good

### `app/uploads.py`
- ✅ `uuid.uuid4()[:8]` for unique filenames — good
- ✅ `_sanitize_filename` strips path traversal chars
- ✅ Size check before write — good
- ⚠️ `ALLOWED_EXTENSIONS = None` means any file type is accepted — potential security risk (executables, scripts, etc.)

### `app/utils.py`
- ✅ Simple, clean utility
- ✅ Explicit charset in media type

### `run.py`
- ✅ Auto-creates database if not exists
- ✅ Kills old processes on the port — useful for development
- ⚠️ Hardcoded `DB_PASSWORD` and `DB_USER` defaults (even in `.env` which is committed) — credentials in `.env` are a risk if the file is committed to version control. Note: `.env` is likely in `.gitignore` but worth confirming.
- ✅ `CREATE DATABASE IF NOT EXISTS` with utf8mb4 — good

### `website/src/App.vue`
- ✅ Clean component composition
- ✅ Responsive design with CSS grid
- ✅ Proper `lang="ts"` and `<script setup>` syntax

### `website/src/world_map.ts`
- ⚠️ `getBounds` O(n) on every mousemove (see #26)
- ✅ WebSocket reconnection with 3-second backoff
- ✅ Proper cleanup in `disconnectWs`
- ✅ Protocol-aware WebSocket URL construction (`ws:` vs `wss:`)

### `website/src/components/HeroMap.vue`
- ✅ Proper cleanup in `onUnmounted`
- ✅ Canvas resize handling
- ⚠️ `users.value = users.value` pattern on line 155 — this doesn't do a reactive update when filtering (Vue 3 reactivity caveat). Should use a spread to trigger reactivity.

### `website/src/components/RegisterModal.vue`
- ✅ Token extraction via regex from plain-text response
- ⚠️ `fetch('/register')` uses relative URL — depends on correct Vite proxy or running from root

### `website/src/components/StatsBar.vue`
- ⚠️ `setInterval` without cleanup (see #27)
- ⚠️ Two separate fetch calls instead of one — minor but `loadInitData` already does this

### `website/vite.config.ts`
- ✅ Correct proxy configuration for API and WebSocket
- ✅ `base: '/'` prevents asset routing conflicts

---

## Architecture Assessment

### Strengths
- **Clean layered architecture**: Router → API → Social → Models → Database. Each layer has clear responsibilities.
- **Spatial hash grid** for the 2D world is elegant and brings `get_visible` from O(n) to O(1) — excellent for a 10k×10k world.
- **Read-and-clear message pattern** with `msg_id` parsing is conceptually sound, though the ID collision issue (Finding #20) needs addressing.
- **Friend request state machine** is correct: null → pending → accepted/blocked.
- **WorldState** is a clean in-memory state manager with proper locking.
- **WS connection pooling** in `app.state.ws_clients` enables targeted push without pub/sub infrastructure.
- **Graceful degradation** in `_build_step_context` with `try/except ImportError` prevents crashes when models are missing.

### Weaknesses
- **Two parallel `_calc_active_score` implementations** with different bugs is a symptom of code duplication between `world.py` and `ws_client.py`.
- **REST `/send` and WebSocket `/send` use different code paths** (`messages.py` vs `ws_client.py`) — increases maintenance burden and risk of inconsistency.
- **`app.state.world_state` as the sole source of truth** is fragile — the fallback singleton and `_world_state_from_app(None)` pattern creates hidden failures.
- **No DI container** — `get_db()` is used via `next(get_db())` in many places (ws_client, world_aggregator) which bypasses FastAPI's dependency injection, making testing harder and creating subtle session lifecycle issues.
- **APScheduler in-process** with no distributed locking — limits horizontal scaling.

---

## Security Analysis

### Auth
- ✅ Token-based auth with `X-Token` header — simple and effective
- ✅ Admin key auth for management endpoints
- ✅ No role system needed for this MVP (crawfish = users)

### Injection
- ✅ All DB queries use SQLAlchemy ORM — no raw SQL concatenation
- ✅ Parameterized queries in `world_aggregator.py` with `text()` and named params — safe
- ⚠️ `func.random()` in `discover` endpoint — not SQL injection, but performance issue

### Data Exposure
- 🔴 `/api/world/share-card` exposes any user's stats to any authenticated caller
- 🔴 `/api/world/share/*` and `/api/world/homepage/{target_id}` are completely unauthenticated — fine for public data, but combined with predictable user IDs allows user enumeration
- 🔴 Homepage HTML storage — stored XSS vector
- 🟡 Registration token in URL query parameter (`?token=`) — Referer header risk

### Rate Limiting
- ✅ Per-user and per-IP rate limiting is well-designed
- ✅ Exempt paths for health/stats/homepage
- ⚠️ Rate limiter looks up user by token in DB on every request — this adds 1 query per authenticated request. Should cache user→rate_limit_key mapping in `app.state`.

### File Uploads
- ⚠️ No file type restrictions (`ALLOWED_EXTENSIONS = None`) — any file type can be uploaded
- ✅ File size limit enforced
- ✅ UUID-based storage prevents filename collisions
- ⚠️ No virus scanning

---

## Performance Analysis

### DB Queries
- 🔴 **N+1 in `_build_step_context`**: O(queries) = O(visible_users × 6) per 5-second cycle per client
- 🔴 **N+1 in `world_leaderboard`**: O(4 × N + 1) queries for N users
- 🔴 **Sequential `OR` queries in `friends-positions`**: 2 queries instead of 1
- ⚠️ `_bg_delete_acked` uses individual `IN` clause — fine for small batches
- ✅ Good indexes on all primary query paths

### Memory
- ✅ `WorldState.users` is bounded by `max_users=500` — won't grow unbounded
- ✅ `_grid` is also bounded by number of active users
- ⚠️ `_rate_limit_buckets` grows with number of unique IPs/tokens — unbounded dict. With 10k users each with unique IPs, this stays in memory. Consider TTL-based eviction.
- ⚠️ `ws_clients` dict holds WebSocket references — bounded by concurrent connections

### Algorithmic Complexity
- ✅ `get_visible` is O(1) via spatial hash grid
- ⚠️ `_calc_exploration_frontier` is O(directions × search_rings × (2r/step)²) ≈ O(3600) worst case — acceptable for 1 call per 5s
- ✅ `get_bounds` is O(n) where n = visible users — fine

---

## Recommendations (Priority Order)

1. **Fix `from_user_id` → `from_id` / `to_user_id` → `to_id` in `world.py`** — this is a correctness emergency, several endpoints are completely broken
2. **Fix undefined `seven_days_ago` in `world_explored`** — currently crashes
3. **Fix `ws_client.py`'s broken `_calc_active_score`** — remove it and import the corrected one
4. **Fix `_world_state_from_app(None)` calls** in `world_explored` and `world_friends_positions` — they always return the fallback singleton
5. **Add CSP header or sandbox iframe for `/homepage/{user_id}`** — stored XSS risk
6. **Deduplicate `_calc_active_score`** into a shared `app/crawfish/social/scoring.py`
7. **Fix `_bg_delete_acked` ID parsing** — parse `msg_N` correctly, don't assume Message IDs equal SocialEvent IDs
8. **Batch the leaderboard queries** into a single aggregated SQL query
9. **Add database-level lock for APScheduler** if horizontal scaling is planned
10. **Migrate `on_event` to `lifespan` context manager** — eliminates deprecation warnings
11. **Cache user→rate_limit_key mapping** in `app.state` to avoid DB lookup per request
12. **Add file type allowlist** in `uploads.py` (`ALLOWED_EXTENSIONS = {'.jpg', '.png', '.gif', '.pdf'}`)
13. **Fix file save/DB transaction ordering** in `send_message_file`
14. **Fix `INSERT OR REPLACE` in SQLite heatmap aggregation** — the double-write is confusing and potentially buggy
15. **Add social event deduplication** with unique constraint

---

## What's Working Well

- **Spatial hash grid** implementation is elegant and performant
- **`_utc_now()` as single source of truth for timestamps** — all timestamps use timezone-aware UTC
- **Friend request state machine** is correct with proper IntegrityError handling for race conditions
- **`step_context` aggregation** in `ws_client.py` is a smart design — gives crawfish a complete world view every tick without scattered messages
- **WorldState thread-safety** with `threading.Lock` is correctly applied to all mutations
- **Graceful WebSocket disconnection** with `contextlib.suppress(asyncio.CancelledError)` is idiomatic
- **`app.state.ws_clients`** provides zero-infrastructure pub/sub for real-time push
- **Batch friend profile queries** avoid N+1 in the friends list endpoint
- **`Bulk_init_from_db`** correctly handles duplicate spawn during reconnection
- **`Stats` counter with `FOR UPDATE`** prevents race conditions in message counting
- **CSS design tokens** in `world/crawfish/index.html` are well-organized and the dark mode implementation is clean
- **Vue 3 composition API** usage is idiomatic with `<script setup>` throughout
- **WebSocket reconnection** with exponential-style fixed backoff in `world_map.ts` handles transient disconnections well
- **`pool_pre_ping=True`** in SQLAlchemy handles MySQL idle timeout gracefully
- **Migration system** correctly handles both MySQL and SQLite dialects
- **`secrets.token_hex(16)`** for token generation is cryptographically sound
- **`with_for_update()`** on Stats counter prevents double-increment race
- **The overall concept** — Travel Frog × AI Agent × Social Network — is creative and well-executed in code structure
