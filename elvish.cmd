@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYW=C:\Users\1\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe
"%PYW%" "%~dp0tools\elvish.py" %*
