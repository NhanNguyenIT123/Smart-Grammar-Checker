@echo off
title Smart Grammar Checker - Master Launcher
:MENU
cls
echo ===================================================
echo      Smart Grammar Checker - Master Launcher       
echo ===================================================
echo.
echo Please choose a running mode for the application:
echo.
echo  [1]  🚀 FULL AI MODE (Recommended)
echo       - Local ML (T5 GEC Model ~900MB) : ENABLED
echo       - SpaCy Syntax NLP               : ENABLED
echo       - Ollama Dynamic AI Generator    : ENABLED
echo.
echo  [2]  🤖 PURE AI MODE (For Dedicated AI Testing)
echo       - Local ML (T5 GEC Model ~900MB) : ENABLED
echo       - Ollama Dynamic AI Generator    : ENABLED
echo       - Rule-based and SpaCy NLP       : DISABLED (Pure ML Output)
echo.
echo  [3]  ⚡ LITE MODE (Fast Startup)
echo       - Rule-based & SpaCy NLP         : ENABLED
echo       - Local ML (T5 GEC Model)        : DISABLED (Saves RAM/CPU)
echo       - Ollama Dynamic AI Generator    : DISABLED (Uses standard templates)
echo.
echo  [4]  ❌ EXIT
echo.
echo ===================================================
set /p choice="Enter your choice (1-4): "

if "%choice%"=="1" goto FULL_AI
if "%choice%"=="2" goto PURE_AI
if "%choice%"=="3" goto LITE
if "%choice%"=="4" goto EXIT
goto MENU

:FULL_AI
cls
echo Starting in FULL AI MODE...
set GRAMMAR_CHECK_ENABLE_LOCAL_ML=1
set GRAMMAR_CHECK_ENABLE_SPACY_DETECTOR=1
set GRAMMAR_CHECK_USE_OLLAMA=1
set GRAMMAR_CHECK_ONLY_ML=0
set GRAMMAR_CHECK_LOCAL_ML_MODEL=%~dp0backend\ml\models\gec_t5_small
goto START_SERVICES

:PURE_AI
cls
echo Starting in PURE AI MODE...
set GRAMMAR_CHECK_ENABLE_LOCAL_ML=1
set GRAMMAR_CHECK_ENABLE_SPACY_DETECTOR=0
set GRAMMAR_CHECK_USE_OLLAMA=1
set GRAMMAR_CHECK_ONLY_ML=1
set GRAMMAR_CHECK_LOCAL_ML_MODEL=%~dp0backend\ml\models\gec_t5_small
goto START_SERVICES

:LITE
cls
echo Starting in LITE MODE...
set GRAMMAR_CHECK_ENABLE_LOCAL_ML=0
set GRAMMAR_CHECK_ENABLE_SPACY_DETECTOR=1
set GRAMMAR_CHECK_USE_OLLAMA=0
set GRAMMAR_CHECK_ONLY_ML=0
goto START_SERVICES

:START_SERVICES
echo.
echo Launching services...
echo.

:: Launch Backend in a new command window
echo [1/2] Starting Backend Server...
start "Smart Grammar Checker - Backend" cmd /k "set GRAMMAR_CHECK_ENABLE_LOCAL_ML=%GRAMMAR_CHECK_ENABLE_LOCAL_ML%&&set GRAMMAR_CHECK_ENABLE_SPACY_DETECTOR=%GRAMMAR_CHECK_ENABLE_SPACY_DETECTOR%&&set GRAMMAR_CHECK_USE_OLLAMA=%GRAMMAR_CHECK_USE_OLLAMA%&&set GRAMMAR_CHECK_ONLY_ML=%GRAMMAR_CHECK_ONLY_ML%&&set GRAMMAR_CHECK_LOCAL_ML_MODEL=%GRAMMAR_CHECK_LOCAL_ML_MODEL%&&backend\.venv\Scripts\python.exe backend\run.py serve --host 127.0.0.1 --port 8000"

:: Small delay to let backend start initializing
timeout /t 2 /nobreak >nul

:: Launch Frontend in a new command window
echo [2/2] Starting Frontend Vite Server...
start "Smart Grammar Checker - Frontend" cmd /k "node_modules\.bin\vite --host"

echo.
echo ===================================================
echo   All systems started successfully!
echo   - Backend  : http://127.0.0.1:8000
echo   - Frontend : http://localhost:5173/grammar
echo ===================================================
echo.
echo This window will close in 5 seconds.
timeout /t 5 >nul
exit

:EXIT
echo.
echo Goodbye!
timeout /t 2 >nul
exit
