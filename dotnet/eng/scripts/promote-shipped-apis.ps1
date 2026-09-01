param(
    [string] $Path = (Join-Path $PSScriptRoot '..\..\src')
)

$ErrorActionPreference = 'Stop'

$root = Resolve-Path $Path
$encoding = [System.Text.UTF8Encoding]::new($true)
$nullableHeader = '#nullable enable'
$promotedFiles = 0
$promotedApis = 0

Get-ChildItem -Path $root -Recurse -Filter 'PublicAPI.Unshipped.txt' | ForEach-Object {
    $unshippedFile = $_.FullName
    $shippedFile = Join-Path $_.DirectoryName 'PublicAPI.Shipped.txt'

    $unshippedLines = if ((Get-Item $unshippedFile).Length -gt 0) {
        Get-Content -Path $unshippedFile -Encoding UTF8 | Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and $_ -ne $nullableHeader
        }
    }
    else {
        @()
    }

    if ($unshippedLines.Count -eq 0) {
        return
    }

    $allLines = [System.Collections.Generic.SortedSet[string]]::new([System.StringComparer]::Ordinal)
    if (Test-Path $shippedFile) {
        Get-Content -Path $shippedFile -Encoding UTF8 | Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and $_ -ne $nullableHeader
        } | ForEach-Object {
            $null = $allLines.Add($_)
        }
    }

    $unshippedLines | ForEach-Object {
        $null = $allLines.Add($_)
    }

    $shippedLines = @($nullableHeader) + @($allLines)
    $shippedContent = [string]::Join("`n", $shippedLines) + "`n"

    [System.IO.File]::WriteAllText($shippedFile, $shippedContent, $encoding)
    [System.IO.File]::WriteAllText($unshippedFile, "$nullableHeader`n", $encoding)

    $promotedFiles++
    $promotedApis += $unshippedLines.Count
    Write-Host "Promoted $($unshippedLines.Count) public API entries in $($_.Directory.Name)."
}

Write-Host "Promoted $promotedApis public API baseline entries across $promotedFiles baseline file(s)."
