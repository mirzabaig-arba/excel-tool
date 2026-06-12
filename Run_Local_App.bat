@echo off
setlocal
title Shareholder Finder - Local App

echo Starting the Web Interface...
echo A browser window will open automatically.
echo.
python -m streamlit run app.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The app failed to start.
    echo Try running "Setup_Local.bat" first.
    pause
)
