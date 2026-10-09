@echo off
setlocal

:: --- Modifica questi percorsi se la tua installazione e' diversa ---
set VENV_PYTHON=%~dp0..\..\.venv312\Scripts\python.exe
set FC_DB=%~dp0..\..\file_classifier.db
:: Esempi: SYNC_ARGS=--block-shutdown   (blocca lo spegnimento mentre lavora)
::        SYNC_ARGS=--shutdown-when-done   (in piu', spegne il PC al termine)
set SYNC_ARGS=
:: -------------------------------------------------------------------

if not exist "%VENV_PYTHON%" (
    echo Python non trovato in: %VENV_PYTHON%
    echo Modifica il percorso VENV_PYTHON in questo file ^(sync.bat^).
    pause
    exit /b 1
)

echo Sincronizzazione in corso su %FC_DB% ...
echo.
"%VENV_PYTHON%" -m file_classifier --db "%FC_DB%" sync %SYNC_ARGS%

echo.
echo Sincronizzazione completata. Premi un tasto per chiudere.
pause >nul
endlocal
