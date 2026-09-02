# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import stat
from pathlib import Path
from xml.etree import ElementTree

import tomllib
import yaml

SAMPLE_ROOT = Path(__file__).parents[1]


def test_direct_code_invocations_2_configuration() -> None:
    azure_yaml = yaml.safe_load((SAMPLE_ROOT / "azure.yaml").read_text())
    service = azure_yaml["services"]["telegram-agent"]

    assert service["codeConfiguration"] == {
        "dependencyResolution": "remote_build",
        "entryPoint": "main.py",
        "runtime": "python_3_13",
    }
    assert service["protocols"] == [{"protocol": "invocations", "version": "2.0.0"}]


def test_dependencies_use_sample_local_pyproject() -> None:
    project = tomllib.loads((SAMPLE_ROOT / "pyproject.toml").read_text())
    dependencies = project["project"]["dependencies"]
    pep621_names = {dependency.split(">=", 1)[0] for dependency in dependencies}
    poetry_names = set(project["tool"]["poetry"]["dependencies"]) - {"python"}

    assert not (SAMPLE_ROOT / "requirements.txt").exists()
    assert "agent-framework-foundry" in pep621_names
    assert "agent-framework-hosting-telegram" in pep621_names
    assert "azure-monitor-opentelemetry" in pep621_names
    assert poetry_names == pep621_names
    assert project["tool"]["uv"]["package"] is False


def test_sensitive_telemetry_is_configurable_for_hosted_agent() -> None:
    azure_yaml = (SAMPLE_ROOT / "azure.yaml").read_text()
    deploy_script = (SAMPLE_ROOT / "deploy.sh").read_text()

    assert "ENABLE_SENSITIVE_DATA" in azure_yaml
    assert 'ENABLE_SENSITIVE_DATA="${ENABLE_SENSITIVE_DATA:-true}"' in deploy_script
    assert 'azd_command env set ENABLE_SENSITIVE_DATA "$ENABLE_SENSITIVE_DATA"' in deploy_script


def test_agent_instructions_are_included_in_deployment() -> None:
    agent_ignore = (SAMPLE_ROOT / ".agentignore").read_text()
    main_source = (SAMPLE_ROOT / "main.py").read_text()

    assert "!instructions.md" in agent_ignore
    assert 'Path(__file__).parent / "instructions.md"' in main_source


def test_apim_policy_preserves_update_and_injects_channel() -> None:
    policy_path = SAMPLE_ROOT / "infra" / "telegram-policy.xml"
    rendered = (
        policy_path
        .read_text()
        .replace(
            "__FOUNDRY_SERVICE_ENDPOINT__",
            "https://sample.services.ai.azure.com",
        )
        .replace(
            "__FOUNDRY_INVOCATIONS_PATH__",
            "/api/projects/sample/agents/telegram-agent/endpoint/protocols/invocations",
        )
    )
    root = ElementTree.fromstring(rendered)
    body_policy = root.find("./inbound/set-body")

    assert body_policy is not None
    assert "preserveContent: true" in rendered
    assert "body[&quot;channel&quot;] = &quot;telegram&quot;" in rendered
    assert "return body.ToString" in (body_policy.text or "")
    assert 'name="Content-Encoding" exists-action="delete"' in rendered
    assert 'name="agent_session_id"' in rendered
    assert 'name="X-Telegram-Bot-Api-Secret-Token" exists-action="delete"' in rendered
    assert 'name="X-Agent-Framework-Ingress-Secret" exists-action="override"' in rendered
    assert "<value>{{TelegramWebhookSecret}}</value>" in rendered


def test_cosmos_partition_key_is_session_id() -> None:
    resources = (SAMPLE_ROOT / "infra" / "resources.bicep").read_text()

    assert "paths: [" in resources
    assert "'/session_id'" in resources


def test_deployment_health_check_rejects_direct_invocation_and_is_subscription_scoped() -> None:
    deploy_script = (SAMPLE_ROOT / "deploy.sh").read_text()

    assert 'if [[ "$health_status" != "401" ]]' in deploy_script
    assert "Authorization: Bearer ${FOUNDRY_TOKEN}" in deploy_script
    assert 'az account get-access-token \\\n        --subscription "$SUBSCRIPTION_ID"' in deploy_script
    assert 'az cosmosdb sql role assignment create \\\n        --subscription "$SUBSCRIPTION_ID"' in deploy_script
    assert '--role "Foundry User"' in deploy_script
    assert '--scope "$FOUNDRY_ACCOUNT_ID"' in deploy_script
    assert "contains(roleDefinitionId, '00000000-0000-0000-0000-000000000002')" in deploy_script
    assert "&& scope=='$COSMOS_ACCOUNT_SCOPE'" in deploy_script
    assert "/namedValues/telegram-webhook-secret/refreshSecret?api-version=2024-05-01" in deploy_script
    assert 'if [[ "$valid_secret_status" == "400" ]]' in deploy_script


def test_deployment_and_removal_require_sample_owned_resource_group() -> None:
    main_bicep = (SAMPLE_ROOT / "infra" / "main.bicep").read_text()
    deploy_script = (SAMPLE_ROOT / "deploy.sh").read_text()
    remove_script = (SAMPLE_ROOT / "remove.sh").read_text()
    ownership_tag = "agent-framework-telegram-hosted-agent"

    assert f"sample: '{ownership_tag}'" in main_bicep
    assert f'!= "{ownership_tag}"' in deploy_script
    assert "already exists without the Telegram sample ownership tag" in deploy_script
    assert f'!= "{ownership_tag}"' in remove_script
    assert "Refusing to remove resource group" in remove_script
    assert remove_script.index("Refusing to remove resource group") < remove_script.index("/deleteWebhook")


def test_default_model_is_gpt_5_6_luna() -> None:
    deploy_script = (SAMPLE_ROOT / "deploy.sh").read_text()

    assert 'MODEL_NAME="${MODEL_NAME:-gpt-5.6-luna}"' in deploy_script
    assert 'MODEL_VERSION="${MODEL_VERSION:-2026-07-09}"' in deploy_script
    assert 'MODEL_SKU_NAME="${MODEL_SKU_NAME:-DataZoneStandard}"' in deploy_script


def test_remove_script_unregisters_webhook_before_deleting_resource_group() -> None:
    remove_path = SAMPLE_ROOT / "remove.sh"
    remove_script = remove_path.read_text()

    assert remove_path.stat().st_mode & stat.S_IXUSR
    assert ': "${TELEGRAM_BOT_TOKEN:?Set TELEGRAM_BOT_TOKEN before running this script.}"' in remove_script
    assert remove_script.index("/deleteWebhook") < remove_script.index("az group delete")
    assert 'if [[ "$(jq -r \'.ok\' <<<"$webhook_deletion")" != "true" ]]' in remove_script
    assert 'RESOURCE_GROUP_NAME="${RESOURCE_GROUP_NAME:-rg-${NAME_PREFIX}}"' in remove_script
    assert '--subscription "$SUBSCRIPTION_ID"' in remove_script
