#!/usr/bin/env pwsh
<#
.SYNOPSIS
Builds and pushes the Foundry.Hosting.IntegrationTests.TestContainer image to a container registry.

.DESCRIPTION
The integration tests in dotnet/tests/Foundry.Hosting.IntegrationTests provision real
Foundry hosted agents that point at a container image. This script builds and pushes that
image, then emits the IT_HOSTED_AGENT_IMAGE=... line that the tests read from the
environment.

.PARAMETER Registry
The container registry login server, e.g. mycompany.azurecr.io. Required. There is no
default because every team and every dev may use a different registry.

.PARAMETER Repository
Image repository name within the registry. Defaults to foundry-hosting-it.

.PARAMETER TestContainerProject
Path to the test container csproj. Defaults to the in repo location.

.EXAMPLE
PS> ./scripts/it-build-image.ps1 -Registry mycompany.azurecr.io
IT_HOSTED_AGENT_IMAGE=mycompany.azurecr.io/foundry-hosting-it:abc123def456

.EXAMPLE
Local dev, set the env var directly:
PS> $env:IT_REGISTRY = "mycompany.azurecr.io"
PS> $env:IT_HOSTED_AGENT_IMAGE = (./scripts/it-build-image.ps1 -Registry $env:IT_REGISTRY | Select-String IT_HOSTED_AGENT_IMAGE).Line.Split('=', 2)[1]

.EXAMPLE
CI workflow, assumes IT_REGISTRY is set in the environment:
- name: Build IT image
  run: pwsh ./scripts/it-build-image.ps1 -Registry $env:IT_REGISTRY | Tee-Object -FilePath $env:GITHUB_ENV
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $Registry,

    [string] $Repository = "foundry-hosting-it",

    [string] $TestContainerProject = "dotnet/tests/Foundry.Hosting.IntegrationTests.TestContainer"
)

$ErrorActionPreference = "Stop"

# Resolve to the repo root regardless of the caller's PWD so all relative paths used below
# (TestContainerProject, the framework src dirs hashed for the image tag) resolve correctly.
# This script lives at <repoRoot>/dotnet/tests/Foundry.Hosting.IntegrationTests/scripts/.
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../../../..")).Path
Push-Location $RepoRoot
try {

if (-not (Test-Path $TestContainerProject)) {
    throw "Test container project not found at '$TestContainerProject' (repo root '$RepoRoot')."
}

# Strip any scheme/trailing slash from the registry, then derive the ACR short name.
$Registry = $Registry -replace '^https?://', '' -replace '/+$', ''
$registryHost = $Registry.Split('.')[0]
if ([string]::IsNullOrWhiteSpace($registryHost)) {
    throw "Could not derive ACR short name from -Registry '$Registry'."
}

# Hash the test container source content AND the source of all referenced framework projects
# so any edit (in TestContainer OR in dotnet/src/Microsoft.Agents.AI.Foundry*/) produces a new
# tag. The TestContainer image embeds compiled output of those projects, so a framework code
# change must invalidate the tag for `docker push` to publish a new layer; a TestContainer-only
# hash silently reused stale images on framework edits.
#
# Keep this list in sync with the `foundryHosting` paths-filter in
# .github/workflows/dotnet-build-and-test.yml so CI gating and image tagging cover the same set.
$hashedDirs = @(
    $TestContainerProject,
    "dotnet/src/Microsoft.Agents.AI.Foundry.Hosting",
    "dotnet/src/Microsoft.Agents.AI.Foundry",
    "dotnet/src/Microsoft.Agents.AI",
    "dotnet/src/Microsoft.Agents.AI.Abstractions",
    "dotnet/src/Microsoft.Agents.AI.Workflows"
)
$sourceFiles = @()
foreach ($dir in $hashedDirs) {
    if (Test-Path $dir) {
        $sourceFiles += @(git -c core.quotepath=false ls-files -- $dir)
    }
}
if ($sourceFiles.Count -eq 0) {
    throw "No tracked files found under any of: $($hashedDirs -join ', ')"
}
$fileHashes = git hash-object -- $sourceFiles
$shaInput = ($fileHashes -join "`n" | git hash-object --stdin).Trim()
$tag = $shaInput.Substring(0, 12)
$image = "$Registry/$Repository`:$tag"

Write-Host "Publishing $TestContainerProject ..." -ForegroundColor Cyan
$out = Join-Path $TestContainerProject "out"
if (Test-Path $out) {
    Remove-Item -Recurse -Force $out
}

# Always tell publish to skip ProjectReference rebuilds via --no-dependencies. Publish
# resolves TestContainer's framework lib references (Foundry, Foundry.Hosting and their
# transitive deps) by reading the prebuilt DLLs at src/<lib>/bin/Release/net10.0/*.dll.
# This:
#   1) Structurally avoids the MSB3026 "file is being used by another process" race that
#      occurs when publish overwrites the same DLL paths a prior `dotnet build` produced
#      while VBCSCompiler from that build still holds file handles.
#   2) Avoids needlessly rebuilding identical managed (RID-agnostic) library DLLs.
# Callers MUST run `dotnet build dotnet/tests/Foundry.Hosting.IntegrationTests/Foundry.Hosting.IntegrationTests.csproj -c Release`
# (or equivalent) first so those prebuilt DLLs exist. The CI workflow does this in the
# preceding "Build Foundry hosted IT (and its deps)" step.
$prebuildProbes = @(
    "dotnet/src/Microsoft.Agents.AI.Foundry/bin/Release/net10.0/Microsoft.Agents.AI.Foundry.dll",
    "dotnet/src/Microsoft.Agents.AI.Foundry.Hosting/bin/Release/net10.0/Microsoft.Agents.AI.Foundry.Hosting.dll"
)
$missingPrebuilds = @($prebuildProbes | Where-Object { -not (Test-Path $_) })
if ($missingPrebuilds.Count -gt 0) {
    $msg = @(
        "Required prebuilt outputs not found:"
        ($missingPrebuilds | ForEach-Object { "  - $_" })
        ""
        "Publish runs with --no-dependencies and consumes prebuilt DLLs in place. Build the"
        "test project first so its ProjectReference closure populates src/<lib>/bin/Release/net10.0/:"
        "  dotnet build dotnet/tests/Foundry.Hosting.IntegrationTests/Foundry.Hosting.IntegrationTests.csproj -c Release"
    ) -join "`n"
    throw $msg
}

dotnet publish $TestContainerProject -c Release -f net10.0 -r linux-musl-x64 --self-contained false --no-dependencies -o $out --tl:off | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish failed with exit code $LASTEXITCODE."
}

Write-Host "Building $image ..." -ForegroundColor Cyan
docker build -t $image -f (Join-Path $TestContainerProject "Dockerfile") $TestContainerProject | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "docker build failed with exit code $LASTEXITCODE."
}

Write-Host "Pushing $image ..." -ForegroundColor Cyan
az acr login -n $registryHost | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "az acr login failed with exit code $LASTEXITCODE."
}

docker push $image | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "docker push failed with exit code $LASTEXITCODE."
}

# Emit the env var line for shells / CI consumption.
"IT_HOSTED_AGENT_IMAGE=$image"

}
finally {
    Pop-Location
}
