// Copyright (c) Microsoft. All rights reserved.
// Azure Storage Account for Function App

@description('Name of the storage account')
param name string

@description('Location for the storage account')
param location string

@description('Tags to apply to the storage account')
param tags object = {}

@description('Storage account SKU')
@allowed(['Standard_LRS', 'Standard_GRS', 'Standard_ZRS'])
param sku string = 'Standard_LRS'

// ============================================================================
// Storage Account
// ============================================================================

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    allowSharedKeyAccess: true  // Required for Function App deployment
    accessTier: 'Hot'
  }
}

// Blob service for Function App deployment packages
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

// Container for deployment packages (required for Flex Consumption)
resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'deploymentpackage'
  properties: {
    publicAccess: 'None'
  }
}

// ============================================================================
// Outputs
// ============================================================================

output id string = storageAccount.id
output name string = storageAccount.name
output primaryEndpoints object = storageAccount.properties.primaryEndpoints
