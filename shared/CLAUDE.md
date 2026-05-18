# `shared/` — CLAUDE.md

Reserved for resources shared between the frontend and the
backend (e.g. cross-language JSON Schema for the wire contract,
or assets we want both sides to read from disk in dev).

Currently empty. The wire contract is enforced in two places
that you must keep in lockstep:

- Backend: `backend/app/models/packets.py` (Pydantic)
- Frontend: `frontend/src/lib/websocket-types.ts` (TypeScript)

If we add an OpenAPI-style schema or a generator, it'll land
here.
