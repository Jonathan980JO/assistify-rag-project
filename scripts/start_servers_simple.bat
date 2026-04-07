@echo off
cd /d "%~dp0.."
echo Starting all servers...
set "PYTHON_EXE=%CD%\graduation\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
	echo [ERROR] Project Python not found at %PYTHON_EXE%
	exit /b 1
)
"%PYTHON_EXE%" -u scripts/project_start_server.py --reload
