@echo off
setlocal

:: --- Modifica questi due percorsi se la tua installazione e' diversa ---
set VENV_PYTHON=%~dp0..\..\.venv312\Scripts\python.exe
set FC_DB=%~dp0..\..\file_classifier.db
:: -------------------------------------------------------------------

if not exist "%VENV_PYTHON%" (
    echo Python non trovato in: %VENV_PYTHON%
    echo Modifica il percorso VENV_PYTHON in questo file ^(cerca.bat^).
    pause
    exit /b 1
)

title Cerca file - %FC_DB%
"%VENV_PYTHON%" -m file_classifier --db "%FC_DB%" cerca

echo.
pause >nul
endlocal
