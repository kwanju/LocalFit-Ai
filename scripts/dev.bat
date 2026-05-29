@echo off
REM LocalFit AI — dev launcher: backend (FastAPI) + frontend (Vite) together.
REM Each runs in its own window so logs and Ctrl+C stay independent.
REM Vite proxies /health, /onboarding, /ws ... to 127.0.0.1:8000 (no CORS needed).
cd /d "%~dp0.."
start "LocalFit backend" cmd /k "uv run python -m app.main"
start "LocalFit UI" cmd /k "cd ui && pnpm dev"
echo Launched backend (http://127.0.0.1:8000) and UI (http://localhost:5173).
