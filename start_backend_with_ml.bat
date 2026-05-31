@echo off
title Smart Grammar Checker - Backend (NLP + Local ML)
echo ===================================================
echo   Backend with Rule-Based + SpaCy + Local ML GEC  
echo ===================================================
echo.

if not exist "backend\ml\models\gec_t5_small\config.json" goto NO_MODEL

echo [OK] Local ML model found. Enabling GEC pipeline...
echo.
set GRAMMAR_CHECK_ENABLE_LOCAL_ML=1
set GRAMMAR_CHECK_LOCAL_ML_MODEL=%~dp0backend\ml\models\gec_t5_small
goto START_SERVER

:NO_MODEL
echo [WARNING] Local ML model not found at backend\ml\models\gec_t5_small\
echo.
echo  Run this first to download the model (~900 MB):
echo    backend\.venv\Scripts\python.exe backend\ml\scripts\download_pretrained_gec.py
echo.
echo  Starting backend WITHOUT local ML...
echo.
set GRAMMAR_CHECK_ENABLE_LOCAL_ML=0

:START_SERVER
set GRAMMAR_CHECK_ENABLE_SPACY_DETECTOR=1

"backend\.venv\Scripts\python.exe" backend\run.py serve --host 127.0.0.1 --port 8000

if %ERRORLEVEL% neq 0 goto ERROR_HANDLER
goto END

:ERROR_HANDLER
echo.
echo [ERROR] Backend failed to start.
pause

:END
