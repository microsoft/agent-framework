# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.ai.projects.models import RaiConfig
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Content Filtering (RAI Policy) Example

This sample demonstrates how to enable content filtering on Azure AI agents using RaiConfig.

Prerequisites:
1. Create an RAI Policy in Azure AI Foundry portal:
   - Go to Azure AI Foundry > Your Project > Guardrails + Controls > Content Filters
   - Create a new content filter or use an existing one
   - Note the policy name

2. Set environment variables:
   - AZURE_AI_PROJECT_ENDPOINT: Your Azure AI Foundry project endpoint
   - AZURE_AI_MODEL_DEPLOYMENT_NAME: Your model deployment name

3. Run `az login` to authenticate
"""


async def main() -> None:
    print("=== Azure AI Agent with Content Filtering ===\n")

    # Replace with your RAI policy from Azure AI Foundry portal
    rai_policy_name = (
        "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/"
        "Microsoft.CognitiveServices/accounts/{accountName}/raiPolicies/{policyName}"
    )

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # Create agent with content filtering enabled via default_options
        agent = await provider.create_agent(
            name="ContentFilteredAgent",
            instructions="You are a helpful assistant.",
            default_options={"rai_config": RaiConfig(rai_policy_name=rai_policy_name)},
        )

        # Test with a normal query
        query = "What is the capital of France?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

        # Test with a query that might trigger content filtering
        # (depending on your RAI policy configuration)
        query2 = "Tell me something inappropriate."
        print(f"User: {query2}")
        try:
            result2 = await agent.run(query2)
            print(f"Agent: {result2}\n")
        except Exception as e:
            print(f"Content filter triggered: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
