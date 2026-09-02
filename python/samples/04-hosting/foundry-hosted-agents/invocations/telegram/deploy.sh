#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

NAME_PREFIX="${NAME_PREFIX:-telegramagent}"
AZURE_LOCATION="${AZURE_LOCATION:-eastus2}"
COSMOS_LOCATION="${COSMOS_LOCATION:-$AZURE_LOCATION}"
RESOURCE_GROUP_NAME="${RESOURCE_GROUP_NAME:-rg-${NAME_PREFIX}}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-${NAME_PREFIX}-telegram}"
AZD_ENV_NAME="${AZD_ENV_NAME:-${NAME_PREFIX}-telegram}"
AGENT_SERVICE="telegram-agent"
MODEL_NAME="${MODEL_NAME:-gpt-5.6-luna}"
MODEL_VERSION="${MODEL_VERSION:-2026-07-09}"
MODEL_FORMAT="${MODEL_FORMAT:-OpenAI}"
MODEL_SKU_NAME="${MODEL_SKU_NAME:-DataZoneStandard}"
MODEL_CAPACITY="${MODEL_CAPACITY:-10}"
ENABLE_SENSITIVE_DATA="${ENABLE_SENSITIVE_DATA:-true}"
APIM_PUBLISHER_NAME="${APIM_PUBLISHER_NAME:-Agent Framework sample}"
ROTATE_TELEGRAM_WEBHOOK_SECRET="${ROTATE_TELEGRAM_WEBHOOK_SECRET:-0}"
RBAC_PROPAGATION_WAIT_SECONDS="${RBAC_PROPAGATION_WAIT_SECONDS:-30}"
FOUNDRY_ACCESS_TIMEOUT_SECONDS="${FOUNDRY_ACCESS_TIMEOUT_SECONDS:-180}"
APIM_SECRET_REFRESH_TIMEOUT_SECONDS="${APIM_SECRET_REFRESH_TIMEOUT_SECONDS:-180}"
INFRA_DEPLOYMENT_ATTEMPTS="${INFRA_DEPLOYMENT_ATTEMPTS:-6}"
INFRA_RETRY_DELAY_SECONDS="${INFRA_RETRY_DELAY_SECONDS:-30}"
PARAMETERS_FILE="$ROOT/.deploy-parameters.json"

cleanup() {
    rm -f "$PARAMETERS_FILE"
}
trap cleanup EXIT

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'Required command not found: %s\n' "$1" >&2
        exit 1
    }
}

output_value() {
    jq -r --arg name "$1" '.[$name].value' <<<"$DEPLOYMENT_OUTPUTS"
}

azd_command() {
    AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd "$@"
}

require_command az
require_command azd
require_command curl
require_command jq
require_command openssl

: "${TELEGRAM_BOT_TOKEN:?Set TELEGRAM_BOT_TOKEN before running this script.}"

if [[ ! "$NAME_PREFIX" =~ ^[a-z0-9]{3,16}$ ]]; then
    printf 'NAME_PREFIX must contain 3-16 lowercase letters or digits.\n' >&2
    exit 1
fi
if [[ "$ROTATE_TELEGRAM_WEBHOOK_SECRET" != "0" && "$ROTATE_TELEGRAM_WEBHOOK_SECRET" != "1" ]]; then
    printf 'ROTATE_TELEGRAM_WEBHOOK_SECRET must be 0 or 1.\n' >&2
    exit 1
fi
if [[ ! "$MODEL_CAPACITY" =~ ^[1-9][0-9]*$ ]]; then
    printf 'MODEL_CAPACITY must be a positive integer.\n' >&2
    exit 1
fi
if [[ "$ENABLE_SENSITIVE_DATA" != "true" && "$ENABLE_SENSITIVE_DATA" != "false" ]]; then
    printf 'ENABLE_SENSITIVE_DATA must be true or false.\n' >&2
    exit 1
