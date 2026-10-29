@echo off
rem Double-click to set up StudyBuddyAvatar. Extra args are passed through (e.g. setup.bat -Cpu)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
pause
