#!/bin/bash
# Adds an extra redirect URI to the Keycloak web-client configuration.
# Auto-detects GitHub Codespaces via CODESPACE_NAME and
# GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN environment variables.

set -e

KEYCLOAK_URL="${KEYCLOAK_URL:-http://keycloak:8080}"

# Auto-detect Codespaces
if [ -n "$CODESPACE_NAME" ] && [ -n "$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN" ]; then
    WEBCLIENT_PUBLIC_URL="https://${CODESPACE_NAME}-8080.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
fi

if [ -z "$WEBCLIENT_PUBLIC_URL" ]; then
    echo "Not running in Codespaces — skipping redirect URI setup."
    exit 0
fi

echo "Configuring Keycloak redirect URIs for: $WEBCLIENT_PUBLIC_URL"

# Get admin token
TOKEN=$(curl -sf -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=admin-cli&username=admin&password=admin" \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

if [ -z "$TOKEN" ]; then
    echo "ERROR: Failed to get admin token" >&2
    exit 1
fi

# Get web-client UUID
CLIENT_UUID=$(curl -sf "$KEYCLOAK_URL/admin/realms/dev/clients?clientId=web-client" \
  -H "Authorization: Bearer $TOKEN" \
  | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')

if [ -z "$CLIENT_UUID" ]; then
    echo "ERROR: Failed to find web-client UUID" >&2
    exit 1
fi
# Update redirect URIs and web origins
curl -sf -X PUT "$KEYCLOAK_URL/admin/realms/dev/clients/$CLIENT_UUID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"redirectUris\": [\"http://localhost:8080/*\", \"${WEBCLIENT_PUBLIC_URL}/*\"],
    \"webOrigins\": [\"http://localhost:8080\", \"${WEBCLIENT_PUBLIC_URL}\"]
  }"

echo "Keycloak redirect URIs updated successfully."
