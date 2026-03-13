#!/usr/bin/env pwsh
# Copyright (c) Microsoft. All rights reserved.

<#
.SYNOPSIS
    Generates a filtered .slnx solution file by removing projects that don't match the specified criteria.

.DESCRIPTION
    Parses a .slnx solution file and applies one or more filters:
    - Removes projects that don't support the specified target framework (via MSBuild query).
    - Optionally removes all sample projects (under samples/).
    - Optionally filters test projects by name pattern (e.g., only *UnitTests*).
    Writes the filtered solution to the specified output path and prints the path.

.PARAMETER Solution
    Path to the source .slnx solution file.

.PARAMETER TargetFramework
    The target framework to filter by (e.g., net10.0, net472).

.PARAMETER Configuration
    Optional MSBuild configuration used when querying TargetFrameworks. Defaults to Debug.

.PARAMETER TestProjectNameFilter
    Optional wildcard pattern to filter test project names (e.g., *UnitTests*, *IntegrationTests*).
    When specified, only test projects whose filename matches this pattern are kept.

.PARAMETER ExcludeSamples
    When specified, removes all projects under the samples/ directory from the solution.

.PARAMETER OutputPath
    Optional output path for the filtered .slnx file. If not specified, a temp file is created.

.EXAMPLE
    # Generate a filtered solution and run tests
    $filtered = ./dotnet/eng/scripts/New-FilteredSolution.ps1 -Solution dotnet/agent-framework-dotnet.slnx -TargetFramework net472
    dotnet test --solution $filtered --no-build -f net472

.EXAMPLE
    # Generate a solution with only unit test projects
    ./dotnet/eng/scripts/New-FilteredSolution.ps1 -Solution dotnet/agent-framework-dotnet.slnx -TargetFramework net10.0 -TestProjectNameFilter "*UnitTests*" -OutputPath filtered-unit.slnx

.EXAMPLE
    # Inline usage with dotnet test (PowerShell)
    dotnet test --solution (./dotnet/eng/scripts/New-FilteredSolution.ps1 -Solution dotnet/agent-framework-dotnet.slnx -TargetFramework net472) --no-build -f net472
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Solution,

    [Parameter(Mandatory)]
    [string]$TargetFramework,

    [string]$Configuration = "Debug",

    [string]$TestProjectNameFilter,

    [switch]$ExcludeSamples,

    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

# Resolve the solution path
$solutionPath = Resolve-Path $Solution
$solutionDir = Split-Path $solutionPath -Parent

if (-not $OutputPath) {
    $OutputPath = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "filtered-$(Split-Path $solutionPath -Leaf)")
}

# Parse the .slnx XML
[xml]$slnx = Get-Content $solutionPath -Raw

$removed = @()
$kept = @()

# Remove sample projects if requested
if ($ExcludeSamples) {
    $sampleProjects = $slnx.SelectNodes("//Project[contains(@Path, 'samples/')]")
    foreach ($proj in $sampleProjects) {
        $projRelPath = $proj.GetAttribute("Path")
        Write-Verbose "Removing (sample): $projRelPath"
        $removed += $projRelPath
        $proj.ParentNode.RemoveChild($proj) | Out-Null
    }
    Write-Host "Removed $($sampleProjects.Count) sample project(s)." -ForegroundColor Yellow
}

# Filter all remaining projects by target framework
$allProjects = $slnx.SelectNodes("//Project")

foreach ($proj in $allProjects) {
    $projRelPath = $proj.GetAttribute("Path")
    $projFullPath = Join-Path $solutionDir $projRelPath
    $projFileName = Split-Path $projRelPath -Leaf
    $isTestProject = $projRelPath -like "*tests/*"

    # Filter test projects by name pattern if specified
    if ($isTestProject -and $TestProjectNameFilter -and ($projFileName -notlike $TestProjectNameFilter)) {
        Write-Verbose "Removing (name filter): $projRelPath"
        $removed += $projRelPath
        $proj.ParentNode.RemoveChild($proj) | Out-Null
        continue
    }

    if (-not (Test-Path $projFullPath)) {
        Write-Verbose "Project not found, keeping in solution: $projRelPath"
        $kept += $projRelPath
        continue
    }

    # Query the project's target frameworks using MSBuild
    $targetFrameworks = & dotnet msbuild $projFullPath -getProperty:TargetFrameworks -p:Configuration=$Configuration -nologo 2>$null
    $targetFrameworks = $targetFrameworks.Trim()

    if ($targetFrameworks -like "*$TargetFramework*") {
        Write-Verbose "Keeping: $projRelPath (targets: $targetFrameworks)"
        $kept += $projRelPath
    }
    else {
        Write-Verbose "Removing: $projRelPath (targets: $targetFrameworks, missing: $TargetFramework)"
        $removed += $projRelPath
        $proj.ParentNode.RemoveChild($proj) | Out-Null
    }
}

# Write the filtered solution
$slnx.Save($OutputPath)

# Report results to stderr so stdout is clean for piping
Write-Host "Filtered solution written to: $OutputPath" -ForegroundColor Green
if ($removed.Count -gt 0) {
    Write-Host "Removed $($removed.Count) project(s):" -ForegroundColor Yellow
    foreach ($r in $removed) {
        Write-Host "  - $r" -ForegroundColor Yellow
    }
}
Write-Host "Kept $($kept.Count) project(s)." -ForegroundColor Green

# Output the path for piping
Write-Output $OutputPath
