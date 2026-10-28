param([int]$Port = 8765)
. (Join-Path $PSScriptRoot 'runtime.ps1')
$appRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = Get-EdgeOpsPython
Push-Location -LiteralPath $appRoot
try {
    Write-Host "EdgeOps local demo: http://127.0.0.1:$Port"
    Write-Host 'Synthetic device data. Press Ctrl+C to stop. No AWS account or dependency installation needed.'
    & $pythonExecutable -X utf8 -m backend.server --port $Port --data 'data/edgeops.sqlite3'
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
