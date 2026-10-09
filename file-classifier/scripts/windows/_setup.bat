@echo off
rem Richiamato dagli altri script con: call "%~dp0_setup.bat"
rem Verifica che l'ambiente sia pronto e, se manca o e' rotto (es. cartella
rem copiata su un altro PC/disco senza l'ambiente virtuale), lo prepara da
rem solo. Alla fine esporta PROJECT_DIR e VENV_PYTHON allo script chiamante
rem e ritorna errorlevel 0 (pronto) o 1 (errore, con messaggio gia' mostrato).
setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0..\.."
set "VENV_DIR=%PROJECT_DIR%\.venv312"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

rem Rimuove il blocco di sicurezza di Windows (file scaricati/copiati da
rem un'altra macchina) da tutto il progetto, in silenzio.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%PROJECT_DIR%' -Recurse -ErrorAction SilentlyContinue | Unblock-File" >nul 2>&1

if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" --version >nul 2>&1
    if not errorlevel 1 goto :check_deps
)

echo [file-classifier] Ambiente non trovato o non funzionante: lo creo adesso ^(solo la prima volta^)...

where py >nul 2>&1
if errorlevel 1 goto :try_python
py -3.12 -m venv "%VENV_DIR%" >nul 2>&1
if exist "%VENV_PYTHON%" goto :check_deps
py -3 -m venv "%VENV_DIR%" >nul 2>&1
if exist "%VENV_PYTHON%" goto :check_deps

:try_python
where python >nul 2>&1
if errorlevel 1 goto :no_python
python -m venv "%VENV_DIR%" >nul 2>&1
if exist "%VENV_PYTHON%" goto :check_deps

:no_python
echo [file-classifier] Errore: nessun Python funzionante trovato sul sistema.
echo Installa Python 3.12 da https://www.python.org/downloads/ e riprova.
pause
endlocal & set "PROJECT_DIR=%PROJECT_DIR%" & set "VENV_PYTHON=%VENV_PYTHON%" & exit /b 1

:check_deps
"%VENV_PYTHON%" -c "import file_classifier, psutil, sklearn, pypdf, docx" >nul 2>&1
if not errorlevel 1 goto :setup_ok

echo [file-classifier] Installazione delle dipendenze in corso ^(solo la prima volta, puo' richiedere qualche minuto^)...
"%VENV_PYTHON%" -m pip install --quiet -e "%PROJECT_DIR%"
if errorlevel 1 (
    echo [file-classifier] Errore durante l'installazione. Controlla la connessione internet e riprova.
    pause
    endlocal & set "PROJECT_DIR=%PROJECT_DIR%" & set "VENV_PYTHON=%VENV_PYTHON%" & exit /b 1
)

:setup_ok
endlocal & set "PROJECT_DIR=%PROJECT_DIR%" & set "VENV_PYTHON=%VENV_PYTHON%" & exit /b 0
