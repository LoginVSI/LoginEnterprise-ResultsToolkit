# Thin native Windows entry point. Does not forward secrets or use WSL.
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Arguments
)
$ErrorActionPreference = 'Stop'
$toolkitRoot = Split-Path $PSScriptRoot -Parent
$toolkitPython = Join-Path $toolkitRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $toolkitPython)) {
    throw 'Install the native Windows environment first: py -3 -m venv .venv'
}
& $toolkitPython -I -m le_results.cli @Arguments
exit $LASTEXITCODE
