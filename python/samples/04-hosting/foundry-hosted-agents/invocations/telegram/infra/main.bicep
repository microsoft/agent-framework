targetScope = 'subscription'

@description('Short lowercase alphanumeric prefix used in resource names.')
@minLength(3)
@maxLength(16)
param namePrefix string = 'telegramagent'

@description('Resource group name. Defaults to rg-<namePrefix>.')
param resourceGroupName string = 'rg-${namePrefix}'

@description('Primary Azure region for Foundry, APIM, Key Vault, and monitoring.')
param location string = deployment().location

@description('Azure region for the serverless Cosmos DB account.')
param cosmosLocation string = location

@description('Object ID of the user or service principal running the deployment.')
param deployerObjectId string

@allowed([
  'User'
  'ServicePrincipal'
])
@description('Microsoft Entra principal type of the deployer.')
param deployerPrincipalType string = 'User'

@description('Publisher email required by API Management.')
param publisherEmail string

@description('Publisher name displayed by API Management.')
param publisherName string = 'Agent Framework sample'

@description('Foundry model name.')
param modelName string = 'gpt-5.6-luna'

@description('Foundry model version.')
param modelVersion string = '2026-07-09'

@description('Foundry model format.')
param modelFormat string = 'OpenAI'

@description('Model deployment SKU.')
param modelSkuName string = 'DataZoneStandard'

@minValue(1)
@description('Model deployment capacity.')
param modelCapacity int = 10

@secure()
@description('Telegram bot token written to Key Vault.')
param telegramBotToken string

@secure()
@description('Telegram webhook secret written to Key Vault.')
param telegramWebhookSecret string

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: {
    'azd-env-name': namePrefix
    sample: 'agent-framework-telegram-hosted-agent'
  }
}

module resources 'resources.bicep' = {
  name: '${namePrefix}-resources'
  scope: resourceGroup
  params: {
    cosmosLocation: cosmosLocation
    deployerObjectId: deployerObjectId
    deployerPrincipalType: deployerPrincipalType
    location: location
    modelCapacity: modelCapacity
    modelFormat: modelFormat
    modelName: modelName
    modelSkuName: modelSkuName
    modelVersion: modelVersion
    namePrefix: namePrefix
    publisherEmail: publisherEmail
    publisherName: publisherName
    telegramBotToken: telegramBotToken
    telegramWebhookSecret: telegramWebhookSecret
  }
}

output resourceGroupName string = resourceGroup.name
output foundryAccountName string = resources.outputs.foundryAccountName
output foundryProjectName string = resources.outputs.foundryProjectName
output foundryProjectId string = resources.outputs.foundryProjectId
output foundryProjectEndpoint string = resources.outputs.foundryProjectEndpoint
output modelDeploymentName string = resources.outputs.modelDeploymentName
output agentName string = resources.outputs.agentName
output applicationInsightsName string = resources.outputs.applicationInsightsName
output applicationInsightsId string = resources.outputs.applicationInsightsId
output monitoringConnectionName string = resources.outputs.monitoringConnectionName
output apimName string = resources.outputs.apimName
output telegramWebhookUrl string = resources.outputs.telegramWebhookUrl
output keyVaultName string = resources.outputs.keyVaultName
output keyVaultId string = resources.outputs.keyVaultId
output keyVaultUrl string = resources.outputs.keyVaultUrl
output cosmosAccountName string = resources.outputs.cosmosAccountName
output cosmosAccountId string = resources.outputs.cosmosAccountId
output cosmosEndpoint string = resources.outputs.cosmosEndpoint
output cosmosDatabaseName string = resources.outputs.cosmosDatabaseName
output cosmosContainerName string = resources.outputs.cosmosContainerName
