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

    [string] $TestContainerProject = "dotnet/tests/Foundry.Hosting.IntegrationTests.TestContainer",

    # Explicit opt-in for the no-rebuild fast path. CI sets this after running the
    # "Build Foundry hosted IT (and its deps)" step, which guarantees the prebuilt
    # library DLLs match current source. Off by default so local invocations always
    # let publish rebuild ProjectReferences and never produce an image whose tag is
    # computed from current source while the contents come from a stale build.
    [switch] $UsePrebuiltProjectReferences
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

# Conditionally tell publish to skip rebuilding ProjectReferences and consume the
# prebuilt library DLLs in place. This avoids two failure modes that arise when
# the CI workflow runs a `dotnet build` of the same library projects immediately
# before this script:
#   1) MSB3026 "file is being used by another process" when publish's MSBuild
#      tries to overwrite src/<lib>/bin/Release/net10.0/<lib>.dll while the
#      previous build's shared-compilation server still holds a file handle.
#   2) Publish needlessly rebuilding identical managed (RID-agnostic) library
#      DLLs that prebuild already produced.
# Gated on -UsePrebuiltProjectReferences (a strict opt-in) instead of marker
# detection, because a developer machine may have a stale Release build of the
# libraries from days ago; using those would silently produce an image whose
# content is older than the source the tag is computed from.
$publishExtraArgs = @()
if ($UsePrebuiltProjectReferences) {
    Write-Host "-UsePrebuiltProjectReferences: skipping ProjectReference rebuild." -ForegroundColor DarkGray
    $publishExtraArgs += "-p:BuildProjectReferences=false"
} else {
    # Preflight: in default (rebuild) mode, publish propagates RuntimeIdentifier=linux-musl-x64
    # to library ProjectReferences and writes their intermediates to a RID-suffixed obj path
    # (e.g. obj/Release/net10.0/linux-musl-x64/). DefaultItemExcludes follows the new
    # IntermediateOutputPath, so any *.AssemblyInfo.cs left in obj/Release/net10.0/ from a
    # prior `dotnet build` is no longer excluded and gets picked up by the **/*.cs Compile
    # glob, producing CS0579 "duplicate attribute" errors. Detect that state up front and
    # tell the user exactly how to recover.
    $staleObjProbes = @(
        "dotnet/src/Microsoft.Agents.AI.Foundry.Hosting/obj/Release/net10.0",
        "dotnet/src/Microsoft.Agents.AI.Foundry/obj/Release/net10.0",
        "dotnet/src/Microsoft.Agents.AI/obj/Release/net10.0",
        "dotnet/src/Microsoft.Agents.AI.Abstractions/obj/Release/net10.0"
    )
    $stale = @($staleObjProbes | Where-Object { Test-Path (Join-Path $_ "*.AssemblyInfo.cs") })
    if ($stale.Count -gt 0) {
        $msg = @(
            "Detected prior Release/net10.0 build outputs in:"
            ($stale | ForEach-Object { "  - $_" })
            ""
            "Publish would propagate -r linux-musl-x64 to those ProjectReferences and the"
            "leftover obj/Release/net10.0/*.AssemblyInfo.cs files would cause CS0579 duplicate"
            "attribute errors. Pick one:"
            "  (a) Pass -UsePrebuiltProjectReferences (skips ProjectReference rebuild and"
            "      uses the existing src/<lib>/bin/Release/net10.0/*.dll outputs in place)."
            "      Only safe when you know those DLLs match current source - this is the path"
            "      CI uses immediately after its 'Build Foundry hosted IT (and its deps)' step."
            "  (b) Remove the stale obj/Release trees, e.g.:"
            "        Remove-Item -Recurse -Force dotnet/src/Microsoft.Agents.AI*/obj/Release"
            "      and re-run."
        ) -join "`n"
        throw $msg
    }
    Write-Host "Letting publish build ProjectReferences (pass -UsePrebuiltProjectReferences in CI to skip)." -ForegroundColor DarkGray
}

dotnet publish $TestContainerProject -c Release -f net10.0 -r linux-musl-x64 --self-contained false -o $out @publishExtraArgs --tl:off | Out-Host
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