fi
if [[ ! "$RBAC_PROPAGATION_WAIT_SECONDS" =~ ^[0-9]+$ ]]; then
    printf 'RBAC_PROPAGATION_WAIT_SECONDS must be a non-negative integer.\n' >&2
    exit 1
fi
if [[ ! "$FOUNDRY_ACCESS_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]]; then
    printf 'FOUNDRY_ACCESS_TIMEOUT_SECONDS must be a non-negative integer.\n' >&2
    exit 1
fi
if [[ ! "$APIM_SECRET_REFRESH_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]]; then
    printf 'APIM_SECRET_REFRESH_TIMEOUT_SECONDS must be a non-negative integer.\n' >&2
    exit 1
fi
if [[ ! "$INFRA_DEPLOYMENT_ATTEMPTS" =~ ^[1-9][0-9]*$ ]]; then
    printf 'INFRA_DEPLOYMENT_ATTEMPTS must be a positive integer.\n' >&2
    exit 1
fi
if [[ ! "$INFRA_RETRY_DELAY_SECONDS" =~ ^[0-9]+$ ]]; then
    printf 'INFRA_RETRY_DELAY_SECONDS must be a non-negative integer.\n' >&2
    exit 1
fi

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"
if [[ "$(
    az group exists \
        --subscription "$SUBSCRIPTION_ID" \
        --name "$RESOURCE_GROUP_NAME"
)" == "true" ]]; then
    existing_group_tags="$(
        az group show \
            --subscription "$SUBSCRIPTION_ID" \
            --name "$RESOURCE_GROUP_NAME" \
            --query tags \
            -o json
    )"
    if [[ "$(jq -r '.sample // ""' <<<"$existing_group_tags")" != "agent-framework-telegram-hosted-agent" ]]; then
        printf 'Resource group %s already exists without the Telegram sample ownership tag.\n' \
            "$RESOURCE_GROUP_NAME" >&2
        exit 1
    fi
fi

ACCOUNT_TYPE="$(az account show --subscription "$SUBSCRIPTION_ID" --query user.type -o tsv)"
if [[ -n "${DEPLOYER_OBJECT_ID:-}" ]]; then
    DEPLOYER_ID="$DEPLOYER_OBJECT_ID"
    DEPLOYER_PRINCIPAL_TYPE="${DEPLOYER_PRINCIPAL_TYPE:-User}"
elif [[ "$ACCOUNT_TYPE" == "user" ]]; then
    DEPLOYER_ID="$(az ad signed-in-user show --query id -o tsv)"
    DEPLOYER_PRINCIPAL_TYPE="User"
else
    CLIENT_ID="$(az account show --subscription "$SUBSCRIPTION_ID" --query user.name -o tsv)"
    DEPLOYER_ID="$(az ad sp show --id "$CLIENT_ID" --query id -o tsv)"
    DEPLOYER_PRINCIPAL_TYPE="ServicePrincipal"
fi

APIM_PUBLISHER_EMAIL="${APIM_PUBLISHER_EMAIL:-$(
    az account show --subscription "$SUBSCRIPTION_ID" --query user.name -o tsv
)}"
if [[ "$APIM_PUBLISHER_EMAIL" != *@* ]]; then
    printf 'Set APIM_PUBLISHER_EMAIL to a valid publisher email address.\n' >&2
    exit 1
fi

existing_vault="$(
    az deployment sub show \
        --name "$DEPLOYMENT_NAME" \
        --subscription "$SUBSCRIPTION_ID" \
        --query properties.outputs.keyVaultName.value \
        -o tsv 2>/dev/null || true
)"
if [[ -z "$existing_vault" ]]; then
    existing_vault="$(
        az keyvault list \
            --subscription "$SUBSCRIPTION_ID" \
            --resource-group "$RESOURCE_GROUP_NAME" \
            --query "[?tags.sample=='agent-framework-telegram-hosted-agent'].name | [0]" \
            -o tsv 2>/dev/null || true
    )"
