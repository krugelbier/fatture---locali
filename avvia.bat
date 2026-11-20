@echo off
title Fatture Locali - Krugel ^& Cafe L'Incontro
echo ===================================================================
echo   FATTURE LOCALI - Krugel ^& Cafe L'Incontro
echo   Avvio dell'applicazione web locale...
echo ===================================================================
echo.

:: 1. Imposta come cartella di lavoro la cartella in cui si trova questo file .bat
cd /d "%~dp0"

:: 2. Trova l'eseguibile Python corretto sul sistema
set "PY_CMD="

if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    set "PY_CMD=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
) else if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
    set "PY_CMD=%LOCALAPPDATA%\Python\bin\python.exe"
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PY_CMD=python"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else (
        set "PY_CMD=python"
    )
)

echo Percorso applicazione: %CD%
echo Rilevato interprete Python: %PY_CMD%
echo.

:: 3. Avvia l'applicazione
"%PY_CMD%" avvia_app.py

if %errorlevel% neq 0 (
    echo.
    echo ===================================================================
    echo Si e' verificato un problema durante l'esecuzione dell'app.
    echo ===================================================================
    pause
)
