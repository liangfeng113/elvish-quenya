@echo off
chcp 65001 >nul
rem Quenya mobile web server (ASCII-only comments)
title Quenya mobile
cd /d "%~dp0"

set PY=
if exist "C:\Users\1\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" (
  set "PY=C:\Users\1\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
)
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Need Python installed, or run: python mobile\serve.py
  pause
  exit /b 1
)

echo.
"%PY%" "%~dp0mobile\serve.py" 8123
echo.
echo Server stopped.
pause
