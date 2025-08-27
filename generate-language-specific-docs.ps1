# Delete all files in the ./user-documentation-dotnet directory.
Get-ChildItem -Path ./user-documentation-dotnet -Recurse | Remove-Item -Force -Recurse
# Delete all files in the ./user-documentation-python directory.
Get-ChildItem -Path ./user-documentation-python -Recurse | Remove-Item -Force -Recurse

$scriptDirectory = $PSScriptRoot
$workspaceRoot = Resolve-Path "$scriptDirectory"
$userDocRoot = Join-Path $workspaceRoot "user-documentation"
$dotnetOutputRoot = Join-Path $workspaceRoot "user-documentation-dotnet"
$pythonOutputRoot = Join-Path $workspaceRoot "user-documentation-python"

# Copy all files from ./user-documentation to ./user-documentation-dotnet and ./user-documentation-python
Get-ChildItem -Path $userDocRoot -Recurse | ForEach-Object {
    if (-not $_.PSIsContainer) {
        $relativePath = $_.FullName.Substring($userDocRoot.Length + 1)
        $dotnetDestination = Join-Path $dotnetOutputRoot $relativePath
        $pythonDestination = Join-Path $pythonOutputRoot $relativePath

        # Create output folder if needed
        $destinationDir = Split-Path $dotnetDestination -Parent
        if (-not (Test-Path $destinationDir)) {
            New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
        }

        $destinationDir = Split-Path $pythonDestination -Parent
        if (-not (Test-Path $destinationDir)) {
            New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
        }

        Write-Host "Copying $($_.FullName) to $dotnetDestination"
        Write-Host "Copying $($_.FullName) to $pythonDestination"

        # Copy the file
        Copy-Item -Path $_.FullName -Destination $dotnetDestination -Force
        Copy-Item -Path $_.FullName -Destination $pythonDestination -Force

        # Read the contents of the copied file
        $content = Get-Content -Path $dotnetDestination -Raw
        # Remove the python sections
        $pattern = '(?s)(::: zone pivot="programming-language-python"\s*).*?(::: zone-end)\r?\n'
        $content = [regex]::Replace($content, $pattern, '')
        # Remove the java sections
        $pattern = '(?s)(::: zone pivot="programming-language-java"\s*).*?(::: zone-end)\r?\n'
        $content = [regex]::Replace($content, $pattern, '')
        # Remove the csharp markers
        $pattern = '(?s)(::: zone pivot="programming-language-csharp"\s\r?\n*)'
        $content = [regex]::Replace($content, $pattern, '')
        # Remove the csharp markers
        $pattern = '(?s)(::: zone-end)\r?\n'
        $content = [regex]::Replace($content, $pattern, '')
        # Write the modified contents back
        Set-Content -Path $dotnetDestination -Value $content

        # Read the contents of the copied file
        $content = Get-Content -Path $pythonDestination -Raw
        # Remove the csharp sections
        $pattern = '(?s)(::: zone pivot="programming-language-csharp"\s*).*?(::: zone-end)\r?\n'
        $content = [regex]::Replace($content, $pattern, '')
        # Remove the java sections
        $pattern = '(?s)(::: zone pivot="programming-language-java"\s*).*?(::: zone-end)\r?\n'
        $content = [regex]::Replace($content, $pattern, '')
        # Remove the csharp markers
        $pattern = '(?s)(::: zone pivot="programming-language-python"\s\r?\n*)'
        $content = [regex]::Replace($content, $pattern, '')
        # Remove the python markers
        $pattern = '(?s)(::: zone-end)\r?\n'
        $content = [regex]::Replace($content, $pattern, '')
        # Write the modified contents back
        Set-Content -Path $pythonDestination -Value $content
    }
}