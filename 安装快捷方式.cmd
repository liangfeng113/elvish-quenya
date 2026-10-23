@echo off
chcp 65001 >nul
rem Quenya learn app - install desktop + start menu + autostart shortcuts (ASCII only)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install.ps1" %*
echo.
pause
