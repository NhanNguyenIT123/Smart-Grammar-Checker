@echo off
title Smart Grammar Checker - Backend
echo ===================================================
echo   Starting Smart Grammar Checker Backend (NLP/ML)  
echo ===================================================
echo.

:: Set environment variable for Local NLP/ML
set GRAMMAR_CHECK_ENABLE_LOCAL_ML=1

:: Run using the virtual environment python executable directly
"backend\.venv\Scripts\python.exe" backend\run.py serve --host 127.0.0.1 --port 8000

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Backend failed to start.
    echo Please make sure you ran "pip install -r backend/requirements.txt" inside your venv.
    pause
)
