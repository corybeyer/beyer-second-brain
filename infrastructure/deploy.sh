#!/bin/bash
# Deploy Second Brain Infrastructure to Azure
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - Subscription selected (az account set --subscription <name>)
#
# Usage:
#   ./deploy.sh <resource-group-name> <location> <postgres-password>
#
# Example:
#   ./deploy.sh rg-secondbrain eastus "MySecurePassword123!"

set -e

RESOURCE_GROUP="${1:-rg-secondbrain}"
LOCATION="${2:-eastus}"
POSTGRES_PASSWORD="${3}"

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo "Error: PostgreSQL password is required"
    echo "Usage: ./deploy.sh <resource-group> <location> <postgres-password>"
    exit 1
fi

echo "=== Second Brain Infrastructure Deployment ==="
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo ""

# Create resource group if it doesn't exist
echo "Creating resource group..."
az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none

# Deploy infrastructure
echo "Deploying infrastructure (this may take 5-10 minutes)..."
DEPLOYMENT_OUTPUT=$(az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file main.bicep \
    --parameters \
        postgresAdminPassword="$POSTGRES_PASSWORD" \
    --query 'properties.outputs' \
    --output json)

# Extract outputs
STORAGE_ACCOUNT=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.storageAccountName.value')
STORAGE_CONNECTION=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.storageConnectionString.value')
POSTGRES_HOST=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.postgresHost.value')
POSTGRES_DB=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.postgresDatabase.value')

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Add these to your .env file:"
echo ""
echo "# Azure Storage"
echo "AZURE_STORAGE_CONNECTION_STRING=\"$STORAGE_CONNECTION\""
echo "AZURE_STORAGE_CONTAINER_NAME=books"
echo ""
echo "# Azure PostgreSQL"
echo "POSTGRES_HOST=$POSTGRES_HOST"
echo "POSTGRES_PORT=5432"
echo "POSTGRES_DB=$POSTGRES_DB"
echo "POSTGRES_USER=sbadmin"
echo "POSTGRES_PASSWORD=<your-password>"
echo ""
echo "=== Next Steps ==="
echo "1. Copy the above values to your .env file"
echo "2. Add your client IP to PostgreSQL firewall (or use Azure Portal)"
echo "3. Run: python scripts/init_db.py to set up extensions and tables"
