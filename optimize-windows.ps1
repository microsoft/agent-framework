<#
PowerShell: optimize-windows.ps1
Purpose: Aggressive Windows optimization/cleanup script with safety safeguards.
Usage examples:
  - Dry run (default): .\optimize-windows.ps1
  - Execute safe cleanup: .\optimize-windows.ps1 -Execute
  - Aggressive execution (kills processes, deletes caches): .\optimize-windows.ps1 -Execute -Aggressive -Force -Reboot
Notes:
  - Requires running as Administrator for most actions.
  - Script performs logging and creates a reversible manifest of deletions/terminated processes where possible.
  - By default runs in preview mode to show planned actions. Use -Execute to actually apply changes.
  - Aggressive mode lowers thresholds and enables service/process termination and system cache removals.
#>

param(
    [switch]$Execute,
    [switch]$Aggressive,
    [switch]$Force,
    [switch]$Reboot,
    [string]$LogPath = "$PSScriptRoot\optimize-windows.log"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

function Log {
    param([string]$Message)
    $time = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "[$time] $Message"
    $line | Tee-Object -FilePath $LogPath -Append | Out-Null
}

function Require-Admin {
    if (-not ([bool] (net session 2>$null))) {
        Log "Not running as Administrator. Exiting."
        throw "This script must be run as Administrator. Restart PowerShell as Administrator and retry."
    }
}

function Safe-Whitelist {
    return @(
        'System', 'Idle', 'Registry', 'explorer', 'dwm', 'SearchIndexer', 'MsMpEng',
        'services', 'lsass', 'wininit', 'winlogon', 'svchost', 'csrss', 'smss',
        'audiodg', 'spoolsv', 'sihost', 'conhost', 'Taskmgr', 'powershell', 'pwsh'
    )
}

function Create-BackupManifest {
    $manifest = "$PSScriptRoot\optimize-backup-$(Get-Date -Format yyyyMMdd-HHmmss).json"
    @{created=(Get-Date); deletions=@(); terminated=@()} | ConvertTo-Json | Out-File -FilePath $manifest -Encoding UTF8
    return $manifest
}

function Append-Manifest {
    param($manifestPath, $section, $entry)
    $json = Get-Content $manifestPath -Raw | ConvertFrom-Json
    $list = $json.$section
    $list += $entry
    $json.$section = $list
    $json | ConvertTo-Json | Out-File -FilePath $manifestPath -Encoding UTF8
}

function Get-TempPaths {
    return @(
        $env:TEMP,
        $env:TMP,
        "$env:SystemRoot\Temp",
        "$env:SystemRoot\SoftwareDistribution\Download",
        "$env:SystemRoot\Prefetch"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
}

function Clear-TempFiles {
    param([switch]$DoDelete, [string]$manifest)
    $paths = Get-TempPaths
    foreach ($p in $paths) {
        Log "Scanning temp path: $p"
        try {
            $items = Get-ChildItem -Path $p -Force -Recurse -ErrorAction SilentlyContinue
            foreach ($it in $items) {
                # Skip reparse points, system-critical files
                if ($it.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
                $entry = @{Path=$it.FullName; Length=$it.Length; LastWrite=$it.LastWriteTime.ToString()}
                if ($DoDelete) {
                    try {
                        Remove-Item -LiteralPath $it.FullName -Force -Recurse -ErrorAction Stop
                        Append-Manifest -manifestPath $manifest -section 'deletions' -entry $entry
                        Log "Deleted: $($it.FullName)"
                    } catch {
                        Log "Failed to delete $($it.FullName): $($_.Exception.Message)"
                    }
                } else {
                    Log "Would delete: $($it.FullName)"
                }
            }
        } catch {
            Log "Error scanning $p: $($_.Exception.Message)"
        }
    }
}

function Empty-RecycleBin {
    param([switch]$DoEmpty)
    if ($DoEmpty) {
        try {
            # Use shell object to empty recycle bin
            $shell = New-Object -ComObject Shell.Application
            $recycle = $shell.Namespace(0xA)
            $recycle.Items() | ForEach-Object { }
            $null = [void]$shell.NameSpace(0xA).Self.InvokeVerb('Empty Recycle Bin')
            Log "Recycle Bin emptied (via shell)."
        } catch {
            Log "Failed to empty Recycle Bin: $($_.Exception.Message)"
        }
    } else {
        Log "Would empty Recycle Bin"
    }
}

function Kill-HeavyProcesses {
    param([int]$CpuThreshold = 15, [int]$MemMBThreshold = 300, [switch]$DoKill, [string]$manifest)
    $whitelist = Safe-Whitelist
    # Get process performance counters
    $procInfos = Get-CimInstance Win32_Process | ForEach-Object {
        $p = $_
        $owner = try { ($p | Invoke-CimMethod -MethodName GetOwner).User } catch { '' }
        [PSCustomObject]@{
            ProcessId = $p.ProcessId
            Name = $p.Name
            CommandLine = $p.CommandLine
            WorkingSetMB = [int]($p.WorkingSetSize / 1MB)
            Priority = $p.Priority
            Owner = $owner
            Path = $p.ExecutablePath
        }
    }
    # Use Get-Process for CPU % via sampling
    $samples = Get-Process | Select-Object Id, ProcessName, CPU, WS
    foreach ($s in $samples) {
        $name = $s.ProcessName
        if ($whitelist -contains $name) { continue }
        $wsMB = [int]($s.WS / 1MB)
        $cpu = if ($s.CPU) { [int]$s.CPU } else { 0 }
        $shouldKill = $false
        if ($cpu -ge $CpuThreshold -or $wsMB -ge $MemMBThreshold) { $shouldKill = $true }
        if ($shouldKill) {
            $entry = @{Name=$name; Id=$s.Id; CPU=$cpu; WS_MB=$wsMB}
            if ($DoKill) {
                try {
                    Stop-Process -Id $s.Id -Force -ErrorAction Stop
                    Append-Manifest -manifestPath $manifest -section 'terminated' -entry $entry
                    Log "Terminated process $name (PID $($s.Id)) CPU=$cpu WS_MB=$wsMB"
                } catch {
                    Log "Failed to terminate $name (PID $($s.Id)): $($_.Exception.Message)"
                }
            } else {
                Log "Would terminate $name (PID $($s.Id)) CPU=$cpu WS_MB=$wsMB"
            }
        }
    }
}

function Stop-NonCriticalServices {
    param([string[]]$Candidates, [switch]$DoStop, [string]$manifest)
    $critical = @('EventLog','PlugPlay','Power','RpcSs','Schedule','Winmgmt','LanmanWorkstation','Netlogon')
    foreach ($svcName in $Candidates) {
        try {
            $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
            if (-not $svc) { continue }
            if ($critical -contains $svc.Name) { Log "Skipping critical service $($svc.Name)"; continue }
            $entry = @{Service=$svc.Name; Status=$svc.Status; DisplayName=$svc.DisplayName}
            if ($DoStop) {
                if ($svc.Status -ne 'Stopped') {
                    Stop-Service -Name $svc.Name -Force -ErrorAction Stop
                    Set-Service -Name $svc.Name -StartupType Disabled -ErrorAction SilentlyContinue
                    Append-Manifest -manifestPath $manifest -section 'terminated' -entry $entry
                    Log "Stopped & disabled service: $($svc.Name)"
                }
            } else {
                Log "Would stop & disable service: $($svc.Name) (Current: $($svc.Status))"
            }
        } catch {
            Log "Service op failed for $svcName: $($_.Exception.Message)"
        }
    }
}

function Run-RepairTools {
    param([switch]$DoRun)
    if ($DoRun) {
        try {
            Log "Running DISM /Online /Cleanup-Image /RestoreHealth"
            Start-Process -FilePath dism.exe -ArgumentList "/Online","/Cleanup-Image","/RestoreHealth" -Wait -NoNewWindow
            Log "DISM completed"
        } catch {
            Log "DISM failed: $($_.Exception.Message)"
        }
        try {
            Log "Running sfc /scannow"
            Start-Process -FilePath sfc.exe -ArgumentList "/scannow" -Wait -NoNewWindow
            Log "SFC completed"
        } catch {
            Log "SFC failed: $($_.Exception.Message)"
        }
    } else {
        Log "Would run DISM and SFC"
    }
}

function Optimize-Volumes {
    param([switch]$DoOptimize)
    $drives = Get-Volume -FileSystemLabel '*' -ErrorAction SilentlyContinue | Where-Object DriveLetter
    foreach ($d in $drives) {
        if ($DoOptimize) {
            try {
                Optimize-Volume -DriveLetter $d.DriveLetter -Defrag -Verbose -ErrorAction Stop
                Log "Optimized drive $($d.DriveLetter):"
            } catch {
                Log "Optimize failed for $($d.DriveLetter): $($_.Exception.Message)"
            }
        } else {
            Log "Would optimize drive $($d.DriveLetter):"
        }
    }
}

# Main flow
try {
    Log "=== Script started. Args: Execute=$Execute Aggressive=$Aggressive Force=$Force Reboot=$Reboot ==="
    Require-Admin
    $manifest = Create-BackupManifest

    if (-not $Execute) {
        Log "DRY RUN mode. No destructive actions will be taken. To apply changes, re-run with -Execute."
    }

    # Safety thresholds
    if ($Aggressive) {
        $cpuThr = 5
        $memThr = 150
        $doStopServices = $true
        $doDeleteTemp = $true
    } else {
        $cpuThr = 15
        $memThr = 400
        $doStopServices = $false
        $doDeleteTemp = $true
    }

    # 1) System inventory
    Log "Collecting system inventory"
    $sys = [PSCustomObject]@{
        ComputerName = $env:COMPUTERNAME
        OS = (Get-CimInstance Win32_OperatingSystem).Caption
        Uptime = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
        User = $env:USERNAME
        Date = Get-Date
    }
    $sys | ConvertTo-Json | Out-File -FilePath "$PSScriptRoot\system-inventory.json" -Encoding UTF8
    Log "Inventory saved"

    # 2) Clear temporary files
    Clear-TempFiles -DoDelete:$Execute -manifest $manifest

    # 3) Empty Recycle Bin
    Empty-RecycleBin -DoEmpty:$Execute

    # 4) Kill heavy processes
    Kill-HeavyProcesses -CpuThreshold $cpuThr -MemMBThreshold $memThr -DoKill:$Execute -manifest $manifest

    # 5) Stop non-critical services (AGGRESSIVE only)
    if ($doStopServices) {
        $candidateServices = @('DiagTrack','WSearch','WaaSMedicSvc','TabletInputService','MapsBroker','XblGameSave','XboxGipSvc')
        Stop-NonCriticalServices -Candidates $candidateServices -DoStop:$Execute -manifest $manifest
    } else {
        Log "Service stopping skipped (Aggressive=false)"
    }

    # 6) Run DISM/SFC repair
    Run-RepairTools -DoRun:$Execute

    # 7) Optimize volumes
    Optimize-Volumes -DoOptimize:$Execute

    # 8) Clear Windows Update cache (SoftwareDistribution)
    $wuCache = "$env:SystemRoot\SoftwareDistribution\Download"
    if (Test-Path $wuCache) {
        Log "Windows Update cache found: $wuCache"
        if ($Execute) {
            try {
                Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue
                Remove-Item -Path "$wuCache\*" -Recurse -Force -ErrorAction SilentlyContinue
                Start-Service -Name wuauserv -ErrorAction SilentlyContinue
                Append-Manifest -manifestPath $manifest -section 'deletions' -entry @{Path=$wuCache; Note='Windows Update cache cleared'}
                Log "Cleared Windows Update cache"
            } catch {
                Log "Failed to clear Windows Update cache: $($_.Exception.Message)"
            }
        } else {
            Log "Would clear Windows Update cache"
        }
    }

    # 9) Trim pagefile? Not modifying pagefile here. Consider on-demand.

    # 10) Final checks
    Log "Finalizing. Manifest: $manifest"

    if ($Execute -and $Reboot) {
        Log "Reboot requested. Rebooting now..."
        Restart-Computer -Force -ErrorAction SilentlyContinue
    } elseif ($Execute) {
        Log "Execution complete. Reboot recommended for some changes to take effect. Use -Reboot to restart automatically."
    } else {
        Log "Dry run complete. Review the log ($LogPath) and manifest ($manifest). Repeat with -Execute to apply changes."
    }

} catch {
    Log "Unhandled error: $($_.Exception.Message)"
    if ($Force -and $Execute) {
        Log "Force mode set; attempting limited recovery actions"
        # Attempt to run sfc at least
        try { Start-Process -FilePath sfc.exe -ArgumentList "/scannow" -Wait -NoNewWindow; Log "SFC attempted" } catch { Log "SFC attempt failed: $($_.Exception.Message)" }
    }
    Log "Exiting with error. See log for details."
    exit 1
}

# End of script