fi

webhook_secret=""
if [[ "$ROTATE_TELEGRAM_WEBHOOK_SECRET" == "0" && -n "$existing_vault" ]]; then
    if ! webhook_secret="$(
        az keyvault secret show \
            --subscription "$SUBSCRIPTION_ID" \
            --vault-name "$existing_vault" \
            --name telegram-webhook-secret \
            --query value \
            -o tsv 2>/dev/null
    )"; then
        printf 'Could not reuse the existing webhook secret from Key Vault. Check deployer access or request rotation.\n' >&2
        exit 1
    fi
fi
if [[ -z "$webhook_secret" ]]; then
    webhook_secret="$(openssl rand -hex 32)"
fi

umask 077
export TELEGRAM_WEBHOOK_SECRET_VALUE="$webhook_secret"
jq -n \
    --arg contentVersion "1.0.0.0" \
    --arg prefix "$NAME_PREFIX" \
    --arg resourceGroup "$RESOURCE_GROUP_NAME" \
    --arg location "$AZURE_LOCATION" \
    --arg cosmosLocation "$COSMOS_LOCATION" \
    --arg deployer "$DEPLOYER_ID" \
    --arg deployerType "$DEPLOYER_PRINCIPAL_TYPE" \
    --arg publisherEmail "$APIM_PUBLISHER_EMAIL" \
    --arg publisherName "$APIM_PUBLISHER_NAME" \
    --arg modelName "$MODEL_NAME" \
    --arg modelVersion "$MODEL_VERSION" \
    --arg modelFormat "$MODEL_FORMAT" \
    --arg modelSku "$MODEL_SKU_NAME" \
    --argjson modelCapacity "$MODEL_CAPACITY" \
    '{
      "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
      contentVersion: $contentVersion,
      parameters: {
        namePrefix: {value: $prefix},
        resourceGroupName: {value: $resourceGroup},
        location: {value: $location},
        cosmosLocation: {value: $cosmosLocation},
        deployerObjectId: {value: $deployer},
        deployerPrincipalType: {value: $deployerType},
        publisherEmail: {value: $publisherEmail},
        publisherName: {value: $publisherName},
        modelName: {value: $modelName},
        modelVersion: {value: $modelVersion},
        modelFormat: {value: $modelFormat},
        modelSkuName: {value: $modelSku},
        modelCapacity: {value: $modelCapacity},
        telegramBotToken: {value: env.TELEGRAM_BOT_TOKEN},
        telegramWebhookSecret: {value: env.TELEGRAM_WEBHOOK_SECRET_VALUE}
      }
    }' >"$PARAMETERS_FILE"
unset TELEGRAM_WEBHOOK_SECRET_VALUE

printf 'Building Bicep...\n'
az bicep build --file "$ROOT/infra/main.bicep" --stdout >/dev/null

printf 'Previewing Azure resource changes...\n'
az deployment sub what-if \
    --name "$DEPLOYMENT_NAME" \
    --subscription "$SUBSCRIPTION_ID" \
    --location "$AZURE_LOCATION" \
    --template-file "$ROOT/infra/main.bicep" \
    --parameters "@$PARAMETERS_FILE" \
    --result-format ResourceIdOnly

printf 'Provisioning Azure resources...\n'
deployment_attempt=1
while true; do
    if DEPLOYMENT_OUTPUTS="$(
        az deployment sub create \
            --name "$DEPLOYMENT_NAME" \
            --subscription "$SUBSCRIPTION_ID" \
            --location "$AZURE_LOCATION" \
            --template-file "$ROOT/infra/main.bicep" \
            --parameters "@$PARAMETERS_FILE" \
            --query properties.outputs \
            -o json
    )"; then
        break
    fi
    if (( deployment_attempt >= INFRA_DEPLOYMENT_ATTEMPTS )); then
        printf 'Infrastructure deployment failed after %s attempts.\n' "$deployment_attempt" >&2
        exit 1
    fi
    deployment_attempt=$((deployment_attempt + 1))
    printf 'Infrastructure is not ready; retrying attempt %s/%s in %s seconds...\n' \
        "$deployment_attempt" "$INFRA_DEPLOYMENT_ATTEMPTS" "$INFRA_RETRY_DELAY_SECONDS"
    sleep "$INFRA_RETRY_DELAY_SECONDS"
