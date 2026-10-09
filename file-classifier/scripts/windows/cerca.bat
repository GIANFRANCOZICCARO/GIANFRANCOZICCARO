@echo off
setlocal

call "%~dp0_setup.bat"
if errorlevel 1 exit /b 1

set FC_DB=%PROJECT_DIR%\file_classifier.db

title Cerca file - %FC_DB%
"%VENV_PYTHON%" -m file_classifier --db "%FC_DB%" cerca

echo.
pause >nul
endlocal
