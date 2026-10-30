# Register, inspect or remove a Windows Task Scheduler entry for `le-results job run`.
# Safe by default: without -Apply it only prints what it would do. It never picks a cadence,
# never stores a password and never enables unattended execution on its own.
#
#   Dry run:   .\Register-LEResultsJob.ps1 -Config D:\jobs\job.json -OutRoot D:\reports -At 06:30 -DaysInterval 1
#   Register:  add -Apply (and -Disabled to create it switched off)
#   Status:    .\Register-LEResultsJob.ps1 -TaskName LEResults-weekly -Show
#   Remove:    .\Register-LEResultsJob.ps1 -TaskName LEResults-weekly -Unregister -Apply
[CmdletBinding()]
param(
    [string] $TaskName = 'LEResults-job',
    [string] $Config,
    [string] $OutRoot,
    [string] $At,
    [int] $DaysInterval = 0,
    [string] $Python,
    [switch] $Apply,
    [switch] $Disabled,
    [switch] $Unregister,
    [switch] $Show
)
$ErrorActionPreference = 'Stop'

if ($Show) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) { Write-Output "No task named $TaskName."; exit 1 }
    $info = $task | Get-ScheduledTaskInfo
    [pscustomobject]@{
        Task = $TaskName; State = [string]$task.State; RunsAs = $task.Principal.UserId
        LogonType = [string]$task.Principal.LogonType; LastRun = $info.LastRunTime
        LastResult = $info.LastTaskResult; NextRun = $info.NextRunTime
    } | Format-List
    Write-Output "LastResult 0 = success, 2 = job failed (see status.json), 3 = skipped, another run active."
    exit 0
}

if ($Unregister) {
    if (-not $Apply) { Write-Output "Dry run: would remove task $TaskName. Add -Apply to remove it."; exit 0 }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Removed task $TaskName. Job output folders are untouched."
    exit 0
}

if (-not $Config -or -not $OutRoot) { throw 'Give -Config (job file) and -OutRoot (output folder).' }
if (-not $At -or $DaysInterval -lt 1) {
    throw 'Choose the schedule explicitly: -At HH:mm and -DaysInterval N. No default cadence is assumed.'
}
$configPath = (Resolve-Path -LiteralPath $Config).Path
$outPath = [System.IO.Path]::GetFullPath($OutRoot)
$toolkitRoot = Split-Path $PSScriptRoot -Parent
if (-not $Python) { $Python = Join-Path $toolkitRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python)) { throw "Python not found at $Python. Pass -Python or install the environment." }
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = "-I -m le_results.cli job run --config `"$configPath`" --out-root `"$outPath`""

Write-Output "Task      : $TaskName"
Write-Output "Runs as   : $identity (interactive logon only; the native vault must belong to this account)"
Write-Output "Command   : `"$Python`" $arguments"
Write-Output "Schedule  : every $DaysInterval day(s) at $At"
Write-Output "Enabled   : $(-not $Disabled)"
if (-not $Apply) { Write-Output "Dry run only. Nothing was registered. Add -Apply to register."; exit 0 }

$action = New-ScheduledTaskAction -Execute $Python -Argument $arguments -WorkingDirectory $outPath
$trigger = New-ScheduledTaskTrigger -Daily -DaysInterval $DaysInterval -At $At
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -StartWhenAvailable:$false
if ($Disabled) { $settings.Enabled = $false }
New-Item -ItemType Directory -Force -Path $outPath | Out-Null
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Write-Output "Registered $TaskName. Check with -Show; remove with -Unregister -Apply."
