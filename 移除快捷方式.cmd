@echo off
chcp 65001 >nul
rem Quenya learn app - remove all shortcuts (ASCII only)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install.ps1" -Remove %*
echo.
pause
