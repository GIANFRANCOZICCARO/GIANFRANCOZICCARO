@echo off
setlocal

:: Esempio: AGENTE_ARGS=--all   (sottopone tutti i dischi collegati, non uno a scelta)
set AGENTE_ARGS=

call "%~dp0_setup.bat"
if errorlevel 1 exit /b 1

set FC_DB=%PROJECT_DIR%\file_classifier.db

title Analisi dischi - %FC_DB%
"%VENV_PYTHON%" -m file_classifier --db "%FC_DB%" agente %AGENTE_ARGS%

echo.
pause >nul
endlocal
