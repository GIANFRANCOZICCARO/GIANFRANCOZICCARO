#Requires -Version 5.0
<#
Crea sul Desktop tre collegamenti per i launcher di file-classifier:
  - Cerca file           -> cerca.bat   (agente interattivo di ricerca)
  - Analizza dischi      -> agente.bat  (elenca i dischi collegati e li sottopone
                                          ad acquisizione o revisione)
  - Interroga contenuti  -> query.bat   (ricerca full-text nel contenuto)

Eseguire una sola volta. Se PowerShell si lamenta dei permessi di
esecuzione, lanciarlo con:
    powershell -ExecutionPolicy Bypass -File .\crea_collegamenti_desktop.ps1
#>

$ScriptsDir = $PSScriptRoot
$Desktop = [Environment]::GetFolderPath("Desktop")
$Shell = New-Object -ComObject WScript.Shell

$Collegamenti = @(
    @{ Nome = "Cerca file.lnk";          Bat = "cerca.bat";  Descrizione = "file-classifier: cerca per parola chiave e apri il file trovato" },
    @{ Nome = "Analizza dischi.lnk";     Bat = "agente.bat"; Descrizione = "file-classifier: elenca i dischi collegati (nuovi/conosciuti) e li sottopone ad acquisizione o revisione" },
    @{ Nome = "Interroga contenuti.lnk"; Bat = "query.bat";  Descrizione = "file-classifier: ricerca full-text nel contenuto dei file indicizzati" }
)

foreach ($c in $Collegamenti) {
    $BatPath = Join-Path $ScriptsDir $c.Bat
    if (-not (Test-Path $BatPath)) {
        Write-Warning "Non trovato: $BatPath (saltato)"
        continue
    }

    $LinkPath = Join-Path $Desktop $c.Nome
    $Shortcut = $Shell.CreateShortcut($LinkPath)
    $Shortcut.TargetPath = $BatPath
    $Shortcut.WorkingDirectory = $ScriptsDir
    $Shortcut.Description = $c.Descrizione
    $Shortcut.Save()
    Write-Host "Creato: $LinkPath"
}

Write-Host "`nFatto. Trovi i tre collegamenti sul Desktop."
