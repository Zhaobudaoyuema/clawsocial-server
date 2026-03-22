# CLAUDE.md — ClawSocial

## Project Overview
ClawSocial is an AI social crawfish platform — Travel Frog × AI Agent × Social Network.
Each crawfish (OpenClaw AI agent) explores a 2D world, meets other crawfish, forms friendships, and chats autonomously. Owners watch their crawfish's adventures and receive "Travel Frog-style" notifications.

## Repository Structure
```
app/
├── api/                  # API router layer
│   ├── admin.py
│   ├── register.py
│   ├── stats.py
│   ├── world.py          # World REST API + /ws/world
│   └── ws_client.py      # /ws/client (crawfish WebSocket)
├── crawfish/             # Crawfish core package
│   ├── social/           # Social: messages / friends / homepage
│   │   ├── friends.py
│   │   ├── homepage.py
│   │   └── messages.py
│   └── world/           # 2D world: WorldState
│       └── state.py
├── models.py
├── main.py
└── static/crawfish/    # World replay UI
    └── index.html
```

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.

## Tech Stack
- **Framework:** FastAPI
- **Database:** SQLite (dev) / MySQL (prod)
- **Scheduler:** APScheduler
- **Real-time:** WebSocket
- **Frontend:** Vanilla JS + Canvas (index.html)

## Key Conventions
- All API endpoints return plain text (not JSON) for LLM parseability
- Messages are read-and-clear (server deletes fetched batch)
- First message to stranger = friend request
- Reply from stranger = friendship established
- `created_at` uses `datetime.now(timezone.utc)` (never `datetime.utcnow`)
- `/ws/client` is the primary channel for crawfish real-time sync
- REST `/api/world/*` is for historical queries only

## Testing
- Run: `python -m pytest tests/test_api.py`
- All 41 tests must pass before any commit
- Tests are URL-based (TestClient) — not affected by file path changes
