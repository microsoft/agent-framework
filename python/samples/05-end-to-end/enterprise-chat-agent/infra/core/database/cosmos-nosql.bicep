// Copyright (c) Microsoft. All rights reserved.
// Azure Cosmos DB NoSQL account and database
// Note: Containers are auto-created by CosmosHistoryProvider and CosmosConversationStore

@description('Name of the Cosmos DB account')
param accountName string

@description('Location for the Cosmos DB account')
param location string

@description('Tags to apply to the Cosmos DB account')
param tags object = {}

@description('Name of the database')
param databaseName string

@description('Enable free tier (only one per subscription)')
param enableFreeTier bool = false

@description('Default consistency level')
@allowed(['Eventual', 'ConsistentPrefix', 'Session', 'BoundedStaleness', 'Strong'])
param defaultConsistencyLevel string = 'Session'

// ============================================================================
// Cosmos DB Account
// ============================================================================

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2023-11-15' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: enableFreeTier
    consistencyPolicy: {
      defaultConsistencyLevel: defaultConsistencyLevel
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
    // Security settings
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

// ============================================================================
// Database
// ============================================================================

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2023-11-15' = {
  parent: cosmosAccount
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// ============================================================================
// Outputs
// ============================================================================

output accountId string = cosmosAccount.id
output accountName string = cosmosAccount.name
output endpoint string = cosmosAccount.properties.documentEndpoint
output databaseName string = database.name
