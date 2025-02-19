@echo off
title manager
cd /d "%~dp0"

REM Start fitting room server
set PYTHON=%~dp0.venv\Scripts\python.exe

%PYTHON% manager.py
