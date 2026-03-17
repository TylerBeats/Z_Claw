@echo off
echo.
echo  ==========================================
echo   OpenClaw // Mission Control
echo  ==========================================
echo.
echo  Starting local server...
echo  Dashboard: http://localhost:3000/dashboard
echo.
start "" "http://localhost:3000/dashboard"
npx serve C:\Users\Matty\OpenClaw-Orchestrator
