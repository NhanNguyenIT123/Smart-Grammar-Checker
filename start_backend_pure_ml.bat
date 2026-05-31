@echo off
title Smart Grammar Checker - Pure AI (Local ML Only)
echo ===================================================
echo   Backend with PURE AI (Local ML Only) - No Rules  
echo ===================================================
echo.

if not exist "backend\ml\models\gec_t5_small\config.json" goto NO_MODEL

echo [OK] Local ML model found. Starting in PURE AI MODE...
echo.
set GRAMMAR_CHECK_ONLY_ML=1
set GRAMMAR_CHECK_ENABLE_LOCAL_ML=1
set GRAMMAR_CHECK_LOCAL_ML_MODEL=%~dp0backend\ml\models\gec_t5_small
goto START_SERVER

:NO_MODEL
echo [ERROR] Local ML model not found at backend\ml\models\gec_t5_small\
echo.
echo  Please run this first to download the model (~900 MB):
echo    backend\.venv\Scripts\python.exe backend\ml\scripts\download_pretrained_gec.py
echo.
pause
exit

:START_SERVER
rem Turn off SpaCy and static rules by enforcing ONLY_ML
set GRAMMAR_CHECK_ENABLE_SPACY_DETECTOR=0

"backend\.venv\Scripts\python.exe" backend\run.py serve --host 127.0.0.1 --port 8000

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Backend failed to start.
    pause
)
