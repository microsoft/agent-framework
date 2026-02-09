# Copyright (c) Microsoft. All rights reserved.

import asyncio
from pathlib import Path

from agent_framework.declarative import AgentFactory

"""
Declarative Agents

Demonstrates creating an agent from a YAML specification using AgentFactory.
Declarative agents let you define agent configuration (model, instructions,
tools, output schema) in YAML files separate from your code.

For more declarative examples:
- OpenAI: getting_started/declarative/openai_responses_agent.py
- Azure OpenAI: getting_started/declarative/azure_openai_responses_agent.py
- Inline YAML: getting_started/declarative/inline_yaml.py
- MCP tools in YAML: getting_started/declarative/mcp_tool_yaml.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/declarative-agents
"""


# <inline_yaml>
AGENT_YAML = """
kind: Prompt
name: Assistant
description: A helpful assistant
instructions: >
  You are a helpful assistant. Answer questions clearly and concisely.
  Always be polite and informative.
model:
    id: gpt-4.1-mini
    provider: OpenAI
    apiType: Responses
    options:
        temperature: 0.7
"""
# </inline_yaml>


async def from_inline_yaml() -> None:
    """Create an agent from an inline YAML string."""
    print("=== Declarative Agent from Inline YAML ===\n")

    # <create_from_yaml>
    agent = AgentFactory().create_agent_from_yaml(AGENT_YAML)

    response = await agent.run("What are three benefits of declarative agent configuration?")
    print(f"Agent: {response.text}")
    # </create_from_yaml>


async def from_yaml_file() -> None:
    """Create an agent from a YAML file on disk."""
    print("\n=== Declarative Agent from YAML File ===\n")

    # <create_from_file>
    # Load YAML from a file
    yaml_path = Path(__file__).parent.parent.parent.parent.parent / "agent-samples" / "openai" / "OpenAIResponses.yaml"

    if not yaml_path.exists():
        print(f"YAML file not found at {yaml_path}. Skipping file-based example.")
        return

    with yaml_path.open("r") as f:
        yaml_str = f.read()

    agent = AgentFactory().create_agent_from_yaml(yaml_str)

    response = await agent.run("Why is the sky blue?")
    # Declarative agents may return structured output defined in the YAML schema
    try:
        parsed = response.value
        print(f"Agent (parsed): {parsed}")
    except Exception:
        print(f"Agent: {response.text}")
    # </create_from_file>


async def main() -> None:
    await from_inline_yaml()
    await from_yaml_file()


if __name__ == "__main__":
    asyncio.run(main())
