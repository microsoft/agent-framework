#requires -Version 7
<#
.SYNOPSIS
  Local smoke test for the Hosted-MemoryAgent sample.
.DESCRIPTION
  Publishes the sample, builds the contributor Docker image, runs ONE container, and drives two
  users (alice, bob) against it by varying the x-agent-user-id request header. Asserts that each
  user only sees their own remembered details. Exits non-zero on failure.

  Prerequisites:
    - Docker
    - az login (token is fetched from the host)
    - .env populated with FOUNDRY_PROJECT_ENDPOINT and model deployments
.NOTES
  The x-agent-user-id header is set here only to simulate distinct users locally. On the Foundry
  platform it is supplied automatically for every request.
#>

[CmdletBinding()]
param(
    [int]$Port = 8088,
    [string]$ImageName = 'hosted-memory-agent-smoke',
    [int]$RecallDelaySeconds = 25
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot/..

if (-not (Test-Path .env)) {
    throw '.env not found. Copy .env.example to .env and fill in FOUNDRY_PROJECT_ENDPOINT.'
}

Write-Host '==> Publishing sample for linux-musl-x64 ...'
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out --tl:off | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'dotnet publish failed.' }

Write-Host '==> Building docker image ...'
docker build -f Dockerfile.contributor -t $ImageName . | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'docker build failed.' }

Write-Host '==> Fetching bearer token ...'
$bearer = az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv
if (-not $bearer) { throw 'Failed to obtain bearer token. Run az login.' }

function Start-Container([string]$ContainerName) {
    docker rm -f $ContainerName 2>$null | Out-Null
    docker run -d --name $ContainerName -p ${Port}:8088 `
        -e AGENT_NAME=hosted-memory-agent `
        -e AZURE_BEARER_TOKEN=$bearer `
        --env-file .env `
        $ImageName | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "docker run failed for $ContainerName." }
    # Wait briefly for the listener to come up.
    Start-Sleep -Seconds 6
}

function Invoke-Agent([string]$Prompt, [string]$UserId, [string]$PreviousResponseId = $null) {
    $body = @{ input = $Prompt; model = 'hosted-memory-agent' }
    if ($PreviousResponseId) { $body['previous_response_id'] = $PreviousResponseId }
    $json = $body | ConvertTo-Json -Compress
    # x-agent-user-id is the identity the Foundry platform injects in production. Sending it locally
    # is how a contributor drives per-user isolation.
    $headers = @{ 'x-agent-user-id' = $UserId }
    $resp = Invoke-RestMethod -Method Post -Uri "http://localhost:$Port/responses" -ContentType 'application/json' -Headers $headers -Body $json
    return $resp
}

function Assert-Contains([string]$Haystack, [string]$Needle, [string]$Label) {
    if ($Haystack -notmatch [regex]::Escape($Needle)) {
        throw "FAILED [$Label]: expected response to contain '$Needle' but got: $Haystack"
    }
    Write-Host "PASS  [$Label]: response contains '$Needle'."
}

function Assert-NotContains([string]$Haystack, [string]$Needle, [string]$Label) {
    if ($Haystack -match [regex]::Escape($Needle)) {
        throw "FAILED [$Label]: response unexpectedly contains '$Needle': $Haystack"
    }
    Write-Host "PASS  [$Label]: response does not contain '$Needle'."
}

try {
    # One container serves BOTH users; per-user isolation is driven purely by the x-agent-user-id
    # header, exactly as the Foundry platform does in production (there the platform sets it).
    Start-Container -ContainerName 'hosted-memory-smoke'

    Write-Host '==> Phase 1: alice teaches the agent her trip details ...'
    $r1 = Invoke-Agent -UserId 'alice' -Prompt 'Hi! My name is Taylor and I am planning a hiking trip to Patagonia in November.'
    $r2 = Invoke-Agent -UserId 'alice' -Prompt 'I am travelling with my sister and we love finding scenic viewpoints.' -PreviousResponseId $r1.id

    Write-Host "==> Waiting $RecallDelaySeconds s for memory extraction ..."
    Start-Sleep -Seconds $RecallDelaySeconds

    $r3 = Invoke-Agent -UserId 'alice' -Prompt 'What do you already know about my upcoming trip?' -PreviousResponseId $r2.id
    $aliceText = ($r3.output | ForEach-Object { $_.content | ForEach-Object { $_.text } }) -join ' '
    Assert-Contains $aliceText 'Patagonia' 'alice recall: Patagonia'

    Write-Host '==> Phase 2: bob asks the SAME container with a different x-agent-user-id ...'
    $b1 = Invoke-Agent -UserId 'bob' -Prompt 'Hello, what trip am I planning?'
    $bobText = ($b1.output | ForEach-Object { $_.content | ForEach-Object { $_.text } }) -join ' '
    Assert-NotContains $bobText 'Patagonia' 'bob isolation: no leak of alice memories'

    Write-Host ''
    Write-Host '==> All smoke assertions passed.'
}
finally {
    docker rm -f hosted-memory-smoke 2>$null | Out-Null
}