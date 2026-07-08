#!/usr/bin/env pwsh
<#
.SYNOPSIS
    List Foundry Tools Catalog connectors, or fetch full details for one connector.

.DESCRIPTION
    Queries the Azure AI Foundry Tools Catalog (asset-gallery) connectors registry.
    - With no -ConnectorName: lists all connectors (name, title, detected auth type).
    - With -ConnectorName:    prints the full JSON details for that connector.

    A bearer token for https://ai.azure.com is required. It is read from the
    -Token parameter, then the CATALOG_TOKEN environment variable, and finally
    acquired automatically via 'az account get-access-token' (requires 'az login').

.EXAMPLE
    ./list-foundry-connectors.ps1
    Lists all connectors.

.EXAMPLE
    ./list-foundry-connectors.ps1 -ConnectorName a365outlookmailmcp
    Prints full details for the Work IQ Mail MCP connector.

.EXAMPLE
    ./list-foundry-connectors.ps1 -PageSize 2000
    Lists more connectors in a single page.
#>
[CmdletBinding()]
param(
    # annotations/name of a connector to fetch full details for. Omit to list all.
    [string]$ConnectorName,
    # Azure ML region host prefix.
    [string]$Region = "eastus",
    # Number of results to request in one page.
    [int]$PageSize = 100,
    # Catalog bearer token (audience https://ai.azure.com). Defaults to $env:CATALOG_TOKEN, else acquired via az.
    [string]$Token = $env:CATALOG_TOKEN
)

$ErrorActionPreference = "Stop"

if (-not $Token) {
    Write-Verbose "No token supplied; acquiring via 'az account get-access-token'..."
    $Token = az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv
}
if (-not $Token) {
    throw "Failed to acquire a catalog token. Run 'az login', or pass -Token / set `$env:CATALOG_TOKEN."
}

$uri = "https://$Region.api.azureml.ms/asset-gallery/v1.0/tools"
$headers = @{
    "Authorization"   = "Bearer $Token"
    "Content-Type"    = "application/json"
    "x-ms-user-agent" = "AzureMachineLearningWorkspacePortal/12.0"
}

$filters = [System.Collections.ArrayList]@(
    @{ field = "entityContainerId"; operator = "eq"; values = @("connectors-registry-prod-bl") }
    @{ field = "type";              operator = "eq"; values = @("tools") }
    @{ field = "kind";              operator = "eq"; values = @("Versioned") }
    @{ field = "labels";            operator = "eq"; values = @("latest") }
)
if ($ConnectorName) {
    [void]$filters.Add(@{ field = "annotations/name"; operator = "eq"; values = @($ConnectorName) })
}

$body = @{
    freeTextSearch          = "*"
    filters                 = $filters
    includeTotalResultCount = $true
    pageSize                = $PageSize
    skip                    = 0
} | ConvertTo-Json -Depth 10

# The response can be several MB and may contain a property with an empty-string
# name, so read the raw content and parse with -AsHashtable.
$content = (Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -Body $body).Content
$resp = $content | ConvertFrom-Json -AsHashtable -Depth 100

if ($ConnectorName) {
    if ($resp.totalCount -eq 0) {
        Write-Warning "No connector found with annotations/name '$ConnectorName'."
        return
    }
    $resp.value | ConvertTo-Json -Depth 100
}
else {
    Write-Host "Total connectors: $($resp.totalCount)"
    $resp.value | ForEach-Object {
        $params = $_.properties.'x-ms-connection-parameters'
        $authType = if ($null -eq $params) {
            "None"
        }
        else {
            $types = $params.Values | ForEach-Object { $_.type }
            if ($types -contains "oauthSetting") { "OAuth2" }
            elseif ($types -contains "securestring") { "CustomKeys" }
            else { "None" }
        }
        [pscustomobject]@{
            Name  = $_.annotations.name
            Title = $_.properties.title
            Auth  = $authType
        }
    } | Format-Table -AutoSize
}
