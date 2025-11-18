# Agent Framework - Cua Integration

Computer use integration for Microsoft Agent Framework powered by [Cua](https://github.com/trycua/cua).

> [!IMPORTANT]
> **Experimental Feature**: This integration is experimental and **not recommended for production use**. It is designed for development, testing, and exploration of computer-use capabilities. For production deployments, thoroughly evaluate security, reliability, and specific requirements for your use case.

## Overview

This package provides seamless integration between Microsoft Agent Framework and Cua, enabling AI agents to control desktop applications across Windows, macOS, and Linux.

`CuaAgentMiddleware` wraps Cua's `ComputerAgent`, which handles the complete agent loop (model inference → parsing → computer actions → multi-step execution). Learn more about [Cua Agent Loops](https://docs.cua.ai/docs/agent-sdk/agent-loops).

### Key Features

- **100+ Model Support**: OpenAI, Anthropic, OpenCUA, InternVL, UI-Tars, GLM, and more
- **Composite Agents**: Combine grounding + planning models (e.g., "ui-tars+gpt-4o")
- **Cross-Platform**: Windows Sandbox, macOS VMs, Linux Docker
- **Human-in-the-Loop**: Built-in approval workflows via Agent Framework middleware
- **Provider Agnostic**: Switch models with a single parameter change

## Installation

```bash
pip install agent-framework-cua
```

## Configuration

Set API keys for the models you plan to use. Cua delegates to the underlying model providers:

```bash
# For Anthropic models (Claude)
export ANTHROPIC_API_KEY="your-anthropic-key"

# For OpenAI models (GPT-4o, GPT-4o-mini)
export OPENAI_API_KEY="your-openai-key"

# For Azure OpenAI
export AZURE_API_KEY="your-azure-key"
export AZURE_API_BASE="https://your-resource.openai.azure.com"
export AZURE_API_VERSION="2024-02-01"
```

**Notes:**
- Only set keys for the models you'll actually use. For example, if using `model="anthropic/claude-sonnet-4-5-20250929"`, you only need `ANTHROPIC_API_KEY`.
- Local models (e.g., `huggingface-local/ByteDance/OpenCUA-7B`) don't require API keys.

## Quick Start

```python
import asyncio
from agent_framework import ChatAgent
from agent_framework_cua import CuaChatClient, CuaAgentMiddleware
from computer import Computer

async def main():
    # Initialize Cua computer (Linux Docker - recommended, cross-platform)
    async with Computer(
        os_type="linux",
        provider_type="docker"
    ) as computer:

        # Create Cua chat client with model and instructions
        chat_client = CuaChatClient(
            model="anthropic/claude-sonnet-4-5-20250929",
            instructions="You are a desktop automation assistant.",
        )

        # Create middleware
        cua_middleware = CuaAgentMiddleware(
            computer=computer,
            require_approval=True,
        )

        # Create Agent Framework agent
        agent = ChatAgent(
            chat_client=chat_client,
            middleware=[cua_middleware],
        )

        # Run agent
        response = await agent.run(
            "Open Firefox and search for 'Python tutorials'"
        )

        print(response)

if __name__ == "__main__":
    asyncio.run(main())
```

## Using Different Models

### OpenAI Computer Use
```python
from agent_framework_cua import CuaChatClient, CuaAgentMiddleware

chat_client = CuaChatClient(
    model="openai/gpt-4o",
)
middleware = CuaAgentMiddleware(computer=computer)
```

### OpenCUA (Local Model)
```python
from agent_framework_cua import CuaChatClient, CuaAgentMiddleware

chat_client = CuaChatClient(
    model="huggingface-local/ByteDance/OpenCUA-7B",
)
middleware = CuaAgentMiddleware(
    computer=computer,
    require_approval=False,  # No approval for local models
)
```

### Composite Agent (Grounding + Planning)
```python
from agent_framework_cua import CuaChatClient, CuaAgentMiddleware

# Combine UI-Tars (grounding) with GPT-4o (planning)
chat_client = CuaChatClient(
    model="huggingface-local/ByteDance-Seed/UI-TARS-1.5-7B+openai/gpt-4o",
)
middleware = CuaAgentMiddleware(computer=computer)
```

## Configuration Options

```python
# CuaChatClient - stores model and instructions
CuaChatClient(
    model: str = "anthropic/claude-sonnet-4-5-20250929",  # Model identifier
    instructions: str | None = None,                       # System instructions
)

# CuaAgentMiddleware - handles computer automation
CuaAgentMiddleware(
    computer: Computer,                 # Cua Computer instance
    model: str | None = None,           # Optional: override client model
    instructions: str | None = None,    # Optional: override client instructions
    max_trajectory_budget: float = 5.0, # Max cost budget
    require_approval: bool = True,      # Human approval required
    approval_interval: int = 5,         # Steps between approvals
)
```

**Note**: Model and instructions are typically provided via `CuaChatClient`. You can optionally override them in `CuaAgentMiddleware`.

## Integration with Workflows

Agent Framework provides orchestration while Cua handles execution:

```python
async def multi_agent_workflow(task: str) -> str:
    # Step 1: Research Agent (Pure Agent Framework)
    research_agent = ChatAgent(
        chat_client=OpenAIChatClient(model_id="gpt-4o-mini"),
        instructions="Create a detailed automation plan",
    )
    plan = await research_agent.run(f"Create plan for: {task}")

    # Step 2: Cua Automation (Agent Framework + Cua)
    async with Computer(os_type="linux", provider_type="docker") as computer:
        cua_chat_client = CuaChatClient(
            model="anthropic/claude-sonnet-4-5-20250929",
            instructions="Execute the plan carefully",
        )

        cua_middleware = CuaAgentMiddleware(
            computer=computer,
            require_approval=True,  # Agent Framework approval workflows
        )

        automation_agent = ChatAgent(
            chat_client=cua_chat_client,
            middleware=[cua_middleware],
        )
        result = await automation_agent.run(f"Execute: {plan}")

    # Step 3: Verification Agent (Pure Agent Framework)
    verify_agent = ChatAgent(
        chat_client=OpenAIChatClient(model_id="gpt-4o"),
        instructions="Verify and summarize results",
    )
    return await verify_agent.run(f"Verify: {result}")
```

See the [Workflow Orchestration sample](../../samples/getting_started/cua/workflow_orchestration/) for a complete example.

## VM Provider Options

For more details on Cua computer configuration, see [Cua Computers documentation](https://docs.cua.ai/docs/computer-sdk/computers).

### Linux on Docker (Cross-platform)

**Recommended** - Works on macOS, Windows, and Linux hosts.

```python
from computer import Computer
from agent_framework_cua import CuaAgentMiddleware

async with Computer(os_type="linux", provider_type="docker") as computer:
    cua_middleware = CuaAgentMiddleware(
        computer=computer,
        model="anthropic/claude-sonnet-4-5-20250929",
    )
    # Use with ChatAgent...
```

**Prerequisites:**
```bash
# Install Docker Desktop or Docker Engine
docker pull --platform=linux/amd64 trycua/cua-xfce:latest
```

### macOS VM (Lume)

**macOS hosts only** - Native macOS virtualization with 97% native CPU performance.

```python
from computer import Computer
from agent_framework_cua import CuaAgentMiddleware

async with Computer(os_type="macos", provider_type="lume") as computer:
    cua_middleware = CuaAgentMiddleware(
        computer=computer,
        model="anthropic/claude-sonnet-4-5-20250929",
    )
    # Use with ChatAgent...
```

**Prerequisites:**
```bash
# Install Lume CLI
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/trycua/cua/main/libs/lume/scripts/install.sh)"

# Start macOS VM
lume run macos-sequoia-cua:latest
```

### Windows Sandbox

**Windows hosts only** - Requires Windows 10 Pro/Enterprise or Windows 11.

```python
from computer import Computer
from agent_framework_cua import CuaAgentMiddleware

async with Computer(os_type="windows", provider_type="winsandbox") as computer:
    cua_middleware = CuaAgentMiddleware(
        computer=computer,
        model="anthropic/claude-sonnet-4-5-20250929",
    )
    # Use with ChatAgent...
```

**Prerequisites:**
```bash
# Enable Windows Sandbox in Windows Features
# Install pywinsandbox dependency
pip install -U git+git://github.com/karkason/pywinsandbox.git
```

### Cloud Sandbox

**Any host** - Managed Cua cloud infrastructure.

```python
from computer import Computer
from agent_framework_cua import CuaAgentMiddleware

async with Computer(
    os_type="linux",
    provider_type="cloud",
    name="your-sandbox-name",
    api_key="your-api-key",
) as computer:
    cua_middleware = CuaAgentMiddleware(
        computer=computer,
        model="anthropic/claude-sonnet-4-5-20250929",
    )
    # Use with ChatAgent...
```

## Examples

See [samples/getting_started/cua](../../samples/getting_started/cua/) for complete working examples:

- **[Basic Example](../../samples/getting_started/cua/basic_example/)** - Getting started with Cua + Agent Framework
- **[Composite Agent](../../samples/getting_started/cua/composite_agent/)** - Combining grounding + planning models
- **[Workflow Orchestration](../../samples/getting_started/cua/workflow_orchestration/)** - Multi-agent workflows showing Agent Framework synergies

## Resources

- [Cua Documentation](https://docs.cua.ai)
  - [Agent Loops](https://docs.cua.ai/docs/agent-sdk/agent-loops) - How Cua's ComputerAgent works
  - [Computers](https://docs.cua.ai/docs/computer-sdk/computers) - Platform-specific setup guides
- [Cua GitHub](https://github.com/trycua/cua)
- [Agent Framework Documentation](https://learn.microsoft.com/agent-framework/)

## License

MIT License - see [LICENSE](./LICENSE) file for details.
