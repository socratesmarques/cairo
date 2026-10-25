$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
try {
    & python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & python -m compileall -q cairo tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (Get-Command node -ErrorAction SilentlyContinue) {
        & node tests/test_voice.cjs
        exit $LASTEXITCODE
    }
    exit 0
}
finally { Pop-Location }
