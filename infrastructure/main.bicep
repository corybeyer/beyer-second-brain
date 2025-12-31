// Second Brain Infrastructure
// Azure resources for the personal knowledge management system

@description('Base name for all resources')
param baseName string = 'secondbrain'

@description('Location for all resources')
param location string = resourceGroup().location

@description('PostgreSQL administrator login')
param postgresAdminLogin string = 'sbadmin'

@description('PostgreSQL administrator password')
@secure()
param postgresAdminPassword string

@description('PostgreSQL SKU name')
param postgresSku string = 'Standard_B1ms'

@description('PostgreSQL storage size in GB')
param postgresStorageGb int = 32

// Generate unique suffix for globally unique names
var uniqueSuffix = uniqueString(resourceGroup().id)
var storageAccountName = '${baseName}${uniqueSuffix}'
var postgresServerName = '${baseName}-pg-${uniqueSuffix}'

// ============================================================================
// Storage Account for PDFs
// ============================================================================
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource booksContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'books'
  properties: {
    publicAccess: 'None'
  }
}

// ============================================================================
// PostgreSQL Flexible Server
// ============================================================================
resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-03-01-preview' = {
  name: postgresServerName
  location: location
  sku: {
    name: postgresSku
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: {
      storageSizeGB: postgresStorageGb
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

// Firewall rule to allow Azure services
resource allowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-03-01-preview' = {
  parent: postgresServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// Database
resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-03-01-preview' = {
  parent: postgresServer
  name: 'secondbrain'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Enable pgvector extension via server configuration
resource vectorExtension 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-03-01-preview' = {
  parent: postgresServer
  name: 'azure.extensions'
  properties: {
    value: 'vector,age'
    source: 'user-override'
  }
}

// ============================================================================
// Outputs
// ============================================================================
output storageAccountName string = storageAccount.name
output storageConnectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storageAccount.listKeys().keys[0].value}'
output postgresServerName string = postgresServer.name
output postgresHost string = postgresServer.properties.fullyQualifiedDomainName
output postgresDatabase string = database.name
