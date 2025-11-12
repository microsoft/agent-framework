$generatedCodeFiles = Get-ChildItem -Name -Path .\bin\Debug\net10.0\Workflows -Filter *.g.cs
Write-Output "x$($generatedCodeFiles.Count)"
foreach ($file in $generatedCodeFiles) {
    $baselineFile = $file -replace '\.g\.cs$', '.cs'
    Write-Output $baselineFile
    Copy-Item -Path ".\bin\Debug\net10.0\Workflows\$file" -Destination ".\Workflows\$baselineFile" -Force
}