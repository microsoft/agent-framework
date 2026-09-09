#!/usr/bin/env bash

set -euo pipefail

NAME_PREFIX="${NAME_PREFIX:-telegramagent}"
RESOURCE_GROUP_NAME="${RESOURCE_GROUP_NAME:-rg-${NAME_PREFIX}}"

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'Required command not found: %s\n' "$1" >&2
        exit 1
    }
}

require_command az
require_command curl
require_command jq

: "${TELEGRAM_BOT_TOKEN:?Set TELEGRAM_BOT_TOKEN before running this script.}"

if [[ ! "$NAME_PREFIX" =~ ^[a-z0-9]{3,16}$ ]]; then
    printf 'NAME_PREFIX must contain 3-16 lowercase letters or digits.\n' >&2
    exit 1
fi

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"

if [[ "$(
    az group exists \
        --subscription "$SUBSCRIPTION_ID" \
        --name "$RESOURCE_GROUP_NAME"
)" != "true" ]]; then
    printf 'Resource group does not exist: %s\n' "$RESOURCE_GROUP_NAME"
    exit 0
fi

group_tags="$(
    az group show \
        --subscription "$SUBSCRIPTION_ID" \
        --name "$RESOURCE_GROUP_NAME" \
        --query tags \
        -o json
)"
if [[ "$(jq -r '.sample // ""' <<<"$group_tags")" != "agent-framework-telegram-hosted-agent" ]]; then
    printf 'Refusing to remove resource group %s without the Telegram sample ownership tag.\n' \
        "$RESOURCE_GROUP_NAME" >&2
    exit 1
fi

printf 'Removing the Telegram webhook...\n'
webhook_deletion="$(
    curl -sS \
        -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook" \
        -H 'Content-Type: application/json' \
        -d '{"drop_pending_updates":false}'
)"
if [[ "$(jq -r '.ok' <<<"$webhook_deletion")" != "true" ]]; then
    printf 'Telegram webhook removal failed: %s\n' \
        "$(jq -r '.description // "unknown error"' <<<"$webhook_deletion")" >&2
    exit 1
fi

printf 'Deleting resource group %s...\n' "$RESOURCE_GROUP_NAME"
az group delete \
    --subscription "$SUBSCRIPTION_ID" \
    --name "$RESOURCE_GROUP_NAME" \
    --yes

printf 'Removal complete.\n'
