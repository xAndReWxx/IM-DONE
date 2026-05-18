# PhysioAI Pro V2 — Root CLAUDE.md

This file is the entry point if you (or any future AI assistant)
need to make sense of the repo. It explains the high-level
architecture, what changed from V1, and where to look first.

For folder-specific details, each subdirectory has its own
`CLAUDE.md` — read those when working inside that folder.

## The 30-second tour

PhysioAI is a **two-piece offline app**:

1. **Frontend** — a React SPA that opens the user's camera,
   sends JPEG frames over WebSocket, and renders a realtime
   skeleton, posture score, Arabic feedback, and exercise UI.
2. **Backend** — a FastAPI server that receives frames, runs a
   MediaPipe pose pipeline, analyzes posture, recommends
   exercises, and tracks rep counts via FSMs — then sends it
   all back on the same WebSocket.

There is **no auth, no database, no cloud**. Everything runs on
one PC.

## The big change from V1

V1 had **three** runtime pieces: frontend, backend, and a
separate `ai-engine/` microservice. Frames went
browser → backend → ai-engine → backend → browser, which:

- Doubled WebSocket latency
- Needed two `pip install` sets and two ports
- Duplicated connection-management code

V2 collapses backend + ai-engine into **one Python process**.
The AI pipeline now lives at `backend/app/services/ai/`. The
`ai-engine/` folder still exists, but it's now just the dataset
analysis reference (see `ai-engine/CLAUDE.md`).

## Folders, ranked by how often you'll touch them

| Rank | Folder       | Why you'd be there                                                  |
|------|--------------|----------------------------------------------------------------------|
| 1    | `frontend/`  | Visual changes, UX tweaks, screen layout                              |
| 2    | `backend/`   | AI logic, posture rules, exercise tracking, WS protocol               |
| 3    | `ai-engine/` | Tuning thresholds via the reference JSON                              |
| 4    | `scripts/`   | Adding new dev/build commands                                         |
| 5    | `datasets/`  | Re-running the analysis on new data                                   |

## How the wire contract works

Two files define the contract:

- `backend/app/models/packets.py` — Pydantic models (server side)
- `frontend/src/lib/websocket-types.ts` — TypeScript types (client side)

**They must stay in sync.** If you change one, change the other
in the same commit, or the live stream will silently misbehave.
See either file's header comment for the full message list.

## Where the dataset thresholds come from

`backend/app/reference/good_posture_reference.json` (and its
mirror in `ai-engine/reference/`) was generated from the two
training CSVs:

- `dataset_all_points.csv` — 2,700 labeled MediaPipe snapshots.
  The `rest` class gives a baseline good-posture pose with
  forward-head ≈ 18°, shoulder tilt ≈ 1.2°, spine lean ≈ 1.4°.
- `data.csv` — 45k rows of angle/EMG labels with English
  recommendations per posture class.

We derived warn/bad thresholds as clinical-style offsets above
the baseline. To retune posture sensitivity, edit the JSON and
restart the backend.

## Defaults / conventions

- **Python 3.11+** for the backend.
- **Node 18+** for the frontend.
- **Single uvicorn worker** — WebSocket connections are
  process-pinned; multi-worker would split clients across
  processes and break the in-memory connection manager.
- **CSS variables** for design tokens — restyle the whole UI
  from `frontend/src/index.css`.

## When iterating

- Backend tests: `cd backend && pytest` (14 tests, all green).
- Frontend type check: `cd frontend && npx tsc --noEmit`.
- Frontend build: `cd frontend && npm run build` (outputs `dist/`).
- Frontend dev with hot reload: `npm run dev`.
- Reload backend on save: `uvicorn ... --reload`.

## When something looks wrong

- "Skeleton is offset / mirrored" → check
  `frontend/src/lib/skeleton.ts` `mirror` flag and the CSS
  `transform: scaleX(-1)` on `.camera__video`. They must match.
- "Posture score is wrong" → tune
  `backend/app/reference/good_posture_reference.json`.
- "AI is dead but UI works" → backend boots in degraded mode
  if MediaPipe didn't install. Check `/health` — `ai_ready`
  should be `true`. If not, `pip install mediapipe` in the
  backend venv.
- "WebSocket immediately closes" → server log will say
  `connection_rejected reason=limit_reached`. Bump
  `WS_MAX_CONNECTIONS` in `backend/.env`.
- "No Arabic voice" → not every browser ships an Arabic voice.
  Check `window.speechSynthesis.getVoices()`. The TTS is
  best-effort and silently no-ops if there's no `ar-*` voice
  available.
