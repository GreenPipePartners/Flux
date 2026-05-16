@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0flux-start.ps1"
exit /b %ERRORLEVEL%
