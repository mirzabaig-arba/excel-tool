@echo off
setlocal
title Shareholder Finder - Local Setup

echo ===================================================
echo   Shareholder Finder - Local Web App Setup
echo ===================================================
echo.

:: Check for Python
python --version >pver.txt 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found. 
    echo Please install Python 3.12 from python.org
    echo IMPORTANT: Check "Add Python to PATH" during installation.
    pause
    exit /b
)
set /p PY_VER=<pver.txt
del pver.txt
echo [INFO] Detected %PY_VER%

echo [1/3] Installing requirements...
echo This includes EasyOCR which is a large download (~500MB).
echo Please be patient...
echo.
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Installation failed. 
    echo Check your internet connection and try again.
    pause
    exit /b
)

echo.
echo [2/3] Downloading OCR models (first time only, ~500MB)...
echo This fixes SSL errors on some Windows computers.
echo.
python download_ocr_models.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] OCR model download failed.
    echo Try running as administrator, or check firewall/antivirus.
    echo You can also run manually: python download_ocr_models.py
    pause
    exit /b
)

echo.
echo [3/3] Setup complete! 
echo You can now run the app using "Run_Local_App.bat"
echo.
pause
