@echo off
REM Detached CrewLab Messenger UI launcher
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-ui.ps1" %*
