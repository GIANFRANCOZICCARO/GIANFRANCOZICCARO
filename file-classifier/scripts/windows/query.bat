@echo off
setlocal enabledelayedexpansion

:: --- Modifica questi due percorsi se la tua installazione e' diversa ---
set VENV_PYTHON=%~dp0..\..\.venv312\Scripts\python.exe
set FC_DB=%~dp0..\..\file_classifier.db
:: -------------------------------------------------------------------

if not exist "%VENV_PYTHON%" (
    echo Python non trovato in: %VENV_PYTHON%
    echo Modifica il percorso VENV_PYTHON in questo file ^(query.bat^).
    pause
    exit /b 1
)

title Interroga contenuti - %FC_DB%

:loop
set TERMINI=
set /p TERMINI="Termini di ricerca nel contenuto (vuoto per uscire): "
if "%TERMINI%"=="" goto fine

"%VENV_PYTHON%" -m file_classifier --db "%FC_DB%" query "%TERMINI%"
echo.
goto loop

:fine
endlocal
