param(
    [string] $Path = (Join-Path $PSScriptRoot '..\..\src')
)

$ErrorActionPreference = 'Stop'

$root = Resolve-Path $Path
$nullableHeader = '#nullable enable'
$filesWithUnshippedApis = @()

Get-ChildItem -Path $root -Recurse -Filter 'PublicAPI.Unshipped.txt' | ForEach-Object {
    $entries = if ((Get-Item $_.FullName).Length -gt 0) {
        Get-Content -Path $_.FullName -Encoding UTF8 | Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and $_ -ne $nullableHeader
        }
    }
    else {
        @()
    }

    if ($entries.Count -gt 0) {
        $filesWithUnshippedApis += [PSCustomObject]@{
            Path = $_.FullName
            Count = $entries.Count
        }
    }
}

if ($filesWithUnshippedApis.Count -eq 0) {
    Write-Host 'No unshipped public APIs found.'
    exit 0
}

Write-Error 'Unshipped public APIs must be promoted before publishing released packages.' -ErrorAction Continue
$filesWithUnshippedApis | ForEach-Object {
    Write-Error "$($_.Path): $($_.Count) unshipped public API entr$(if ($_.Count -eq 1) { 'y' } else { 'ies' })" -ErrorAction Continue
}

exit 1
