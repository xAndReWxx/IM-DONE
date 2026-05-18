# `backend/` — CLAUDE.md

## What lives here

The PhysioAI Pro V2 **backend**: a single FastAPI process that
serves both the HTTP health endpoints **and** the realtime
WebSocket session. It also embeds the entire AI pipeline
(MediaPipe + posture analysis + rep tracking) so there's no
second microservice to run.

If you used V1 (or the earlier V2 scaffold) and noticed there
was a separate `ai-engine/` Python service: that's now merged
in here under `app/services/ai/` for lower latency and easier
offline use.

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
cp .env.example .env                                # optional — defaults are fine
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

First run downloads the MediaPipe pose model (~9 MB) to
`app/models_cache/`. Subsequent runs reuse it.

Test endpoints (HTTP):

- `GET /`              — identity check
- `GET /health`        — detailed status incl. AI readiness
- `GET /health/ready`  — minimal readiness probe
- `GET /docs`          — Swagger UI (dev mode only)

WebSocket endpoint:

- `ws://localhost:8000/ws/session`

## Folder map and intent

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 ← FastAPI app factory; uvicorn imports `app`
│   │
│   ├── config/                 ← Pydantic Settings singleton
│   │   └── settings.py
│   │
│   ├── core/                   ← Cross-cutting concerns
│   │   ├── events.py           ← Lifespan: startup/shutdown hooks
│   │   └── exceptions.py       ← PhysioAIError + subclasses
│   │
│   ├── middleware/
│   │   └── error_handler.py    ← Global HTTP exception → JSON
│   │
│   ├── models/
│   │   └── packets.py          ← Pydantic models for every WS packet
│   │
│   ├── routers/
│   │   ├── health.py           ← GET / /health /health/ready
│   │   └── websocket_routes.py ← /ws/session
│   │
│   ├── services/               ← Business logic
│   │   ├── frame_router.py     ← Rate-limit + concurrency cap → AI
│   │   ├── ai_engine.py        ← Main pipeline orchestrator (singleton)
│   │   └── ai/                 ← AI sub-pipeline (the meat)
│   │       ├── pose_engine.py        ← MediaPipe Tasks API wrapper
│   │       ├── landmark_filter.py    ← Per-client EMA smoothing
│   │       ├── geometry.py           ← Angle/midpoint math
│   │       ├── posture_analyzer.py   ← Score/issues/Arabic feedback
│   │       ├── exercise_catalog.py   ← Static exercise content (AR/EN)
│   │       └── exercises/            ← One file per rep tracker
│   │           ├── base.py           ← BaseExerciseTracker FSM
│   │           ├── chin_tuck.py
│   │           ├── wall_angel.py
│   │           └── thoracic_extension.py
│   │
│   ├── reference/
│   │   └── good_posture_reference.json  ← Thresholds derived from your CSVs
│   │
│   ├── utils/
│   │   ├── helpers.py          ← client ID, timestamp, byte formatting
│   │   └── logger.py           ← structlog setup (get_logger)
│   │
│   ├── websocket/
│   │   ├── manager.py          ← ConnectionManager singleton
│   │   └── handler.py          ← Main per-connection async function
│   │
│   └── models_cache/           ← Downloaded MediaPipe model (.gitignored)
│
├── tests/                      ← pytest suite
├── requirements.txt
├── pyproject.toml
├── .env.example
└── .gitignore
```

## End-to-end request flow

```
Browser              Backend                    AI pipeline
   │                    │                            │
   │── WS connect ──────▶                            │
   │                    ├ ConnectionManager.connect  │
   │◀── connected ──────┤                            │
   │                    │                            │
   │── frame (JPEG) ────▶                            │
   │                    ├ handler._handle_frame      │
   │                    ├ FramePacket.validate       │
   │                    ├ frame_router.process_frame │
   │                    │    └ rate limit + sem ───▶ ai_engine.process_frame
   │                    │                            ├ decode (OpenCV)
   │                    │                            ├ pose detect (MediaPipe)
   │                    │                            ├ EMA smooth
   │                    │                            ├ PostureAnalyzer
   │                    │                            ├ recommend_for_issues
   │                    │                            └ tracker.process (if any)
   │◀── pose_result ────┤◀ ──── PoseResultPacket ────┘
   │                    │
   │── select_exercise ─▶  ai_engine.select_exercise
   │── reset_reps ──────▶  ai_engine.reset_reps
   │── heartbeat ───────▶  reply with pong
