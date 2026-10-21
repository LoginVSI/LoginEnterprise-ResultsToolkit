[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Package,
    [ValidateSet('PowerBI','MicrosoftPowerBI')][string]$ConnectorFolder = 'PowerBI',
    [string]$BackupDirectory,
    [string]$DocumentsDirectory,
    [ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedSha256,
    [switch]$UnblockDownloadedPackage,
    [switch]$DiagnoseOnly
)
$ErrorActionPreference = 'Stop'
$moves = @()
$placed = $false
function Get-ToolkitHash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','') }
    finally { $sha.Dispose(); $stream.Dispose() }
}
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $packagePath = (Resolve-Path -LiteralPath $Package).Path
    $zip = [IO.Compression.ZipFile]::OpenRead($packagePath)
    try {
        $entry = $zip.GetEntry('ResultsToolkit.pq')
        $entries = @($zip.Entries | ForEach-Object { $_.FullName } | Sort-Object)
        $expectedEntries = @('ResultsToolkit.pq','icon16.png','icon32.png') | Sort-Object
        if (($entries -join '|') -cne ($expectedEntries -join '|')) { throw 'Package must contain exactly the toolkit source and two expected icons.' }
        if ($null -eq $entry -or $entry.Length -gt 1048576) { throw 'Package needs the bounded ResultsToolkit.pq source entry.' }
        $reader = New-Object IO.StreamReader($entry.Open())
        try { $source = $reader.ReadToEnd() } finally { $reader.Dispose() }
        if ($source -notmatch 'shared ResultsToolkit\.Rows\s*=' -or $source -notmatch 'DataSource.Kind="ResultsToolkit"') { throw 'Package does not export the expected toolkit function/kind.' }
    } finally { $zip.Dispose() }
    $documents = $DocumentsDirectory
    if (-not $documents) { $documents = [Environment]::GetFolderPath('MyDocuments') }
    if ([string]::IsNullOrWhiteSpace($documents)) { throw 'Windows did not resolve the current user Documents folder.' }
    $documents = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($documents).TrimEnd('\')
    $folders = @((Join-Path $documents 'Power BI Desktop\Custom Connectors'), (Join-Path $documents 'Microsoft Power BI Desktop\Custom Connectors'))
    $targetFolder = $folders[0]
    if ($ConnectorFolder -eq 'MicrosoftPowerBI') { $targetFolder = $folders[1] }
    $target = Join-Path $targetFolder 'ResultsToolkit.mez'
    foreach ($folder in $folders) {
        if (Test-Path -LiteralPath $folder) {
            $other = @(Get-ChildItem -LiteralPath $folder -File | Where-Object { $_.BaseName -like 'ResultsToolkit*' -and $_.BaseName -ne 'ResultsToolkit' -and $_.Extension -in @('.mez','.pq','.m','.pqx') })
            if ($other.Count -gt 0) { throw 'A differently named toolkit registration exists. Inspect it before installing another toolkit package.' }
        }
    }
    $existing = @($folders | ForEach-Object {
        if (Test-Path -LiteralPath $_) {
            Get-ChildItem -LiteralPath $_ -File | Where-Object { $_.BaseName -eq 'ResultsToolkit' -and $_.Extension -in @('.mez','.pq','.m','.pqx') }
        }
    })
    $digest = Get-ToolkitHash $packagePath
    if ($ExpectedSha256 -and $digest -ne $ExpectedSha256) { throw 'Package hash differs from the independently approved checksum; nothing installed.' }
    if ($DiagnoseOnly) {
        [pscustomobject]@{Documents=$documents;Target=$target;ExistingToolkitFiles=@($existing.FullName);PackageSHA256=$digest;SourceExportPresent=$true;HostLoaded='unverified';SecuritySettingsChanged=$false} | ConvertTo-Json -Depth 4
        exit 0
    }
    $nativeDocuments = [Environment]::GetFolderPath('MyDocuments')
    if ([IO.Path]::GetFullPath($documents).TrimEnd('\') -eq [IO.Path]::GetFullPath($nativeDocuments).TrimEnd('\')) {
        if (Get-Process -Name PBIDesktop,PBIDesktopStore -ErrorAction SilentlyContinue) { throw 'Close Power BI Desktop after saving edits, then rerun installation. No process was stopped.' }
    }
    if ($existing.FullName -contains $packagePath) { throw 'Use a package outside the connector registration folders as installation input.' }
    if (-not $BackupDirectory) {
        $BackupDirectory = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) ('LoginEnterpriseResultsToolkit\connector-backups\' + [Guid]::NewGuid().ToString())
    }
    $backup = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($BackupDirectory)
    foreach ($folder in $folders) {
        $resolvedFolder = [IO.Path]::GetFullPath($folder).TrimEnd('\') + '\'
        if (($backup.TrimEnd('\') + '\').StartsWith($resolvedFolder,[StringComparison]::OrdinalIgnoreCase)) { throw 'Keep backups outside connector registration folders.' }
    }
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    New-Item -ItemType Directory -Path $targetFolder -Force | Out-Null
    # Copy verified backups first. Only canonical toolkit files are moved, never other connectors.
    $moves = @()
    for ($i=0; $i -lt $existing.Count; $i++) {
        $old = $existing[$i]
        $oldPath = [IO.Path]::GetFullPath($old.FullName)
        $allowed = $false
        foreach ($folder in $folders) { if ([IO.Path]::GetDirectoryName($oldPath) -eq [IO.Path]::GetFullPath($folder)) { $allowed=$true } }
        if (-not $allowed) { throw 'Resolved toolkit path is outside the inspected user connector folders.' }
        $saved = Join-Path $backup ($i.ToString() + '-' + $old.Name)
        if (Test-Path -LiteralPath $saved) { throw 'Use a new backup directory; existing backup is preserved.' }
        Copy-Item -LiteralPath $oldPath -Destination $saved
        if ((Get-ToolkitHash $oldPath) -ne (Get-ToolkitHash $saved)) { throw 'Backup hash differs; installation stopped.' }
        $moves += [pscustomobject]@{Original=$oldPath;Backup=$saved}
    }
    $staged = Join-Path $targetFolder ('ResultsToolkit-' + [Guid]::NewGuid().ToString() + '.tmp')
    Copy-Item -LiteralPath $packagePath -Destination $staged
    if ((Get-ToolkitHash $staged) -ne $digest) { throw 'Staged package hash differs; installation stopped.' }
    if ($UnblockDownloadedPackage) { Unblock-File -LiteralPath $staged }
    foreach ($item in $moves) {
        # The resolved source paths were checked above. Preserve every old file as a backup.
        $disabled = $item.Backup + '.original'
        Move-Item -LiteralPath $item.Original -Destination $disabled
    }
    Move-Item -LiteralPath $staged -Destination $target
    $placed = $true
    [pscustomobject]@{Target=$target;PackageSHA256=$digest;Backups=$moves;RestartRequired=$true;HostLoaded='unverified';SecuritySettingsChanged=[bool]$UnblockDownloadedPackage;DownloadedFileUnblocked=[bool]$UnblockDownloadedPackage} | ConvertTo-Json -Depth 4
} catch {
    $installError = $_.Exception.Message
    if ($placed -and (Test-Path -LiteralPath $target) -and [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($target)) -eq [IO.Path]::GetFullPath($targetFolder) -and (Get-ToolkitHash $target) -eq $digest) {
        try { Remove-Item -LiteralPath $target }
        catch { [Console]::Error.WriteLine('New package remains at the target; retained backups: ' + $backup) }
    }
    foreach ($item in $moves) {
        if (-not (Test-Path -LiteralPath $item.Original) -and (Test-Path -LiteralPath $item.Backup)) {
            try { Copy-Item -LiteralPath $item.Backup -Destination $item.Original }
            catch { [Console]::Error.WriteLine('Automatic restore failed; retained backup: ' + $item.Backup) }
        }
    }
    if ($staged -and (Test-Path -LiteralPath $staged) -and [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($staged)) -eq [IO.Path]::GetFullPath($targetFolder) -and [IO.Path]::GetExtension($staged) -eq '.tmp') {
        Remove-Item -LiteralPath $staged
    }
    [Console]::Error.WriteLine('Connector installation failed: ' + $installError)
    exit 2
}
