@echo off
rem Starts the backend (http://localhost:8000) and the dashboard (http://localhost:5173),
rem each in its own window. Close a window (or press Ctrl+C in it) to stop that server.
set ROOT=%~dp0..

if not exist "%ROOT%\dashboard\node_modules" (
    echo Installing dashboard dependencies...
    pushd "%ROOT%\dashboard"
    call npm install
    popd
)

start "sayn backend" /D "%ROOT%\backend" cmd /k uv run uvicorn vibe.api:app --port 8000
start "sayn dashboard" /D "%ROOT%\dashboard" cmd /k npm run dev

echo Backend:   http://localhost:8000
echo Dashboard: http://localhost:5173
