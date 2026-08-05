#requires -Version 7
<#
.SYNOPSIS
  Local smoke test for the Hosted-AgentSkills sample.
.DESCRIPTION
  Publishes the sample, builds the contributor Docker image, runs the container, drives
  two conversations via curl invocations, and asserts that the agent loaded the correct
  Foundry Skill for each prompt (verified via canary tokens in the response).
  Exits non-zero on failure.

  Prerequisites:
    - Docker
    - az login (token is fetched from the host)
    - .env populated with FOUNDRY_PROJECT_ENDPOINT and model deployment
    - Skills provisioned to Foundry (set PROVISION_SAMPLE_SKILLS=true on first run)
.NOTES
  This script is for local Docker debugging only. Running locally the container needs no user
  identity: per-user isolation simply is not triggered. On the Foundry platform the caller identity
  (x-agent-user-id) is supplied automatically for every request.
#>

[CmdletBinding()]
param(
    [int]$Port = 8088,
    [string]$ImageName = 'hosted-agent-skills-smoke',
    [string]$ContainerName = 'hosted-agent-skills-smoke'
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

function Start-Container {
    docker rm -f $ContainerName 2>$null | Out-Null
    docker run -d --name $ContainerName -p ${Port}:8088 `
        -e AGENT_NAME=hosted-agent-skills `
        -e AZURE_BEARER_TOKEN=$bearer `
        --env-file .env `
        $ImageName | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "docker run failed." }
    # Wait for the server to start and download skills from Foundry.
    Write-Host '  Waiting for startup (skill download + server ready) ...'
    Start-Sleep -Seconds 15
}

function Invoke-Agent([string]$Prompt, [string]$PreviousResponseId = $null) {
    $body = @{ input = $Prompt; model = 'hosted-agent-skills' }
    if ($PreviousResponseId) { $body['previous_response_id'] = $PreviousResponseId }
    $json = $body | ConvertTo-Json -Compress
    $resp = Invoke-RestMethod -Method Post -Uri "http://localhost:$Port/responses" -ContentType 'application/json' -Body $json
    return $resp
}

function Get-ResponseText($response) {
    return ($response.output | ForEach-Object { $_.content | ForEach-Object { $_.text } }) -join ' '
}

function Assert-Contains([string]$Haystack, [string]$Needle, [string]$Label) {
    if ($Haystack -notmatch [regex]::Escape($Needle)) {
        throw "FAILED [$Label]: expected response to contain '$Needle' but got: $Haystack"
    }
    Write-Host "PASS  [$Label]: response contains '$Needle'."
}

try {
    Start-Container

    Write-Host '==> Test 1: Routine support question -> support-style skill ...'
    $r1 = Invoke-Agent -Prompt 'Hi, I am Alex. I just want to confirm I can return my tent within 30 days.'
    $text1 = Get-ResponseText $r1
    Assert-Contains $text1 'STYLE-CANARY-3318' 'routine question: support-style canary'

    Write-Host '==> Test 2: Escalation trigger -> escalation-policy skill ...'
    $r2 = Invoke-Agent -Prompt 'I want a $750 refund on Order #A-1042 right now or I am calling my lawyer.'
    $text2 = Get-ResponseText $r2
    Assert-Contains $text2 'ESC-CANARY-7742' 'escalation trigger: escalation-policy canary'

    Write-Host ''
    Write-Host '==> All smoke assertions passed.'
}
finally {
    docker rm -f $ContainerName 2>$null | Out-Null
}