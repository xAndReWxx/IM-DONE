@echo off
REM ============================================================
REM PhysioAI Pro V2 — Run both services (Windows)
REM ============================================================
REM Spins up the backend and the frontend dev server in two
REM separate command windows.
REM ============================================================

set ROOT=%~dp0..
set BACKEND=%ROOT%\backend
set FRONTEND=%ROOT%\frontend

echo --- PhysioAI Pro V2 launcher ---

REM Backend setup
if not exist "%BACKEND%\.venv" (
  echo [backend] Creating venv...
  cd /d "%BACKEND%"
  python -m venv .venv
)
cd /d "%BACKEND%"
call .venv\Scripts\activate
pip install -q -r requirements.txt

REM Frontend setup
cd /d "%FRONTEND%"
if not exist node_modules (
  echo [frontend] Installing npm deps...
  npm install --silent --no-audit --no-fund
)

REM Launch each in its own window
start "PhysioAI backend"  cmd /k "cd /d %BACKEND% && .venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
start "PhysioAI frontend" cmd /k "cd /d %FRONTEND% && npm run dev -- --host 0.0.0.0"

echo.
echo Backend  : http://localhost:8000
echo Frontend : https://localhost:5173
echo.
echo --- TABLET ACCESS ---
echo Open https://YOUR_LAPTOP_IP:5173 on the tablet
echo Accept the self-signed certificate warning
echo Camera + AI scanning will work over HTTPS

