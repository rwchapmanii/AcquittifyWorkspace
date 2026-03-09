@echo off
setlocal

set HOST=%INCOURT_SERVER_HOST%
if "%HOST%"=="" set HOST=127.0.0.1
set PORT=%INCOURT_SERVER_PORT%
if "%PORT%"=="" set PORT=8777

set PYTHON=%~dp0..\.venv-incourt\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=%~dp0..\.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

"%PYTHON%" -m uvicorn incourt_listener.streaming_server:app --host %HOST% --port %PORT%
