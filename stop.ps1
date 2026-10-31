$ErrorActionPreference = 'Stop'
try {
    $config = Invoke-RestMethod 'http://127.0.0.1:8787/api/config' -TimeoutSec 2
    if ($config.app -eq 'ClipDock') {
        Invoke-RestMethod 'http://127.0.0.1:8787/api/shutdown' -Method Post -Headers @{'X-ClipDock-Token'=$config.token} -ContentType 'application/json' -Body '{}' | Out-Null
        Write-Host 'ClipDock stopped. Saved downloads are kept.'
    }
} catch {
    Write-Host 'ClipDock is already stopped or is not reachable.'
}
