# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "openai>=1.50,<3",
#     "azure-identity>=1.19,<2",
# ]
# ///
# Run with: uv run call_server.py

# Copyright (c) Microsoft. All rights reserved.

"""Call the deployed Hyperlight CodeAct Foundry hosted agent via the OpenAI client."""

import os

from azure.identity import AzureCliCredential
from openai import OpenAI

# Set FOUNDRY_AGENT_ENDPOINT to your deployed agent endpoint, e.g.
#   https://<your-foundry-resource>.services.ai.azure.com/api/projects/<project>/agents/<agent-name>
ENDPOINT = os.environ.get(
    "FOUNDRY_AGENT_ENDPOINT",
    "https://<your-foundry-resource>.services.ai.azure.com"
    "/api/projects/<project>/agents/<agent-name>",
)
SCOPE = "https://ai.azure.com/.default"
PROMPT = (
    "Fetch all users, find the admins, multiply 7 by 6, and print the users, "
    "admins and multiplication result. Use execute_code with call_tool(...)."
)


def main() -> None:
    token = AzureCliCredential().get_token(SCOPE).token
    client = OpenAI(base_url=ENDPOINT, api_key=token, default_query={"api-version": "v1"})
    response = client.responses.create(model="hosted-agent", input=PROMPT)
    print(response.output_text)


if __name__ == "__main__":
    main()
