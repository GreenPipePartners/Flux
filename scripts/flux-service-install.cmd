@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Write-Host 'Windows service install is not wired yet. Use scripts\flux-start.cmd for foreground Windows startup.'; exit 1"
exit /b %ERRORLEVEL%
