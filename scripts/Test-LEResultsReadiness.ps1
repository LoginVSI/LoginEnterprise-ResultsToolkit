# Bootstrap checks run before importing the Python engine. No credentials or HTTP here.
[CmdletBinding()]
param(
    [string] $Python,
    [string] $Profile,
    [string] $OutputDirectory,
    [switch] $Live
)
$ErrorActionPreference = 'Stop'
$toolkitRoot = Split-Path $PSScriptRoot -Parent
if (-not $Python) { $Python = Join-Path $toolkitRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    Write-Output '{"ok":false,"code":"python_missing","action":"Install 64-bit Python 3.11 or 3.14 for your user, then create the project .venv. See docs/quickstart.md."}'
    exit 2
}
$bootstrap = @'
import importlib.util, json, platform, struct, sys
missing = [name for name in ('httpx', 'keyring', 'platformdirs', 'cryptography', 'le_results') if importlib.util.find_spec(name) is None]
ok = sys.version_info >= (3, 11) and struct.calcsize('P') == 8 and not missing
print(json.dumps({'ok': ok, 'python': platform.python_version(), 'architecture': platform.machine(), 'bits': struct.calcsize('P') * 8, 'matrix_verified_runtime': sys.version_info[:2] in ((3, 11), (3, 14)), 'missing_dependencies': missing, 'action': 'Use direct .venv executable invocation; install hash-locked requirements and the toolkit if dependencies are missing.'}))
sys.exit(0 if ok else 2)
'@
try {
    $bootstrapOutput = & $Python -I -c $bootstrap 2>$null
    $bootstrapExit = $LASTEXITCODE
} catch {
    $bootstrapOutput = $null
    $bootstrapExit = 2
}
if ($bootstrapOutput) { Write-Output $bootstrapOutput }
else { Write-Output '{"ok":false,"code":"environment_broken","action":"The selected Python cannot start. Preserve the old .venv and recreate it with an explicit installed runtime, then install documented locks."}' }
if ($bootstrapExit -ne 0) { exit 2 }
if ($Profile) {
    $engineArguments = @('-m', 'le_results.cli', 'doctor', '--profile', $Profile)
    if (-not $Live) { $engineArguments += '--offline' }
    if ($OutputDirectory) { $engineArguments += @('--out', $OutputDirectory) }
    & $Python @engineArguments
    exit $LASTEXITCODE
}
exit 0
