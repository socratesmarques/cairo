param(
    [string]$BindHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    & python -m cairo --host $BindHost --port $Port
    $runExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $runExitCode
