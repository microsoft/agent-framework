#requires -Version 7.0
<#
.SYNOPSIS
  One-time bootstrap of stable hosted agents for the Foundry.Hosting.IntegrationTests suite.

.DESCRIPTION
  The IT fixture targets stable, scenario-keyed agent names (e.g. it-happy-path) and only
  manages versions on each test run. The agent itself must already exist AND its managed
  identity must hold the Azure AI User role on the project scope, otherwise inbound
  inference calls fail with HTTP 500 PermissionDenied.

  This script idempotently creates each scenario agent (with a placeholder version) and
  grants Azure AI User on the project to its managed identity. Re-run it safely; existing
  agents and role assignments are left in place.

.PARAMETER ProjectEndpoint
  Foundry project endpoint, e.g. https://<account>.services.ai.azure.com/api/projects/<project>

.PARAMETER Image
  Container image reference for the placeholder version (e.g. <acr>.azurecr.io/foundry-hosting-it:<tag>).
  Use the value emitted by scripts/it-build-image.ps1.

.NOTES
  Per-scenario data-plane RBAC (e.g. `Search Index Data Reader` on the Azure AI Search service
  for the `azure-search-rag` scenario) is intentionally NOT performed by this script. Search,
  Cosmos, and other backing services are treated as pre-existing infrastructure. Grant the
  scenario-specific data role to the agent's managed identity manually after the first run
  (see dotnet/tests/Foundry.Hosting.IntegrationTests/README.md).

.EXAMPLE
  ./it-bootstrap-agents.ps1 `
    -ProjectEndpoint "https://my-acct.services.ai.azure.com/api/projects/my-proj" `
    -Image "myacr.azurecr.io/foundry-hosting-it:abc123"
#>
param(
    [Parameter(Mandatory)] [string] $ProjectEndpoint,
    [Parameter(Mandatory)] [string] $Image
)

$ErrorActionPreference = 'Stop'

$Scenarios = @(
    'happy-path',
    'tool-calling',
    'tool-calling-approval',
    'mcp-toolbox',
    'custom-storage',
    'azure-search-rag',
    'session-files'
)

# Resolve project ARM scope from the endpoint.
$endpointUri = [Uri]$ProjectEndpoint
$accountName = $endpointUri.Host.Split('.')[0]
$projectName = ($endpointUri.AbsolutePath.TrimEnd('/') -split '/')[-1]
$accountInfo = az cognitiveservices account list --query "[?name=='$accountName'].{name:name, rg:resourceGroup, sub:id}" | ConvertFrom-Json
if (-not $accountInfo) { throw "Could not find Cognitive Services account '$accountName'." }
$rg = $accountInfo[0].rg
$sub = ($accountInfo[0].sub -split '/')[2]
$projectScope = "/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.CognitiveServices/accounts/$accountName/projects/$projectName"
Write-Host "Project scope: $projectScope"

$tok = az account get-access-token --resource "https://ai.azure.com" --query accessToken -o tsv
$headers = @{
    Authorization = "Bearer $tok"
    'Foundry-Features' = 'HostedAgents=V1Preview'
    'Content-Type' = 'application/json'
}

foreach ($scenario in $Scenarios) {
    $agentName = "it-$scenario"
    Write-Host ""
    Write-Host "=== $agentName ==="

    # 1. Ensure the agent exists. Create a placeholder version if it doesn't.
    $agent = $null
    try {
        $agent = Invoke-RestMethod -Method GET -Headers $headers `
            -Uri "$ProjectEndpoint/agents/$agentName`?api-version=v1"
        Write-Host "  agent exists"
    } catch {
        if ($_.Exception.Response.StatusCode -ne 404) { throw }
    }

    if (-not $agent) {
        Write-Host "  creating placeholder version..."
        $body = @{
            definition = @{
                kind = 'hosted'
                container_protocol_versions = @(@{ protocol = 'responses'; version = '1.0.0' })
                cpu = '0.25'
                memory = '0.5Gi'
                environment_variables = @{ IT_SCENARIO = $scenario }
                image = $Image
            }
            metadata = @{ enableVnextExperience = 'true' }
        } | ConvertTo-Json -Depth 10
        Invoke-RestMethod -Method POST -Headers $headers `
            -Uri "$ProjectEndpoint/agents/$agentName/versions`?api-version=v1" `
            -Body $body | Out-Null
        Start-Sleep 5
        $agent = Invoke-RestMethod -Method GET -Headers $headers `
            -Uri "$ProjectEndpoint/agents/$agentName`?api-version=v1"
    }

    $principalId = $agent.versions.latest.instance_identity.principal_id
    Write-Host "  agent MI: $principalId"

    # 2. PATCH the agent endpoint to route via @latest if not already configured.
    # Using @latest means each new version added by the IT fixture automatically becomes the
    # served version, no per-run PATCH needed (which is good because the strongly-typed
    # PATCH wrapper is alpha-only on Azure.AI.Projects right now).
    $hasLatestSelector = $agent.agent_endpoint -and `
        ($agent.agent_endpoint.version_selector.version_selection_rules | Where-Object { $_.agent_version -eq '@latest' })
    if ($hasLatestSelector) {
        Write-Host "  endpoint already routes via @latest"
    } else {
        Write-Host "  patching endpoint to route via @latest..."
        $patchBody = @{
            agent_endpoint = @{
                version_selector = @{
                    version_selection_rules = @(@{
                        type = 'FixedRatio'
                        agent_version = '@latest'
                        traffic_percentage = 100
                    })
                }
                protocols = @('responses')
            }
        } | ConvertTo-Json -Depth 10
        Invoke-RestMethod -Method PATCH -Headers $headers `
            -Uri "$ProjectEndpoint/agents/$agentName`?api-version=v1" `
            -Body $patchBody | Out-Null
    }

    # 3. Grant Azure AI User on the project scope to the agent MI (idempotent).
    $existing = az role assignment list --assignee $principalId --scope $projectScope `
        --query "[?roleDefinitionName=='Azure AI User']" 2>$null | ConvertFrom-Json
    if ($existing) {
        Write-Host "  role already assigned"
    } else {
        Write-Host "  granting Azure AI User..."
        $maxAttempts = 12
        $granted = $false
        for ($i = 1; $i -le $maxAttempts; $i++) {
            $output = az role assignment create `
                --assignee-object-id $principalId `
                --assignee-principal-type ServicePrincipal `
                --role 'Azure AI User' `
                --scope $projectScope 2>&1
            if ($LASTEXITCODE -eq 0) {
                $granted = $true
                break
            }
            if ($output -match 'Cannot find user or service principal in graph') {
                Write-Host "    attempt $i/$maxAttempts : MI not yet in AAD graph, retrying in 15s..."
                Start-Sleep 15
                continue
            }
            throw "az role assignment failed: $output"
        }
        if (-not $granted) {
            throw "MI '$principalId' did not appear in AAD graph after $maxAttempts attempts."
        }
        Write-Host "  granted (RBAC propagation may take 1-3 minutes)"
    }
}

Write-Host ""
Write-Host "Done. Wait ~3 minutes after first-time grants before running the tests."
