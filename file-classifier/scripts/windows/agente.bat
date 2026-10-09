@echo off
setlocal

:: --- Modifica questi percorsi se la tua installazione e' diversa ---
set VENV_PYTHON=%~dp0..\..\.venv312\Scripts\python.exe
set FC_DB=%~dp0..\..\file_classifier.db
:: Esempio: AGENTE_ARGS=--all   (sottopone tutti i dischi collegati, non uno a scelta)
set AGENTE_ARGS=
:: -------------------------------------------------------------------

if not exist "%VENV_PYTHON%" (
    echo Python non trovato in: %VENV_PYTHON%
    echo Modifica il percorso VENV_PYTHON in questo file ^(agente.bat^).
    pause
    exit /b 1
)

title Analisi dischi - %FC_DB%
"%VENV_PYTHON%" -m file_classifier --db "%FC_DB%" agente %AGENTE_ARGS%

echo.
pause >nul
endlocal
