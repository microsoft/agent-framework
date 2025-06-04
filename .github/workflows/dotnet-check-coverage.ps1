param (
    [string]$JsonReportPath,
    [double]$CoverageThreshold
)

$jsonContent = Get-Content $JsonReportPath -Raw | ConvertFrom-Json
$coverageBelowThreshold = $false

$nonExperimentalAssemblies = [System.Collections.Generic.HashSet[string]]::new()

$assembliesCollection = @(
    'Microsoft.Agents.Abstractions'
    'Microsoft.Agents'
)

foreach ($assembly in $assembliesCollection) {
    $nonExperimentalAssemblies.Add($assembly)
}

function Get-FormattedValue {
    param (
        [float]$Coverage,
        [bool]$UseIcon = $false
    )
    $formattedNumber = "{0:N1}" -f $Coverage
    $icon = if (-not $UseIcon) { "" } elseif ($Coverage -ge $CoverageThreshold) { '✅' } else { '❌' }
    
    return "$formattedNumber% $icon"
}

$totallines = $jsonContent.summary.totallines
$totalbranches = $jsonContent.summary.totalbranches
$lineCoverage = $jsonContent.summary.linecoverage
$branchCoverage = $jsonContent.summary.branchcoverage

$totalTableData = [PSCustomObject]@{
    'Metric'          = 'Total Coverage'
    'Total Lines'   = Get-FormattedValue -Coverage $totallines
    'Total Branches' = Get-FormattedValue -Coverage $totalbranches
    'Line Coverage'   = Get-FormattedValue -Coverage $lineCoverage
    'Branch Coverage' = Get-FormattedValue -Coverage $branchCoverage
}

$totalTableData | Format-Table -AutoSize

$assemblyTableData = @()

foreach ($assembly in $jsonContent.coverage.assemblies) {
    $assemblyName = $assembly.name
    $assemblyLineCoverage = $assembly.coverage
    $assemblyBranchCoverage = $assembly.branchcoverage
    $assemblyTotallines = $assembly.totallines
    $assemblyTotalbranches = $assembly.totalbranches
    
    $isNonExperimentalAssembly = $nonExperimentalAssemblies -contains $assemblyName

    $lineCoverageFailed = $assemblyLineCoverage -lt $CoverageThreshold -and $assemblyTotallines -gt 0
    $branchCoverageFailed = $assemblyBranchCoverage -lt $CoverageThreshold -and $assemblyTotalbranches -gt 0

    if ($isNonExperimentalAssembly -and ($lineCoverageFailed -or $branchCoverageFailed)) {
        $coverageBelowThreshold = $true
    }

    $assemblyTableData += [PSCustomObject]@{
        'Assembly Name' = $assemblyName
        'Line'          = Get-FormattedValue -Coverage $assemblyLineCoverage -UseIcon $isNonExperimentalAssembly
        'Branch'        = Get-FormattedValue -Coverage $assemblyBranchCoverage -UseIcon $isNonExperimentalAssembly
    }
}

$sortedTable = $assemblyTableData | Sort-Object {
    $nonExperimentalAssemblies -contains $_.'Assembly Name'
} -Descending

$sortedTable | Format-Table -AutoSize

if ($coverageBelowThreshold) {
    Write-Host "Code coverage is lower than defined threshold: $CoverageThreshold. Stopping the task."
    exit 1
}
