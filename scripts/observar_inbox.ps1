<#
.SYNOPSIS
  Observa la carpeta data\inbox\ y procesa automáticamente cualquier PDF nuevo.

.DESCRIPTION
  Usa FileSystemWatcher de .NET para detectar cuando se agrega un archivo PDF
  a la carpeta data\inbox\. Al detectarlo, ejecuta automáticamente el pipeline
  de procesamiento.

  La ventana debe permanecer ABIERTA. Para cerrar: Ctrl+C.

.EXAMPLE
  .\scripts\observar_inbox.ps1
  .\scripts\observar_inbox.ps1 -Silent
#>

param([switch]$Silent)

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$InboxPath    = Join-Path $ProjectRoot "data\inbox"
$PythonScript = Join-Path $ProjectRoot "scripts\procesar_inbox.py"

function Write-Log($msg) {
    Write-Host ("[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $msg)
}

function Invoke-Processor {
    Write-Log "Procesando PDFs en inbox..."
    try {
        $output = & python $PythonScript --inbox-only 2>&1
        foreach ($line in $output) { Write-Host "  $line" }
        if (-not $Silent) { [Console]::Beep(800,200); Start-Sleep -Milliseconds 150; [Console]::Beep(1200,300) }
    } catch { Write-Log "ERROR: $_"; if (-not $Silent) { [Console]::Beep(200,500) } }
}

# ─── INICIO ──────────────────────────────────────────────────
Clear-Host
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║    OBSERVADOR DE EXTRACTOS BANCARIOS    ║" -ForegroundColor Cyan
Write-Host "╠══════════════════════════════════════════╣" -ForegroundColor Cyan
Write-Host "║  Estado: ACTIVO                         ║" -ForegroundColor Cyan
Write-Host "║  Inbox: data\inbox\                    ║" -ForegroundColor Cyan
Write-Host "║  Ctrl+C para detener.                  ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan

if (-not (Test-Path $InboxPath)) { New-Item -ItemType Directory -Path $InboxPath -Force | Out-Null }

# Procesar PDFs pendientes al inicio
$existing = Get-ChildItem $InboxPath -Filter "*.pdf" -ErrorAction SilentlyContinue
if ($existing) { Write-Log "Pendientes: $($existing.Count) PDF(s)"; Invoke-Processor }

# ─── WATCHER ───────────────────────────────────────────────
$Watcher = New-Object System.IO.FileSystemWatcher
$Watcher.Path = $InboxPath
$Watcher.Filter = "*.pdf"
$Watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName -bor [System.IO.NotifyFilters]::Size
$Watcher.EnableRaisingEvents = $true

$script:eventDetected = $false

$action = { $script:eventDetected = $true }
$null = Register-ObjectEvent -InputObject $Watcher -EventName Created -Action $action -SourceIdentifier PDFCreated
$null = Register-ObjectEvent -InputObject $Watcher -EventName Changed  -Action $action -SourceIdentifier PDFChanged

# ─── BUCLE PRINCIPAL ──────────────────────────────────────
try {
    $lastRun = (Get-Date).AddSeconds(-30)
    while ($true) {
        if ($script:eventDetected) {
            $script:eventDetected = $false
            $now = Get-Date
            # Debounce: esperar 4s desde último evento antes de ejecutar
            Start-Sleep -Seconds 4
            if ($script:eventDetected) {
                # Llegó otro archivo mientras esperábamos, reiniciar
                $script:eventDetected = $false
                Start-Sleep -Seconds 4
            }
            # Verificar que aún hay PDFs
            if (Get-ChildItem $InboxPath -Filter "*.pdf" -ErrorAction SilentlyContinue) {
                Invoke-Processor
            }
        }
        Start-Sleep -Milliseconds 500
    }
}
finally {
    $null = Unregister-Event -SourceIdentifier PDFCreated -ErrorAction SilentlyContinue
    $null = Unregister-Event -SourceIdentifier PDFChanged -ErrorAction SilentlyContinue
    $Watcher.Dispose()
    Write-Log "Observador detenido."
}