done
cleanup

PROJECT_ID="$(output_value foundryProjectId)"
FOUNDRY_ACCOUNT_ID="${PROJECT_ID%/projects/*}"
PROJECT_ENDPOINT="$(output_value foundryProjectEndpoint)"
MODEL_DEPLOYMENT_NAME="$(output_value modelDeploymentName)"
COSMOS_ENDPOINT="$(output_value cosmosEndpoint)"
COSMOS_ACCOUNT_NAME="$(output_value cosmosAccountName)"
COSMOS_ACCOUNT_SCOPE="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP_NAME}"\
"/providers/Microsoft.DocumentDB/databaseAccounts/${COSMOS_ACCOUNT_NAME}"
COSMOS_DATABASE_NAME="$(output_value cosmosDatabaseName)"
COSMOS_CONTAINER_NAME="$(output_value cosmosContainerName)"
KEY_VAULT_ID="$(output_value keyVaultId)"
KEY_VAULT_URL="$(output_value keyVaultUrl)"
WEBHOOK_URL="$(output_value telegramWebhookUrl)"
APIM_NAME="$(output_value apimName)"

if ! azd_command env list -o json \
    | jq -e --arg name "$AZD_ENV_NAME" '.[] | select((.Name // .name) == $name)' >/dev/null; then
    azd_command env new "$AZD_ENV_NAME" \
        --subscription "$SUBSCRIPTION_ID" \
        --location "$AZURE_LOCATION" \
        --no-prompt
else
    azd_command env select "$AZD_ENV_NAME"
fi

azd_command env set AZURE_SUBSCRIPTION_ID "$SUBSCRIPTION_ID"
azd_command env set AZURE_LOCATION "$AZURE_LOCATION"
azd_command env set AZURE_RESOURCE_GROUP "$RESOURCE_GROUP_NAME"
azd_command env set AZURE_AI_PROJECT_ID "$PROJECT_ID"
azd_command env set AZURE_AI_PROJECT_ENDPOINT "$PROJECT_ENDPOINT"
azd_command env set FOUNDRY_PROJECT_ENDPOINT "$PROJECT_ENDPOINT"
azd_command env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$MODEL_DEPLOYMENT_NAME"
azd_command env set AZURE_COSMOS_ENDPOINT "$COSMOS_ENDPOINT"
azd_command env set AZURE_COSMOS_DATABASE_NAME "$COSMOS_DATABASE_NAME"
azd_command env set AZURE_COSMOS_CONTAINER_NAME "$COSMOS_CONTAINER_NAME"
azd_command env set KEY_VAULT_URL "$KEY_VAULT_URL"
azd_command env set ENABLE_SENSITIVE_DATA "$ENABLE_SENSITIVE_DATA"

printf 'Checking Foundry project access...\n'
access_deadline=$((SECONDS + FOUNDRY_ACCESS_TIMEOUT_SECONDS))
until azd_command ai project show --output json >/dev/null 2>&1; do
    if (( SECONDS >= access_deadline )); then
        printf 'Timed out waiting for the deployer Foundry role to propagate.\n' >&2
        azd_command ai project show --output json
        exit 1
    fi
    sleep 10
done

printf 'Validating hosted-agent metadata...\n'
azd_command ai agent doctor --local-only

printf 'Deploying hosted-agent source...\n'
azd_command deploy "$AGENT_SERVICE" --no-prompt

