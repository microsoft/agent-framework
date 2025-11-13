# Stop any existing dotnet processes on ports 5000 and 5018
$existingProcesses = Get-NetTCPConnection -LocalPort 5000,5018 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($processId in $existingProcesses) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

# Wait a moment for ports to be released
Start-Sleep -Seconds 1

# Build the solution first
Write-Host "Building solution..."
$solutionPath = Join-Path $PSScriptRoot "AGUIDojo.slnx"
dotnet build $solutionPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed. Exiting." -ForegroundColor Red
    exit 1
}
Write-Host "Build completed successfully." -ForegroundColor Green

# Start server in background (no-build since we already built)
$serverPath = Join-Path $PSScriptRoot "AGUIDojoServer"
Start-Process -FilePath "dotnet" -ArgumentList "run", "--no-build" -WorkingDirectory $serverPath -NoNewWindow

# Wait for server to start
Start-Sleep -Seconds 3

# Start client in background (no-build since we already built)
$clientPath = Join-Path $PSScriptRoot "AGUIDojoClient"
Start-Process -FilePath "dotnet" -ArgumentList "run", "--no-build" -WorkingDirectory $clientPath -NoNewWindow

Write-Host "Started AGUIDojoServer on http://localhost:5018"
Write-Host "Started AGUIDojoClient on http://localhost:5000"
