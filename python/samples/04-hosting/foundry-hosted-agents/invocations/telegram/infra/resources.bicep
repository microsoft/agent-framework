targetScope = 'resourceGroup'

@description('Short lowercase alphanumeric prefix used in resource names.')
param namePrefix string

@description('Primary Azure region.')
param location string

@description('Azure region for Cosmos DB.')
param cosmosLocation string

@description('Object ID of the deployment principal.')
param deployerObjectId string

@allowed([
  'User'
  'ServicePrincipal'
])
@description('Microsoft Entra principal type of the deployer.')
param deployerPrincipalType string

@description('Publisher email required by API Management.')
param publisherEmail string

@description('Publisher name displayed by API Management.')
param publisherName string

@description('Foundry model name.')
param modelName string

@description('Foundry model version.')
param modelVersion string

@description('Foundry model format.')
param modelFormat string

@description('Model deployment SKU.')
param modelSkuName string

@description('Model deployment capacity.')
param modelCapacity int

@secure()
@description('Telegram bot token written to Key Vault.')
param telegramBotToken string

@secure()
@description('Telegram webhook secret written to Key Vault.')
param telegramWebhookSecret string

var suffix = take(uniqueString(subscription().id, resourceGroup().id), 7)
var compactPrefix = take(toLower(namePrefix), 12)
var foundryAccountName = '${compactPrefix}-ai-${suffix}'
var foundryProjectName = '${compactPrefix}-project'
var modelDeploymentName = modelName
var agentName = 'telegram-agent'
var logAnalyticsName = '${compactPrefix}-logs-${suffix}'
var applicationInsightsName = '${compactPrefix}-appi-${suffix}'
var monitoringConnectionName = 'application-insights'
var apimName = '${compactPrefix}-apim-${suffix}'
var keyVaultName = take('${compactPrefix}-kv-${suffix}', 24)
var cosmosAccountName = '${compactPrefix}-cosmos-${suffix}'
var cosmosDatabaseName = 'telegram-agent'
var cosmosContainerName = 'chat-history'
var telegramApiName = 'telegram-api'
var telegramOperationName = 'telegram-webhook'
var botTokenSecretName = 'telegram-bot-token'
var webhookSecretName = 'telegram-webhook-secret'

var foundryServiceEndpoint = 'https://${foundryAccountName}.services.ai.azure.com'
var foundryProjectEndpoint = '${foundryServiceEndpoint}/api/projects/${foundryProjectName}'
var foundryInvocationsPath = '/api/projects/${foundryProjectName}/agents/${agentName}/endpoint/protocols/invocations'
var telegramWebhookUrl = 'https://${apimName}.azure-api.net/telegram/webhook'
var telegramPolicy = replace(
  replace(loadTextContent('telegram-policy.xml'), '__FOUNDRY_SERVICE_ENDPOINT__', foundryServiceEndpoint),
  '__FOUNDRY_INVOCATIONS_PATH__',
  foundryInvocationsPath
)
var tags = {
  sample: 'agent-framework-telegram-hosted-agent'
}

var foundryUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '53ca6127-db72-4b80-b1b0-d745d6d5456d'
)
var foundryProjectManagerRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'eadc314b-1a2d-4efa-be10-5d325db5065e'
)
var keyVaultSecretsUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: applicationInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2026-05-01' = {
  name: foundryAccountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    allowProjectManagement: true
    customSubDomainName: foundryAccountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2026-05-01' = {
  parent: foundryAccount
  name: foundryProjectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    description: 'Agent Framework Telegram hosted-agent sample'
    displayName: foundryProjectName
  }
}

resource monitoringConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-05-01' = {
  parent: foundryProject
  name: monitoringConnectionName
  properties: {
    authType: 'ApiKey'
    category: 'AppInsights'
    credentials: {
      key: applicationInsights.properties.ConnectionString
    }
    isSharedToAll: false
    metadata: {
      ApiType: 'Azure'
      ResourceId: applicationInsights.id
    }
    target: applicationInsights.id
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundryAccount
  name: modelDeploymentName
  sku: {
    name: modelSkuName
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: modelFormat
      name: modelName
      version: modelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    accessPolicies: []
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
    sku: {
      family: 'A'
      name: 'standard'
    }
  }
}

