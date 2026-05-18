# `ai-engine/` — CLAUDE.md

## What lives here

This folder is the **AI pipeline reference**: the dataset
analysis output, threshold derivation, and a copy of the
good-posture reference that the backend loads at startup.

In V1 / the earlier V2 scaffold, this was a **separate Python
microservice** that ran its own WebSocket on a second port. We
merged that into the backend in this V2 rewrite — see
"Why the merge?" below — so this folder no longer contains a
runnable service.

If you need to change AI behavior (thresholds, exercises,
posture rules, smoothing, etc.), see **`backend/CLAUDE.md`** for
where the code now lives, or jump straight to
`backend/app/services/ai/`.

## Folder map

```
ai-engine/
├── CLAUDE.md                          ← (this file)
└── reference/
    └── good_posture_reference.json    ← derived from your CSVs
```

The reference JSON is the authoritative dataset summary. The
backend has its own copy under
`backend/app/reference/good_posture_reference.json` — both
should stay identical. Treat the one in this folder as the
"source", and copy it to the backend when changes are made.

## Why the merge?

In V1, the AI engine ran as a second microservice. That
arrangement had three big costs for an offline MVP:

1. **Doubled WebSocket latency** — frames hopped
   browser → backend → ai-engine → backend → browser
2. **Two ports/origins** — needed extra CORS plumbing and
   a second `pip install` set
3. **Duplicated WS code** — both processes implemented their
   own connection manager, validation, and routing

V2 collapses both into one FastAPI process. The AI pipeline now
lives in `backend/app/services/ai/` and is called directly from
the WebSocket handler. One server, one port, one set of deps,
half the latency.

## The reference JSON, briefly

`reference/good_posture_reference.json` was generated from the
project's training data:

- **`dataset_all_points.csv`** — 2,700 labeled snapshots, each
  with 33 MediaPipe landmarks (x, y, z, visibility). The
  `rest` class (n=406) gives us a clean "good posture" pose:

  | Metric                   | Mean   | What it means        |
  |--------------------------|--------|----------------------|
  | forward-head angle       | 18.3°  | ear-to-shoulder line |
  | shoulder tilt            | 1.2°   | shoulder horizontal  |
  | spine lean               | 1.4°   | shoulder-mid → hip-mid |

- **`data.csv`** — 45,000 rows of angle/EMG/posture labels with
  English recommendations per class
  (`Good Posture`, `Slouching`, `Neck Bend`, `Leaning Forward`,
  `Shoulder Tilt`).

From these we derived the warn/bad thresholds:

```jsonc
"thresholds": {
  "forward_head_warn_deg": 22.0,   // > baseline + ~4°
  "forward_head_bad_deg":  30.0,   // clinical FHP cutoff
  "shoulder_tilt_warn_deg": 5.0,
  "shoulder_tilt_bad_deg": 10.0,
  "spine_lean_warn_deg":   6.0,
  "spine_lean_bad_deg":   12.0
}
```

The backend loads this JSON in `PostureAnalyzer.__init__`. To
retune posture sensitivity without touching Python, edit the
JSON and restart the server.

## Adding a new posture rule

1. Pick the landmarks involved
   (see `backend/app/services/ai/posture_analyzer.py` for the
   indices we use).
2. Add a function to `geometry.py` if a new math primitive is
   needed.
3. Extend `analyze()` in `posture_analyzer.py` with the new
   rule.
4. Add the issue key to the `PostureIssue` union in
   `frontend/src/lib/websocket-types.ts`.
5. Add an Arabic feedback string in `ISSUE_FEEDBACK_AR` and an
   exercise mapping in
   `backend/app/services/ai/exercise_catalog.py`.
