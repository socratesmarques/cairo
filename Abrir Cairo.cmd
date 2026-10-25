@echo off
cd /d "%~dp0"
python -m cairo.desktop
if errorlevel 1 pause