AGENT_JSON="$(azd_command ai agent show "$AGENT_SERVICE" --output json)"
AGENT_PRINCIPAL_ID="$(jq -r '.instance_identity.principal_id' <<<"$AGENT_JSON")"
if [[ -z "$AGENT_PRINCIPAL_ID" || "$AGENT_PRINCIPAL_ID" == "null" ]]; then
    printf 'Hosted-agent instance identity was not returned.\n' >&2
    exit 1
fi

permissions_changed=0
if [[ "$(
    az role assignment list \
        --subscription "$SUBSCRIPTION_ID" \
        --assignee "$AGENT_PRINCIPAL_ID" \
        --scope "$FOUNDRY_ACCOUNT_ID" \
        --query "[?roleDefinitionName=='Foundry User'] | length(@)" \
        -o tsv
)" == "0" ]]; then
    az role assignment create \
        --subscription "$SUBSCRIPTION_ID" \
        --assignee-object-id "$AGENT_PRINCIPAL_ID" \
        --assignee-principal-type ServicePrincipal \
        --role "Foundry User" \
        --scope "$FOUNDRY_ACCOUNT_ID" \
        -o none
    permissions_changed=1
fi

if [[ "$(
    az role assignment list \
        --subscription "$SUBSCRIPTION_ID" \
        --assignee "$AGENT_PRINCIPAL_ID" \
        --scope "$KEY_VAULT_ID" \
        --query "[?roleDefinitionName=='Key Vault Secrets User'] | length(@)" \
        -o tsv
)" == "0" ]]; then
    az role assignment create \
        --subscription "$SUBSCRIPTION_ID" \
        --assignee-object-id "$AGENT_PRINCIPAL_ID" \
        --assignee-principal-type ServicePrincipal \
        --role "Key Vault Secrets User" \
        --scope "$KEY_VAULT_ID" \
        -o none
    permissions_changed=1
fi

if [[ "$(
    az cosmosdb sql role assignment list \
        --subscription "$SUBSCRIPTION_ID" \
        --resource-group "$RESOURCE_GROUP_NAME" \
        --account-name "$COSMOS_ACCOUNT_NAME" \
        --query "[?principalId=='$AGENT_PRINCIPAL_ID' \
            && contains(roleDefinitionId, '00000000-0000-0000-0000-000000000002') \
            && scope=='$COSMOS_ACCOUNT_SCOPE'] | length(@)" \
        -o tsv
)" == "0" ]]; then
    az cosmosdb sql role assignment create \
        --subscription "$SUBSCRIPTION_ID" \
        --resource-group "$RESOURCE_GROUP_NAME" \
        --account-name "$COSMOS_ACCOUNT_NAME" \
        --scope / \
        --principal-id "$AGENT_PRINCIPAL_ID" \
        --role-definition-id 00000000-0000-0000-0000-000000000002 \
        -o none
    permissions_changed=1
fi

if [[ "$permissions_changed" == "1" && "$RBAC_PROPAGATION_WAIT_SECONDS" -gt 0 ]]; then
    printf 'Waiting %s seconds for new data-plane permissions...\n' "$RBAC_PROPAGATION_WAIT_SECONDS"
    sleep "$RBAC_PROPAGATION_WAIT_SECONDS"
fi

printf 'Checking the hosted endpoint rejects unauthenticated direct invocation...\n'
FOUNDRY_TOKEN="$(
    az account get-access-token \
        --subscription "$SUBSCRIPTION_ID" \
        --resource https://ai.azure.com/ \
        --query accessToken \
        -o tsv
)"
AGENT_ENDPOINT="$(jq -r '.agent_endpoints.invocations' <<<"$AGENT_JSON")"
if [[ "$AGENT_ENDPOINT" == *"?"* ]]; then
    HEALTH_ENDPOINT="${AGENT_ENDPOINT}&agent_session_id=deployment-health"
else
    HEALTH_ENDPOINT="${AGENT_ENDPOINT}?agent_session_id=deployment-health"
fi
health_response="$(
    curl -sS \
        -w $'\n%{http_code}' \
        -X POST "$HEALTH_ENDPOINT" \
        -H "Authorization: Bearer ${FOUNDRY_TOKEN}" \
        -H 'Content-Type: application/json' \
        -d '{}'
)"
health_status="${health_response##*$'\n'}"
if [[ "$health_status" != "401" ]]; then
    printf 'Unexpected hosted-agent health response: %s\n' "$health_status" >&2
    exit 1
fi

printf 'Synchronizing the APIM webhook secret from Key Vault...\n'
APIM_SECRET_REFRESH_URL="https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}"\
"/resourceGroups/${RESOURCE_GROUP_NAME}/providers/Microsoft.ApiManagement/service/${APIM_NAME}"\
"/namedValues/telegram-webhook-secret/refreshSecret?api-version=2024-05-01"
refresh_deadline=$((SECONDS + APIM_SECRET_REFRESH_TIMEOUT_SECONDS))
while true; do
    refreshed=0
    if az rest --method post --url "$APIM_SECRET_REFRESH_URL" --output none >/dev/null 2>&1; then
        valid_secret_response="$(
            curl -sS \
                -w $'\n%{http_code}' \
                -X POST "$WEBHOOK_URL" \
                -H 'Content-Type: application/json' \
                -H "X-Telegram-Bot-Api-Secret-Token: $webhook_secret" \
                -d '{}'
        )"
        valid_secret_status="${valid_secret_response##*$'\n'}"
        if [[ "$valid_secret_status" == "400" ]]; then
            refreshed=1
        fi
    fi
    if [[ "$refreshed" == "1" ]]; then
        break
    fi
    if (( SECONDS >= refresh_deadline )); then
        printf 'Timed out waiting for APIM to refresh the webhook secret from Key Vault.\n' >&2
        exit 1
    fi
    sleep 10
