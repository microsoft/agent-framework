# Copyright (c) Microsoft. All rights reserved.

"""Run agent-generated Python in an Azure Container Apps Dynamic Sessions pool.

Prerequisites:
- Install agent-framework-foundry, azure-identity, and httpx; sign in with az login.
- Set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL for your model deployment.
- Set POOL_MANAGEMENT_ENDPOINT to the Python code-interpreter pool's management
  endpoint (az containerapp sessionpool show --query properties.poolManagementEndpoint).
- Give the signed-in identity Azure ContainerApps Session Executor on the pool,
  and permission to invoke the Foundry model.

Each program run generates a fresh session identifier, reused for its tool calls.
The identifier is owned by the application, never selected by the model. In a
multi-user host, create a separate agent/tool/session binding for each authorized
conversation. Pool cooldown controls cleanup after the last use; this sample does
not provision or delete Azure resources. Model and session-pool usage incur costs.

The tool sends code to the configured cloud sandbox; it does not execute code on
this machine. Configure the pool's network access for your workload and do not
pass application credentials or confidential data into generated code.

REST contract:
https://learn.microsoft.com/rest/api/data-plane/containerapps/code-execution/execute
"""

import asyncio
import os
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    pool_endpoint = os.environ["POOL_MANAGEMENT_ENDPOINT"].rstrip("/")
    endpoint = urlsplit(pool_endpoint)
    if (
        endpoint.scheme != "https"
        or not endpoint.netloc
        or "?" in pool_endpoint
        or "#" in pool_endpoint
        or endpoint.username is not None
    ):
        raise ValueError("POOL_MANAGEMENT_ENDPOINT must be a trusted HTTPS pool URL without credentials or a query.")
    session_id = str(uuid4())

    async with AzureCliCredential() as credential, httpx.AsyncClient(timeout=70, follow_redirects=False) as http_client:

        @tool
        async def execute_python(
            code: Annotated[str, "Python code to execute in the remote session."],
        ) -> dict[str, Any]:
            """Run Python in the conversation's cloud sandbox and return its output and execution status."""
            token = await credential.get_token("https://dynamicsessions.io/.default")
            response = await http_client.post(
                f"{pool_endpoint}/executions",
                params={"api-version": "2025-10-02-preview", "identifier": session_id},
                headers={"Authorization": f"Bearer {token.token}"},
                json={
                    "codeInputType": "Inline",
                    "executionType": "Synchronous",
                    "code": code,
                    "timeoutInSeconds": 30,
                    "outputStreamsMaxLength": 4096,
                },
            )
            response.raise_for_status()
            return response.json()

        async with Agent(
            client=FoundryChatClient(
                project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                model=os.environ["FOUNDRY_MODEL"],
                credential=credential,
            ),
            instructions="Use execute_python for calculations. Check its status and errors before reporting a result.",
            tools=[execute_python],
        ) as agent:
            result = await agent.run("Use Python to calculate the total of 19.95, 42.50, and 8.75, then add 8% tax.")
            print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
