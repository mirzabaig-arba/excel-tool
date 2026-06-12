@echo off
setlocal
title Shareholder Finder - Local App

echo Starting the Web Interface...
echo A browser window will open automatically.
echo Keep this window open while processing photos.
echo.
python -m streamlit run app.py --server.headless false --browser.gatherUsageStats false
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The app failed to start.
    echo Try running "Setup_Local.bat" first.
    pause
)
