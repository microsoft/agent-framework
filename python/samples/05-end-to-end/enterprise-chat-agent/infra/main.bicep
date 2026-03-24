// Copyright (c) Microsoft. All rights reserved.
// Enterprise Chat Agent - Infrastructure as Code
//
// This Bicep template deploys:
// - Azure Function App (Flex Consumption)
// - Azure Cosmos DB (NoSQL)
// - Azure OpenAI (optional, can use existing)
// - Supporting resources (Storage, App Insights, Log Analytics)

targetScope = 'subscription'

// ============================================================================
// Parameters
// ============================================================================

@minLength(1)
@maxLength(64)
@description('Name of the environment (e.g., dev, staging, prod)')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Name of the resource group')
param resourceGroupName string = ''

@description('Azure OpenAI endpoint URL (leave empty to create new)')
param azureOpenAiEndpoint string = ''

@description('Azure OpenAI model deployment name')
param azureOpenAiModel string = 'gpt-4o'

@description('Cosmos DB database name')
param cosmosDatabaseName string = 'chat_db'

@description('Cosmos DB container name for messages')
param cosmosContainerName string = 'messages'

// ============================================================================
// Variables
// ============================================================================

var abbrs = loadJsonContent('./abbreviations.json')
var tags = { 'azd-env-name': environmentName }
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

// ============================================================================
// Resource Group
// ============================================================================

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : '${abbrs.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}

// ============================================================================
// Monitoring (Log Analytics + App Insights)
// ============================================================================

module monitoring './core/monitor/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: '${abbrs.insightsComponents}${resourceToken}'
  }
}

// ============================================================================
// Storage Account (for Function App)
// ============================================================================

module storage './core/storage/storage-account.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    name: '${abbrs.storageStorageAccounts}${resourceToken}'
    location: location
    tags: tags
  }
}

// ============================================================================
// Cosmos DB
// ============================================================================

module cosmos './core/database/cosmos-nosql.bicep' = {
  name: 'cosmos'
  scope: rg
  params: {
    accountName: '${abbrs.documentDBDatabaseAccounts}${resourceToken}'
    location: location
    tags: tags
    databaseName: cosmosDatabaseName
    containerName: cosmosContainerName
    partitionKeyPath: '/thread_id'
  }
}

// ============================================================================
// Function App
// ============================================================================

module functionApp './core/host/function-app.bicep' = {
  name: 'functionApp'
  scope: rg
  params: {
    name: '${abbrs.webSitesFunctions}${resourceToken}'
    location: location
    tags: tags
    storageAccountName: storage.outputs.name
    applicationInsightsName: monitoring.outputs.applicationInsightsName
    cosmosAccountName: cosmos.outputs.accountName
    cosmosDatabaseName: cosmosDatabaseName
    cosmosContainerName: cosmosContainerName
    azureOpenAiEndpoint: azureOpenAiEndpoint
    azureOpenAiModel: azureOpenAiModel
  }
}

// ============================================================================
// Outputs
// ============================================================================

output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name

output AZURE_FUNCTION_APP_NAME string = functionApp.outputs.name
output AZURE_FUNCTION_APP_URL string = functionApp.outputs.url

output AZURE_COSMOS_ENDPOINT string = cosmos.outputs.endpoint
output AZURE_COSMOS_DATABASE_NAME string = cosmosDatabaseName
output AZURE_COSMOS_CONTAINER_NAME string = cosmosContainerName

output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.applicationInsightsConnectionString
