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

if (-not (Test-Path $TestContainerProject)) {
    throw "Test container project not found at '$TestContainerProject'."
}

# Hash the test container source so the tag tracks content. If nothing changed, ACR keeps
# the existing image and `docker push` is a no op.
$sourceFiles = git -c core.quotepath=false ls-files $TestContainerProject
$shaInput = $sourceFiles | git hash-object --stdin
$tag = $shaInput.Substring(0, 12)
$image = "$Registry/$Repository`:$tag"

Write-Host "Publishing $TestContainerProject ..." -ForegroundColor Cyan
$out = Join-Path $TestContainerProject "out"
if (Test-Path $out) {
    Remove-Item -Recurse -Force $out
}

dotnet publish $TestContainerProject -c Release -f net10.0 -r linux-musl-x64 --self-contained false -o $out --tl:off | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish failed with exit code $LASTEXITCODE."
}

Write-Host "Building $image ..." -ForegroundColor Cyan
docker build -t $image -f (Join-Path $TestContainerProject "Dockerfile") $TestContainerProject | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "docker build failed with exit code $LASTEXITCODE."
}

Write-Host "Pushing $image ..." -ForegroundColor Cyan
$registryHost = $Registry.Split('.')[0]
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
