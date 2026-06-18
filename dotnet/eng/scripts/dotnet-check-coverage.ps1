param (
    [string]$JsonReportPath,
    [double]$CoverageThreshold
)

$jsonContent = Get-Content $JsonReportPath -Raw | ConvertFrom-Json
$coverageBelowThreshold = $false

$nonExperimentalAssemblies = [System.Collections.Generic.HashSet[string]]::new()

$assembliesCollection = @(
    'Microsoft.Agents.AI.Abstractions'
    'Microsoft.Agents.AI'
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
    'Total Lines'     = $totallines
    'Total Branches'  = $totalbranches
    'Line Coverage'   = Get-FormattedValue -Coverage $lineCoverage
    'Branch Coverage' = Get-FormattedValue -Coverage $branchCoverage
}

$totalTableData | Format-Table -AutoSize

$assemblyTableData = @()

foreach ($assembly in $jsonContent.coverage.assemblies) {
    $assemblyName = $assembly.name
    $assemblyTotallines = $assembly.totallines
    $assemblyTotalbranches = $assembly.totalbranches
    $assemblyLineCoverage = $assembly.coverage
    $assemblyBranchCoverage = $assembly.branchcoverage
    
    $isNonExperimentalAssembly = $nonExperimentalAssemblies -contains $assemblyName

    $lineCoverageFailed = $assemblyLineCoverage -lt $CoverageThreshold -and $assemblyTotallines -gt 0
    $branchCoverageFailed = $assemblyBranchCoverage -lt $CoverageThreshold -and $assemblyTotalbranches -gt 0

    if ($isNonExperimentalAssembly -and ($lineCoverageFailed -or $branchCoverageFailed)) {
        $coverageBelowThreshold = $true
    }

    $assemblyTableData += [PSCustomObject]@{
        'Assembly Name' = $assemblyName
        'Total Lines'     = $assemblyTotallines
        'Total Branches'  = $assemblyTotalbranches
        'Line Coverage'   = Get-FormattedValue -Coverage $assemblyLineCoverage -UseIcon $isNonExperimentalAssembly
        'Branch Coverage' = Get-FormattedValue -Coverage $assemblyBranchCoverage -UseIcon $isNonExperimentalAssembly
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
