. (Join-Path $PSScriptRoot 'runtime.ps1')
$pythonExecutable = Get-EdgeOpsPython
$nodeExecutable = Get-EdgeOpsNode
Push-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
try {
    & $pythonExecutable -X utf8 -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Backend or edge-agent tests failed.' }
    & $nodeExecutable --test 'frontend/tests/*.test.mjs'
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
    & $pythonExecutable -X utf8 -m unittest discover -s infra/tests -v
    if ($LASTEXITCODE -ne 0) { throw 'AWS adapter tests failed.' }
    & $pythonExecutable -m compileall -q backend scripts
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax validation failed.' }
    Write-Host 'All local checks passed. Cloud deployment is not implied by these checks.'
} finally {
    Pop-Location
}
