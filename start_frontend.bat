@echo off
title Smart Grammar Checker - Frontend
echo ===================================================
echo       Starting Smart Grammar Checker Frontend     
echo ===================================================
echo.

:: Run using npm.cmd to avoid PowerShell Execution Policy restrictions
call npm.cmd run dev

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Frontend failed to start.
    echo Please make sure you ran "npm install" first.
    pause
)
