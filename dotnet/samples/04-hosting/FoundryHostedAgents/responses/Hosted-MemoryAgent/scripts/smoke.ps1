#requires -Version 7
<#
.SYNOPSIS
  Local smoke test for the Hosted-MemoryAgent sample.
.DESCRIPTION
  Publishes the sample, builds the contributor Docker image, runs the container twice with two
  distinct HOSTED_USER_ISOLATION_KEY values, drives a multi-turn conversation per user via curl
  invocations, and asserts that each user only sees their own remembered details.
  Exits non-zero on failure.

  Prerequisites:
    - Docker
    - az login (token is fetched from the host)
    - .env populated with FOUNDRY_PROJECT_ENDPOINT and model deployments
.NOTES
  This script is for local Docker debugging only. The Foundry platform supplies the isolation
  keys for every inbound request in production and the dev fallback used here must not be
  enabled in production deployments.
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

function Start-Container([string]$UserKey, [string]$ChatKey, [string]$ContainerName) {
    docker rm -f $ContainerName 2>$null | Out-Null
    docker run -d --name $ContainerName -p ${Port}:8088 `
        -e AGENT_NAME=hosted-memory-agent `
        -e AZURE_BEARER_TOKEN=$bearer `
        -e HOSTED_USER_ISOLATION_KEY=$UserKey `
        -e HOSTED_CHAT_ISOLATION_KEY=$ChatKey `
        --env-file .env `
        $ImageName | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "docker run failed for $ContainerName." }
    # Wait briefly for the listener to come up.
    Start-Sleep -Seconds 6
}

function Invoke-Agent([string]$Prompt, [string]$PreviousResponseId = $null) {
    $body = @{ input = $Prompt; model = 'hosted-memory-agent' }
    if ($PreviousResponseId) { $body['previous_response_id'] = $PreviousResponseId }
    $json = $body | ConvertTo-Json -Compress
    $resp = Invoke-RestMethod -Method Post -Uri "http://localhost:$Port/responses" -ContentType 'application/json' -Body $json
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
    Write-Host '==> Phase 1: alice teaches the agent her trip details ...'
    Start-Container -UserKey 'alice' -ChatKey 'alice-chat-1' -ContainerName 'hosted-memory-smoke-alice'
    $r1 = Invoke-Agent -Prompt 'Hi! My name is Taylor and I am planning a hiking trip to Patagonia in November.'
    $r2 = Invoke-Agent -Prompt 'I am travelling with my sister and we love finding scenic viewpoints.' -PreviousResponseId $r1.id

    Write-Host "==> Waiting $RecallDelaySeconds s for memory extraction ..."
    Start-Sleep -Seconds $RecallDelaySeconds

    $r3 = Invoke-Agent -Prompt 'What do you already know about my upcoming trip?' -PreviousResponseId $r2.id
    $aliceText = ($r3.output | ForEach-Object { $_.content | ForEach-Object { $_.text } }) -join ' '
    Assert-Contains $aliceText 'Patagonia' 'alice recall: Patagonia'

    docker rm -f hosted-memory-smoke-alice | Out-Null

    Write-Host '==> Phase 2: bob starts a fresh container with a different user isolation key ...'
    Start-Container -UserKey 'bob' -ChatKey 'bob-chat-1' -ContainerName 'hosted-memory-smoke-bob'
    $b1 = Invoke-Agent -Prompt 'Hello, what trip am I planning?'
    $bobText = ($b1.output | ForEach-Object { $_.content | ForEach-Object { $_.text } }) -join ' '
    Assert-NotContains $bobText 'Patagonia' 'bob isolation: no leak of alice memories'

    Write-Host ''
    Write-Host '==> All smoke assertions passed.'
}
finally {
    docker rm -f hosted-memory-smoke-alice 2>$null | Out-Null
    docker rm -f hosted-memory-smoke-bob 2>$null | Out-Null
}
