@echo off
cd /d "%~dp0"
python -m unittest -v test_vision
python test_app.py
pause
