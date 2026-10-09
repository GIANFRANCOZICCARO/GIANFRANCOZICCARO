@echo off
setlocal enabledelayedexpansion

call "%~dp0_setup.bat"
if errorlevel 1 exit /b 1

set FC_DB=%PROJECT_DIR%\file_classifier.db

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