resource botTokenSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: keyVault
  name: botTokenSecretName
  properties: {
    value: telegramBotToken
  }
}

resource webhookSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: keyVault
  name: webhookSecretName
  properties: {
    value: telegramWebhookSecret
  }
}

resource deployerKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, deployerObjectId, keyVaultSecretsUserRoleId)
  properties: {
    principalId: deployerObjectId
    principalType: deployerPrincipalType
    roleDefinitionId: keyVaultSecretsUserRoleId
  }
}

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: apimName
  location: location
  sku: {
    name: 'Consumption'
    capacity: 0
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
    publicNetworkAccess: 'Enabled'
  }
}

resource apimKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, apim.id, keyVaultSecretsUserRoleId)
  properties: {
    principalId: apim.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: keyVaultSecretsUserRoleId
  }
}

resource webhookSecretNamedValue 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: webhookSecretName
  properties: {
    displayName: 'TelegramWebhookSecret'
    keyVault: {
      secretIdentifier: webhookSecret.properties.secretUri
    }
    secret: true
  }
  dependsOn: [
    apimKeyVaultRole
  ]
}

resource telegramApi 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: telegramApiName
  properties: {
    displayName: 'Telegram webhook'
    path: 'telegram'
    protocols: [
      'https'
    ]
    serviceUrl: foundryServiceEndpoint
    subscriptionRequired: false
  }
}

resource telegramOperation 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: telegramApi
  name: telegramOperationName
  properties: {
    displayName: 'Receive Telegram update'
    method: 'POST'
    urlTemplate: '/webhook'
    responses: [
      {
        statusCode: 200
        description: 'Telegram update completed'
      }
      {
        statusCode: 400
        description: 'Unsupported Telegram update'
      }
      {
        statusCode: 401
        description: 'Invalid Telegram webhook secret'
      }
    ]
  }
}

resource telegramOperationPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2024-05-01' = {
  parent: telegramOperation
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: telegramPolicy
  }
  dependsOn: [
    webhookSecretNamedValue
  ]
}

resource apimFoundryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryProject
  name: guid(foundryProject.id, apim.id, foundryUserRoleId)
  properties: {
    principalId: apim.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: foundryUserRoleId
  }
}

resource deployerFoundryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundryProject
  name: guid(foundryProject.id, deployerObjectId, foundryProjectManagerRoleId)
  properties: {
    principalId: deployerObjectId
    principalType: deployerPrincipalType
    roleDefinitionId: foundryProjectManagerRoleId
  }
}

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2025-04-15' = {
  name: cosmosAccountName
  location: cosmosLocation
  kind: 'GlobalDocumentDB'
  tags: tags
  properties: {
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    databaseAccountOfferType: 'Standard'
    disableLocalAuth: true
    locations: [
      {
        failoverPriority: 0
        isZoneRedundant: false
        locationName: cosmosLocation
      }
    ]
    publicNetworkAccess: 'Enabled'
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2025-04-15' = {
  parent: cosmosAccount
  name: cosmosDatabaseName
  properties: {
    resource: {
      id: cosmosDatabaseName
    }
  }
}

resource cosmosContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-04-15' = {
  parent: cosmosDatabase
  name: cosmosContainerName
  properties: {
    resource: {
      id: cosmosContainerName
      partitionKey: {
        kind: 'Hash'
        paths: [
          '/session_id'
        ]
      }
    }
  }
}

output foundryAccountName string = foundryAccount.name
output foundryProjectName string = foundryProject.name
output foundryProjectId string = foundryProject.id
output foundryProjectEndpoint string = foundryProjectEndpoint
output modelDeploymentName string = modelDeployment.name
output agentName string = agentName
output applicationInsightsName string = applicationInsights.name
output applicationInsightsId string = applicationInsights.id
output monitoringConnectionName string = monitoringConnection.name
output apimName string = apim.name
output telegramWebhookUrl string = telegramWebhookUrl
output keyVaultName string = keyVault.name
output keyVaultId string = keyVault.id
output keyVaultUrl string = keyVault.properties.vaultUri
output cosmosAccountName string = cosmosAccount.name
output cosmosAccountId string = cosmosAccount.id
output cosmosEndpoint string = cosmosAccount.properties.documentEndpoint
output cosmosDatabaseName string = cosmosDatabase.name
output cosmosContainerName string = cosmosContainer.name
