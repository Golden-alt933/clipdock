param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$appUrl = 'http://127.0.0.1:8787'
try {
    $existing = Invoke-RestMethod "$appUrl/api/config" -TimeoutSec 2
    if ($existing.app -eq 'ClipDock') {
        if (-not $NoBrowser) { Start-Process $appUrl }
        exit 0
    }
} catch { }
try {
    $pythonPath = Join-Path $appRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        Write-Host 'Setting up ClipDock for the first time...'
        $pythonCommand = Get-Command python -ErrorAction Stop
        & $pythonCommand.Source -m venv (Join-Path $appRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the app environment. Install Python 3.11 or newer.' }
    }
    & $pythonPath -c 'import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(name) is not None for name in ("fastapi", "uvicorn", "yt_dlp", "yt_dlp_ejs")) else 1)'
    if ($LASTEXITCODE -ne 0) {
        & $pythonPath -m pip install -r (Join-Path $appRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Setup failed. Check your internet connection and try again.' }
    }
    foreach ($toolName in @('ffmpeg', 'node')) {
        if (-not (Get-Command $toolName -ErrorAction SilentlyContinue)) {
            throw "$toolName is missing. See README.txt for the free installation instructions."
        }
    }
    $runtimePath = Join-Path $appRoot '.runtime'
    New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
    $argumentList = '"' + (Join-Path $appRoot 'run.py') + '"'
    $appProcess = Start-Process -FilePath $pythonPath -ArgumentList $argumentList -WorkingDirectory $appRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath 'server.log') -RedirectStandardError (Join-Path $runtimePath 'errors.log')
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($appProcess.HasExited) { throw 'ClipDock could not start. Check .runtime\errors.log. Port 8787 may already be in use.' }
        try {
            $health = Invoke-RestMethod "$appUrl/api/config" -TimeoutSec 1
            if ($health.app -eq 'ClipDock') {
                if (-not $NoBrowser) { Start-Process $appUrl }
                exit 0
            }
        } catch { }
    }
    throw 'ClipDock is taking too long to start. Check .runtime\errors.log.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
