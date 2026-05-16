@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Write-Host 'Windows background service is not wired yet.'; exit 1"
exit /b %ERRORLEVEL%
