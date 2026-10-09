@echo off
setlocal

:: Esempi: SYNC_ARGS=--block-shutdown   (blocca lo spegnimento mentre lavora)
::        SYNC_ARGS=--shutdown-when-done   (in piu', spegne il PC al termine)
set SYNC_ARGS=

call "%~dp0_setup.bat"
if errorlevel 1 exit /b 1

set FC_DB=%PROJECT_DIR%\file_classifier.db

echo Sincronizzazione in corso su %FC_DB% ...
echo.
"%VENV_PYTHON%" -m file_classifier --db "%FC_DB%" sync %SYNC_ARGS%

echo.
echo Sincronizzazione completata. Premi un tasto per chiudere.
pause >nul
endlocal
