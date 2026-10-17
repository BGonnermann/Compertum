@echo off
python -B "%~dp0server.py" --open-browser
if errorlevel 1 pause
