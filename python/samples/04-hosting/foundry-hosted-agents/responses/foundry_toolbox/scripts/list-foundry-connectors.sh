#!/usr/bin/env bash
#
# List Foundry Tools Catalog connectors, or fetch full details for one connector.
#
#   - With no -n: lists all connectors (name, title, detected auth type).
#   - With -n NAME: prints the full JSON details for that connector.
#
# A bearer token for https://ai.azure.com is required. It is read from the
# -t option, then the CATALOG_TOKEN environment variable, and finally acquired
# automatically via 'az account get-access-token' (requires 'az login').
#
# Requires: curl, jq (and optionally az).
#
# Examples:
#   ./list-foundry-connectors.sh
#   ./list-foundry-connectors.sh -n a365outlookmailmcp
#   ./list-foundry-connectors.sh -p 2000
#
set -euo pipefail

CONNECTOR_NAME=""
REGION="eastus"
PAGE_SIZE=100
TOKEN="${CATALOG_TOKEN:-}"

usage() {
  cat <<EOF
Usage: $0 [-n connector_name] [-r region] [-p page_size] [-t token]

  -n  Connector annotations/name to fetch full details for (e.g. a365outlookmailmcp).
      If omitted, lists all connectors (name, title, auth type).
  -r  Azure ML region host prefix (default: ${REGION}).
  -p  Page size (default: ${PAGE_SIZE}).
  -t  Catalog bearer token (audience https://ai.azure.com).
      Defaults to \$CATALOG_TOKEN, else acquired via 'az'.
  -h  Show this help.
EOF
}

while getopts ":n:r:p:t:h" opt; do
  case "$opt" in
    n) CONNECTOR_NAME="$OPTARG" ;;
    r) REGION="$OPTARG" ;;
    p) PAGE_SIZE="$OPTARG" ;;
    t) TOKEN="$OPTARG" ;;
    h) usage; exit 0 ;;
    \?) echo "Invalid option: -$OPTARG" >&2; usage; exit 1 ;;
    :)  echo "Option -$OPTARG requires an argument." >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$TOKEN" ]]; then
  TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
fi
if [[ -z "$TOKEN" ]]; then
  echo "Failed to acquire a catalog token. Run 'az login', or pass -t / set CATALOG_TOKEN." >&2
  exit 1
fi

URI="https://${REGION}.api.azureml.ms/asset-gallery/v1.0/tools"

# Base filters; optionally narrow to a single connector by annotations/name.
FILTERS=$(jq -nc --arg connector "$CONNECTOR_NAME" '
   [
     {"field":"entityContainerId","operator":"eq","values":["connectors-registry-prod-bl"]},
     {"field":"type",            "operator":"eq","values":["tools"]},
     {"field":"kind",            "operator":"eq","values":["Versioned"]},
     {"field":"labels",          "operator":"eq","values":["latest"]}
   ] + ( ($connector | length) > 0
         ? [{"field":"annotations/name","operator":"eq","values":[$connector]}]
         : [] )
 ')

BODY=$(cat <<EOF
{
  "freeTextSearch": "*",
  "filters": $FILTERS,
  "includeTotalResultCount": true,
  "pageSize": $PAGE_SIZE,
  "skip": 0
}
EOF
)

RESPONSE=$(curl -sS -X POST "$URI" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "x-ms-user-agent: AzureMachineLearningWorkspacePortal/12.0" \
  -d "$BODY")

if [[ -n "$CONNECTOR_NAME" ]]; then
  # Full JSON details for the requested connector.
  echo "$RESPONSE" | jq '.value'
else
  # name, title, and detected auth type for each connector.
  echo "$RESPONSE" | jq -r '
    .totalCount as $total |
    "Total connectors: \($total)",
    (.value[] | "\(.annotations.name)\t\(.properties.title)\t\(
      .properties["x-ms-connection-parameters"] |
      if . == null then "None"
      elif ([.[].type] | any(. == "oauthSetting")) then "OAuth2"
      elif ([.[].type] | any(. == "securestring")) then "CustomKeys"
      else "None" end
    )")'
fi
