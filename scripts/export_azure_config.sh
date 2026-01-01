#!/bin/bash
# Export Azure configuration for review
# Run this to diagnose blob trigger issues

set -e

RESOURCE_GROUP="rg-second-brain"
FUNCTION_APP="func-secondbrain"
STORAGE_ACCOUNT="stsecondbrain"
OUTPUT_DIR="azure-export"

mkdir -p "$OUTPUT_DIR"

echo "=== Exporting Azure Configuration ==="

# 1. Function App settings (CRITICAL - contains AzureWebJobsStorage)
echo "Exporting Function App settings..."
az functionapp config appsettings list \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  -o json > "$OUTPUT_DIR/function-app-settings.json" 2>/dev/null || echo "Failed to export app settings"

# 2. Function App configuration
echo "Exporting Function App config..."
az functionapp config show \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  -o json > "$OUTPUT_DIR/function-app-config.json" 2>/dev/null || echo "Failed to export app config"

# 3. Function App identity (for managed identity check)
echo "Exporting Function App identity..."
az functionapp identity show \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  -o json > "$OUTPUT_DIR/function-app-identity.json" 2>/dev/null || echo "Failed to export identity"

# 4. Storage account info
echo "Exporting Storage Account info..."
az storage account show \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  -o json > "$OUTPUT_DIR/storage-account.json" 2>/dev/null || echo "Failed to export storage"

# 5. RBAC role assignments on storage account
echo "Exporting Storage RBAC assignments..."
STORAGE_ID=$(az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query id -o tsv 2>/dev/null)
if [ -n "$STORAGE_ID" ]; then
  az role assignment list \
    --scope "$STORAGE_ID" \
    -o json > "$OUTPUT_DIR/storage-rbac.json" 2>/dev/null || echo "Failed to export RBAC"
fi

# 6. List functions deployed
echo "Exporting deployed functions..."
az functionapp function list \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  -o json > "$OUTPUT_DIR/deployed-functions.json" 2>/dev/null || echo "Failed to list functions"

# 7. Check function app status
echo "Checking Function App status..."
az functionapp show \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query "{name:name, state:state, defaultHostName:defaultHostName, kind:kind}" \
  -o json > "$OUTPUT_DIR/function-app-status.json" 2>/dev/null || echo "Failed to get status"

echo ""
echo "=== Export Complete ==="
echo "Files saved to: $OUTPUT_DIR/"
ls -la "$OUTPUT_DIR/"

echo ""
echo "=== Quick Diagnostics ==="

# Check if AzureWebJobsStorage is set
echo ""
echo "Checking AzureWebJobsStorage configuration..."
if [ -f "$OUTPUT_DIR/function-app-settings.json" ]; then
  STORAGE_SETTING=$(cat "$OUTPUT_DIR/function-app-settings.json" | grep -E '"name":\s*"AzureWebJobsStorage"' || true)
  if [ -z "$STORAGE_SETTING" ]; then
    echo "⚠️  WARNING: AzureWebJobsStorage not found in app settings!"
    echo "   This is likely why the blob trigger isn't firing."
  else
    echo "✓ AzureWebJobsStorage is configured"
  fi
fi

# Check managed identity
echo ""
echo "Checking Managed Identity..."
if [ -f "$OUTPUT_DIR/function-app-identity.json" ]; then
  PRINCIPAL_ID=$(cat "$OUTPUT_DIR/function-app-identity.json" | grep -o '"principalId":\s*"[^"]*"' | head -1 || true)
  if [ -n "$PRINCIPAL_ID" ]; then
    echo "✓ Managed Identity is enabled"
    echo "  $PRINCIPAL_ID"
  else
    echo "⚠️  Managed Identity may not be enabled"
  fi
fi
