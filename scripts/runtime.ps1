$ErrorActionPreference = 'Stop'

function Get-EdgeOpsPython {
    $candidates = @()
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython -and $systemPython.Source -notlike '*WindowsApps*') {
        $candidates += $systemPython.Source
    }
    $candidates += (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    throw 'Python 3.11 or newer is required. Install Python, then rerun this script.'
}

function Get-EdgeOpsNode {
    $systemNode = Get-Command node -ErrorAction SilentlyContinue
    if ($systemNode) { return $systemNode.Source }
    $bundledNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    if (Test-Path -LiteralPath $bundledNode) { return $bundledNode }
    throw 'Node.js 20 or newer is needed only for the frontend checks.'
}