done

printf 'Checking APIM rejects an invalid webhook secret...\n'
invalid_response="$(
    curl -sS \
        -w $'\n%{http_code}' \
        -X POST "$WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -H 'X-Telegram-Bot-Api-Secret-Token: invalid' \
        -d '{"update_id":1,"message":{"chat":{"id":1,"type":"private"},"text":"hello"}}'
)"
invalid_status="${invalid_response##*$'\n'}"
if [[ "$invalid_status" != "401" ]]; then
    printf 'APIM did not reject an invalid Telegram secret: %s\n' "$invalid_status" >&2
    exit 1
fi

printf 'Registering the Telegram webhook...\n'
registration="$(
    curl -sS \
        -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
        -H 'Content-Type: application/json' \
        -d "$(
            jq -n \
                --arg url "$WEBHOOK_URL" \
                --arg secret "$webhook_secret" \
                '{
                  url: $url,
                  secret_token: $secret,
                  allowed_updates: ["message", "edited_message", "callback_query"],
                  drop_pending_updates: false
                }'
        )"
)"
if [[ "$(jq -r '.ok' <<<"$registration")" != "true" ]]; then
    printf 'Telegram webhook registration failed: %s\n' "$(jq -r '.description // "unknown error"' <<<"$registration")" >&2
    exit 1
fi

webhook_info="$(curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo")"
if ! jq -e \
    --arg url "$WEBHOOK_URL" \
    '.ok == true
      and .result.url == $url
      and ((.result.allowed_updates // []) | sort
        == (["message", "edited_message", "callback_query"] | sort))' \
    <<<"$webhook_info" >/dev/null; then
    printf 'Telegram webhook verification failed.\n' >&2
    exit 1
fi

printf '\nDeployment complete.\n'
printf 'Resource group: %s\n' "$RESOURCE_GROUP_NAME"
printf 'Telegram webhook: %s\n' "$WEBHOOK_URL"
printf 'Agent status: %s\n' "$(jq -r '.status' <<<"$AGENT_JSON")"
