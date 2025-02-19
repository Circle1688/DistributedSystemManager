@echo off
title node
cd /d "%~dp0"

REM Start fitting room server
set PYTHON=%~dp0.venv\Scripts\python.exe

%PYTHON% node.py

pause