```

## Key design decisions (and why)

### Backend + AI in one process

V1 separated the AI engine into a second WebSocket service.
That doubled latency (frame → backend → AI → backend → client),
required two ports/origins, and made offline deployment harder.
V2 collapses them: the AI pipeline runs in `app/services/ai/`
and is called directly from the WS handler. One server, one
port, fewer moving parts.

### `RunningMode.IMAGE` instead of `LIVE_STREAM`

MediaPipe's `LIVE_STREAM` mode uses a callback-based async API
that's awkward to combine with FastAPI's per-request async flow.
`IMAGE` mode is synchronous and integrates cleanly with
`asyncio.to_thread`. At our target FPS (20), the latency
difference is negligible.

### Per-client state (smoothing + rep tracking)

Both the EMA filter and the exercise FSM are stateful. We hold
that state in `AIEngine._client_state[client_id]` and tear it
down on disconnect. This stops one user's history from leaking
into another's skeleton or rep count.

### Soft-failing MediaPipe

If MediaPipe doesn't install (CI, frontend-only iteration), the
backend still boots — it just returns empty `pose_result`
payloads. The frontend handles this gracefully ("stand in
frame"). This makes parallel frontend work possible without
blocking on the CV stack.

### Thresholds from your dataset, not guesses

`posture_analyzer.py` reads thresholds from
`app/reference/good_posture_reference.json`, which was generated
from the CSVs you provided (`data.csv`, `dataset_all_points.csv`).
The defaults in `settings.py` are fallbacks; the JSON wins when
present. Adjust the JSON to retune posture sensitivity without
touching Python code.

### Rate limit + concurrency cap

`FrameRouter` rate-limits each client at `MAX_FPS` and uses a
process-wide `asyncio.Semaphore` to cap total in-flight AI calls.
Without these, one client spamming frames could starve others.

## Wire contract (must stay in sync with the frontend)

### Client → Server

| `type`             | Payload                              | Effect                          |
|--------------------|--------------------------------------|---------------------------------|
| `frame`            | `{timestamp, frame: base64 JPEG}`    | Run AI pipeline, reply pose_result |
| `select_exercise`  | `{exercise_id}`                      | Switch tracked exercise          |
| `reset_reps`       | `{}`                                 | Zero current rep counter         |
| `heartbeat`        | `{timestamp?}`                       | Keep-alive; reply with pong      |

### Server → Client

| `type`         | Payload                                                                          |
|----------------|----------------------------------------------------------------------------------|
| `connected`    | `{client_id, config: {...}}` — handshake reply                                  |
| `pose_result`  | `{fps, landmarks, posture_score, posture_issues, feedback_ar, recommendations, rep_state, latency_ms}` |
| `error`        | `{code, message, details?}`                                                      |
| `heartbeat`    | `{timestamp, server_time}` — pong                                                |

If you change the contract, update both:

1. `backend/app/models/packets.py` (Pydantic models)
2. `frontend/src/lib/websocket-types.ts` (TS types)

## Where to look for things

| You want to…                       | Open this file                                                 |
|------------------------------------|----------------------------------------------------------------|
| Tune posture sensitivity           | `app/reference/good_posture_reference.json` (or settings)      |
| Add a new exercise                 | `app/services/ai/exercises/` + `exercise_catalog.py`           |
| Change the WebSocket path          | `app/routers/websocket_routes.py` + frontend `WS_URL`          |
| Adjust rate limiting               | `app/services/frame_router.py` + `MAX_FPS` in settings         |
| Change Arabic feedback wording     | `app/services/ai/posture_analyzer.py` (`ISSUE_FEEDBACK_AR`)    |
| Add a new posture rule             | `app/services/ai/posture_analyzer.py` (`analyze` method)       |
| Adjust EMA smoothing               | `app/services/ai/landmark_filter.py` or `EMA_ALPHA_LANDMARKS`  |
