@echo off
title Smart Grammar Checker Launcher
echo ===================================================
echo      Smart Grammar Checker - Master Launcher       
echo ===================================================
echo.
echo Launching services...
echo.

:: Launch Backend in a new command window
echo [1/2] Starting Backend (NLP/ML Enabled)...
start "Smart Grammar Checker - Backend" cmd /c "start_backend.bat"

:: Small delay to let backend start initializing
timeout /t 2 /nobreak >nul

:: Launch Frontend in a new command window
echo [2/2] Starting Frontend...
start "Smart Grammar Checker - Frontend" cmd /c "start_frontend.bat"

echo.
echo ===================================================
echo   All systems started successfully!
echo   - Backend: http://127.0.0.1:8000
echo   - Frontend: http://localhost:5173/grammar
echo ===================================================
echo.
echo This window will close in 5 seconds.
timeout /t 5 >nul
exit
