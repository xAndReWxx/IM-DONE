# `scripts/` — CLAUDE.md

Convenience launchers and small helpers. Nothing here is
required to run PhysioAI — they just save typing.

| File             | Purpose                                                            |
|------------------|--------------------------------------------------------------------|
| `run_all.sh`     | Linux/macOS: starts the backend on :8000 and the frontend dev server on :5173, wired together via Vite's `/ws` proxy. Forwards Ctrl+C to both. |
| `run_all.bat`    | Windows equivalent — opens two cmd windows.                         |

First run installs the backend's Python deps in `backend/.venv`
and the frontend's npm packages. Subsequent runs reuse them.

If you'd rather start each service yourself, see the root
`README.md` for the explicit two-terminal commands.
