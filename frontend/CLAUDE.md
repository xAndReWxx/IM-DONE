# `frontend/` — CLAUDE.md

## What lives here

A React + Vite + TypeScript SPA. Two screens:

1. **LandingScreen** — a single robotic eye that tracks the
   cursor, surrounded by instrument-panel framing and a primary
   "Begin session" CTA.
2. **SessionScreen** — live camera with a real-time skeleton
   overlay, a 0-100 posture gauge, Arabic coaching feedback (RTL,
   with TTS), exercise recommendation cards, and a rep counter
   when an exercise is selected.

No router, no state library, no signup/login. The app holds one
`view` flag at the top and switches between the two screens.

## Aesthetic — "Industrial instrument panel"

This is intentionally NOT the default cyan/purple AI look.

- **Surfaces**: deep charcoal (`#0a0a0a` → `#242424`)
- **Text/lines**: bone white (`#f4f1ea`, never pure `#fff`)
- **Single accent**: signal amber `#f5b042` — used like a
  warning lamp, sparingly
- **Strokes**: hairlines (0.5–1px); no thick borders
- **Type**: Manrope (display), JetBrains Mono (telemetry), Cairo (Arabic RTL)
- **Motion**: slow ticks (eye bezel), gentle blinks, easing curves —
  nothing rave-y

All tokens live as CSS variables in `src/index.css`. Restyle
the entire app from one file.

## Quick start

```bash
cd frontend
npm install
npm run dev                # opens http://localhost:5173
```

Vite proxies `/ws` and `/health` to `http://localhost:8000`, so
just start the backend separately and the frontend talks to it
on the same origin (no CORS in dev).

For production:

```bash
npm run build              # outputs dist/
npm run preview            # serves dist/ locally
```

## Folder map

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts            ← React plugin + dev proxy for /ws and /health
├── src/
│   ├── main.tsx              ← React entry; mounts <App />
│   ├── App.tsx               ← Switches LandingScreen ↔ SessionScreen
│   ├── index.css             ← Design tokens + global resets
│   │
│   ├── components/
│   │   ├── RoboticEye.tsx + .css       ← The centerpiece SVG eye
│   │   ├── CameraOverlay.tsx + .css    ← <video> + skeleton canvas
│   │   ├── PostureGauge.tsx + .css     ← Half-circle dial (0..100)
│   │   ├── FeedbackPanel.tsx + .css    ← Arabic RTL coaching line
│   │   ├── RepCounter.tsx + .css       ← Big tabular-numeric counter + phase
│   │   ├── TelemetryBar.tsx + .css     ← FPS / latency strip
│   │   └── ExerciseCardView.tsx + .css ← Tappable recommendation card
│   │
│   ├── hooks/
│   │   ├── useCamera.ts          ← getUserMedia lifecycle
│   │   ├── useFrameSender.ts     ← Capture+JPEG+send loop
│   │   ├── useSessionSocket.ts   ← WebSocket session state
│   │   ├── useArabicVoice.ts     ← Web Speech API TTS for Arabic
│   │   └── useEyeFocus.ts        ← Cursor / idle drift for the eye
│   │
│   ├── lib/
│   │   ├── websocket-types.ts    ← Wire contract (mirrors backend Pydantic)
│   │   └── skeleton.ts           ← Canvas skeleton renderer
│   │
│   └── screens/
│       ├── LandingScreen.tsx + .css
│       └── SessionScreen.tsx + .css
```

## Data flow

```
┌────────────────────┐                  ┌─────────────────────┐
│  useCamera         │ video stream     │  <video> element    │
│  (getUserMedia)    │ ───────────────▶ │  (mirrored, muted)  │
└────────────────────┘                  └──────────┬──────────┘
                                                   │
                                       captureFrame│ (canvas → JPEG blob)
                                                   ▼
┌────────────────────┐ base64 + JSON   ┌─────────────────────┐
│  useFrameSender    │ ──── WS ─────▶  │   Backend           │
│  (~12 fps)         │                  │   /ws/session       │
└────────────────────┘                  └──────────┬──────────┘
                                                   │
                                  pose_result      │
                                                   ▼
┌────────────────────────────────────────────────────────────┐
│  useSessionSocket                                          │
│  splits result into:                                       │
│    landmarks → CameraOverlay (draws skeleton)              │
│    posture_score → PostureGauge                            │
│    feedback_ar → FeedbackPanel + useArabicVoice (TTS)      │
│    recommendations → ExerciseCardView list                 │
│    rep_state → RepCounter                                  │
└────────────────────────────────────────────────────────────┘
```

## Key design decisions

### One pending frame at a time

`useSessionSocket.sendFrame` uses a `busyRef` so we never have
more than one base64+JSON in flight. Stacking frames is what
kills WebSocket realtime feel — better to drop a frame than to
queue a tower of stale ones behind it.

### Skeleton on a separate canvas

The skeleton overlay isn't drawn into the camera's video stream
— it's a transparent canvas on top. This lets the user's video
remain pixel-perfect and gives us full canvas APIs for the
overlay without touching the camera capture path.

### `key={display}` on the feedback text

When the Arabic line changes, we want a smooth fade-in instead
of a snappy in-place swap. Setting `key` to the text content
forces React to remount the node, which triggers our CSS
`@keyframes feedback-fade` from scratch each time.

### TTS deduplication

`useArabicVoice` keeps a `lastSpokenRef` so repeated identical
feedback ("اعتدل في جلستك") isn't read every frame. A 400ms
debounce smooths over rapid issue toggles.

### Eye uses circular clamp, not square

In `RoboticEye`, the pupil's travel is `min(1, hypot(x,y)) *
MAX_TRAVEL` — so it moves in a disk, not a square. Without this
the pupil "sticks" at corners and looks robotic in a bad way.

## Wire contract

Mirrors `backend/app/models/packets.py`. The types live in
`src/lib/websocket-types.ts`. **If you change one side, change
the other in the same commit.**

| Direction        | Message types |
|------------------|---------------|
| Client → Server  | `frame`, `select_exercise`, `reset_reps`, `heartbeat` |
| Server → Client  | `connected`, `pose_result`, `error`, `heartbeat`      |

## Where to look for things

| You want to…                        | Open this file                       |
|-------------------------------------|--------------------------------------|
| Restyle the whole app               | `src/index.css` (design tokens)      |
| Change the robotic eye              | `src/components/RoboticEye.{tsx,css}`|
| Add a new screen                    | `src/screens/` + switch in `App.tsx` |
| Change frame rate / quality         | `src/hooks/useFrameSender.ts`        |
| Switch off auto-TTS                 | `SessionScreen` voice toggle / `useArabicVoice` |
| Add a new server message type       | `src/lib/websocket-types.ts` + handle in `useSessionSocket` |
| Change WebSocket URL                | `useSessionSocket` constructor (defaults to same origin) |
