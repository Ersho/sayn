@echo off
rem Double-click friendly wrapper around setup.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
pause
