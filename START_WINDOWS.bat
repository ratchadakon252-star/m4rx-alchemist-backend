@echo off
cd /d "%~dp0"
title THE ALCHEMIST NEXT - Image First
cls
echo ======================================
echo THE ALCHEMIST NEXT - IMAGE FIRST
 echo ======================================
echo.
echo Checking Python ...
python --version
if errorlevel 1 goto python_error
echo.
echo Installing required packages when needed ...
python -m pip install -r requirements.txt
if errorlevel 1 goto install_error
echo.
echo Starting local web app ...
echo Open browser at http://127.0.0.1:8765
echo Keep this window open while using the app.
python app.py
echo.
echo The app has stopped. Read the message above if unexpected.
pause
goto end
:python_error
echo Python not found. Install Python 3.12 or later with PATH enabled.
pause
goto end
:install_error
echo Installation failed. Check the error messages above and Internet connection.
pause
:end
