#!/usr/bin/env pwsh
# Copyright (c) Microsoft. All rights reserved.

<#
.SYNOPSIS
    Bumps the .NET package version and updates its date suffix.

.DESCRIPTION
    Updates VersionPrefix by incrementing the selected version component and
    resetting lower components to zero. Defaults to a minor version bump. Sets
    DateSuffix to the release date in yyMMdd format. Leaves RCNumber and all
    other package properties unchanged, preserving file formatting and UTF-8 BOM.
    Each invocation increments the selected version component again.

.PARAMETER ReleaseDate
    Release date for DateSuffix. Defaults to today's local date.

.PARAMETER Path
    Package properties file. Defaults to dotnet\nuget\nuget-package.props,
    resolved relative to this script, independently of the working directory.

.PARAMETER VersionPart
    Version component to increment: Major, Minor, or Patch. Defaults to Minor.

.EXAMPLE
    .\dotnet\eng\scripts\Update-PackageVersion.ps1

.EXAMPLE
    .\dotnet\eng\scripts\Update-PackageVersion.ps1 -VersionPart Major
    Increments the major version and resets minor and patch to zero.

.EXAMPLE
    .\dotnet\eng\scripts\Update-PackageVersion.ps1 -VersionPart Patch
    Increments the patch version, leaving major and minor unchanged.

.EXAMPLE
    .\dotnet\eng\scripts\Update-PackageVersion.ps1 -ReleaseDate '2026-10-23' -WhatIf
    Previews a minor version bump with DateSuffix set to 261023.
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [datetime]$ReleaseDate = (Get-Date),

    [ValidateNotNullOrEmpty()]
    [string]$Path = (Join-Path $PSScriptRoot '..\..\nuget\nuget-package.props'),

    [ValidateSet('Major', 'Minor', 'Patch')]
    [string]$VersionPart = 'Minor'
)

$ErrorActionPreference = 'Stop'

$propsPath = (Resolve-Path -LiteralPath $Path).ProviderPath
$content = [System.IO.File]::ReadAllText($propsPath)
$versionMatches = [regex]::Matches($content, '<VersionPrefix>(?<Version>[0-9]+\.[0-9]+\.[0-9]+)</VersionPrefix>')
$dateMatches = [regex]::Matches($content, '<DateSuffix>[0-9]{6}</DateSuffix>')

if ($versionMatches.Count -ne 1) {
    throw "Expected exactly one VersionPrefix in major.minor.patch format in '$propsPath'."
}

if ($dateMatches.Count -ne 1) {
    throw "Expected exactly one DateSuffix in yyMMdd format in '$propsPath'."
}

$version = [version]$versionMatches[0].Groups['Version'].Value
$newVersion = switch ($VersionPart) {
    'Major' { [version]::new(($version.Major + 1), 0, 0).ToString() }
    'Minor' { [version]::new($version.Major, ($version.Minor + 1), 0).ToString() }
    'Patch' { [version]::new($version.Major, $version.Minor, ($version.Build + 1)).ToString() }
}
$dateSuffix = $ReleaseDate.ToString('yyMMdd', [System.Globalization.CultureInfo]::InvariantCulture)
$updatedContent = $content.Replace($versionMatches[0].Value, "<VersionPrefix>$newVersion</VersionPrefix>")
$updatedContent = $updatedContent.Replace($dateMatches[0].Value, "<DateSuffix>$dateSuffix</DateSuffix>")

if ($PSCmdlet.ShouldProcess($propsPath, "Set VersionPrefix to $newVersion and DateSuffix to $dateSuffix")) {
    $bytes = [System.IO.File]::ReadAllBytes($propsPath)
    $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    [System.IO.File]::WriteAllText($propsPath, $updatedContent, [System.Text.UTF8Encoding]::new($hasBom))
    Write-Host "Updated VersionPrefix: $version -> $newVersion; DateSuffix: $dateSuffix"
}
